"""Market Feed Adapters: Unified WebSocket Push & REST Polling Adapters for MarketEventBus."""

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from packages.core.event_bus import MarketEventBus, TickerUpdateEvent
from packages.execution.base import BaseBrokerGateway

logger = logging.getLogger(__name__)


class BaseMarketFeedAdapter(ABC):
    """Abstract base adapter that feeds standardized TickerUpdateEvents into a MarketEventBus."""

    def __init__(
        self,
        gateway: BaseBrokerGateway,
        event_bus: MarketEventBus,
        symbols: List[str],
        market_type: Optional[str] = None,
    ):
        self.gateway = gateway
        self.event_bus = event_bus
        self.symbols = [s.replace("-", "/").replace("_", "/").upper() for s in symbols]
        self.market_type = (market_type or gateway.default_market_type).upper()
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """Start feeding market events into the EventBus."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop background market feed."""
        pass

    @abstractmethod
    def get_feed_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the feed."""
        pass


class PollingMarketFeedAdapter(BaseMarketFeedAdapter):
    """REST Polling Market Feed Adapter for exchanges that do not support WebSocket."""

    def __init__(
        self,
        gateway: BaseBrokerGateway,
        event_bus: MarketEventBus,
        symbols: List[str],
        market_type: Optional[str] = None,
        poll_interval_sec: float = 5.0,
    ):
        super().__init__(gateway=gateway, event_bus=event_bus, symbols=symbols, market_type=market_type)
        self.poll_interval_sec = max(0.5, float(poll_interval_sec))
        self._thread: Optional[threading.Thread] = None
        self._poll_count = 0

    def poll_once(self, source_label: str = "POLLING") -> int:
        """Fetch tickers synchronously via gateway REST/mock and publish TickerUpdateEvents."""
        emitted = 0
        for sym in self.symbols:
            try:
                ticker = self.gateway.fetch_ticker(sym, market_type=self.market_type)
                price = float(ticker.get("price", 0.0))
                if price <= 0:
                    continue
                bid = float(ticker.get("bid", price))
                ask = float(ticker.get("ask", price))
                ts = int(ticker.get("timestamp", int(time.time() * 1000)))
                ev = TickerUpdateEvent(
                    exchange=self.gateway.exchange_name,
                    symbol=sym,
                    market_type=self.market_type,
                    price=price,
                    bid=bid,
                    ask=ask,
                    timestamp_ms=ts,
                    source=source_label,
                )
                self.event_bus.publish(ev)
                emitted += 1
            except Exception as exc:
                logger.debug(f"PollingMarketFeedAdapter failed to poll {sym}: {exc}")
        self._poll_count += 1
        return emitted

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"PollingFeed-{self.gateway.exchange_name}-{self.market_type}",
        )
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            self.poll_once(source_label="POLLING")
            sleep_steps = max(1, int(self.poll_interval_sec * 10))
            for _ in range(sleep_steps):
                if not self._running:
                    break
                time.sleep(self.poll_interval_sec / sleep_steps)

    def stop(self) -> None:
        self._running = False

    def get_feed_status(self) -> Dict[str, Any]:
        return {
            "mode": "POLLING",
            "exchange": self.gateway.exchange_name,
            "market_type": self.market_type,
            "running": self._running,
            "poll_count": self._poll_count,
        }


class HybridWebSocketFeedAdapter(BaseMarketFeedAdapter):
    """Real-time WebSocket Market Feed Adapter with automatic REST Polling Fallback on disconnect."""

    def __init__(
        self,
        gateway: BaseBrokerGateway,
        event_bus: MarketEventBus,
        symbols: List[str],
        market_type: Optional[str] = None,
        fallback_poll_interval_sec: float = 5.0,
        stale_timeout_sec: float = 6.0,
    ):
        super().__init__(gateway=gateway, event_bus=event_bus, symbols=symbols, market_type=market_type)
        self.fallback_poll_interval_sec = max(1.0, float(fallback_poll_interval_sec))
        self.stale_timeout_sec = float(stale_timeout_sec)
        self._last_ws_tick_ts: Dict[str, float] = {}
        self._ws_event_count = 0
        self._fallback_event_count = 0
        self._active_source = "WEBSOCKET"
        self._watchdog_thread: Optional[threading.Thread] = None

    def _on_ws_tick(self, cached_ticker: Dict[str, Any]) -> None:
        """Callback invoked directly by BingXWebSocketClient on every incoming tick."""
        m_type = str(cached_ticker.get("market_type", "")).upper()
        if m_type != self.market_type:
            return
        sym = str(cached_ticker.get("symbol", "")).replace("-", "/").upper()
        if sym not in self.symbols:
            return
        price = float(cached_ticker.get("price", 0.0))
        if price <= 0:
            return

        now = time.time()
        self._last_ws_tick_ts[sym] = now
        self._ws_event_count += 1
        self._active_source = "WEBSOCKET"

        ev = TickerUpdateEvent(
            exchange=self.gateway.exchange_name,
            symbol=sym,
            market_type=m_type,
            price=price,
            bid=float(cached_ticker.get("bid", price)),
            ask=float(cached_ticker.get("ask", price)),
            timestamp_ms=int(cached_ticker.get("timestamp", int(now * 1000))),
            source="WEBSOCKET",
        )
        self.event_bus.publish(ev)

    def ingest_ws_payload(self, payload: Dict[str, Any], market_type: Optional[str] = None) -> Optional[TickerUpdateEvent]:
        """Parse a raw BingX WebSocket JSON payload and immediately emit TickerUpdateEvent."""
        m_type = (market_type or self.market_type).upper()
        data_type = str(payload.get("dataType", ""))
        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        raw_sym = str(data.get("s", ""))
        if not raw_sym and "@" in data_type:
            raw_sym = data_type.split("@")[0]
        if not raw_sym:
            return None

        clean_sym = raw_sym.replace("-", "/").replace("_", "/").upper()
        price = float(data.get("c", data.get("lastPrice", 0.0)) or 0.0)
        if price <= 0:
            return None

        bid = float(data.get("B", data.get("bidPrice", price)) or price)
        ask = float(data.get("A", data.get("askPrice", price)) or price)
        ts = int(data.get("E", data.get("time", int(time.time() * 1000))))

        self._on_ws_tick(
            {
                "symbol": clean_sym,
                "market_type": m_type,
                "price": price,
                "bid": bid,
                "ask": ask,
                "timestamp": ts,
            }
        )
        return TickerUpdateEvent(
            exchange=self.gateway.exchange_name,
            symbol=clean_sym,
            market_type=m_type,
            price=price,
            bid=bid,
            ask=ask,
            timestamp_ms=ts,
            source="WEBSOCKET",
        )

    def check_health_and_fallback(self) -> int:
        """Check if WebSocket ticks are fresh; if stale or disconnected, poll via REST fallback."""
        now = time.time()
        emitted = 0
        for sym in self.symbols:
            last_ts = self._last_ws_tick_ts.get(sym, 0.0)
            is_stale = (now - last_ts) >= self.stale_timeout_sec
            if is_stale:
                try:
                    ticker = self.gateway.fetch_ticker(sym, market_type=self.market_type)
                    price = float(ticker.get("price", 0.0))
                    if price <= 0:
                        continue
                    self._fallback_event_count += 1
                    self._active_source = "POLLING_FALLBACK"
                    ev = TickerUpdateEvent(
                        exchange=self.gateway.exchange_name,
                        symbol=sym,
                        market_type=self.market_type,
                        price=price,
                        bid=float(ticker.get("bid", price)),
                        ask=float(ticker.get("ask", price)),
                        timestamp_ms=int(ticker.get("timestamp", int(now * 1000))),
                        source="POLLING_FALLBACK",
                    )
                    self.event_bus.publish(ev)
                    emitted += 1
                except Exception as exc:
                    logger.debug(f"HybridWebSocketFeedAdapter fallback poll failed for {sym}: {exc}")
        return emitted

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        ws_client = getattr(self.gateway, "ws_client", None)
        if ws_client is not None and hasattr(ws_client, "register_listener"):
            ws_client.register_listener(self._on_ws_tick)
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name=f"HybridWSWatchdog-{self.gateway.exchange_name}-{self.market_type}",
        )
        self._watchdog_thread.start()

    def _watchdog_loop(self) -> None:
        while self._running:
            self.check_health_and_fallback()
            sleep_steps = max(1, int(self.fallback_poll_interval_sec * 5))
            for _ in range(sleep_steps):
                if not self._running:
                    break
                time.sleep(self.fallback_poll_interval_sec / sleep_steps)

    def stop(self) -> None:
        self._running = False
        ws_client = getattr(self.gateway, "ws_client", None)
        if ws_client is not None and hasattr(ws_client, "unregister_listener"):
            ws_client.unregister_listener(self._on_ws_tick)

    def get_feed_status(self) -> Dict[str, Any]:
        return {
            "mode": "HYBRID_WEBSOCKET",
            "active_source": self._active_source,
            "exchange": self.gateway.exchange_name,
            "market_type": self.market_type,
            "running": self._running,
            "ws_event_count": self._ws_event_count,
            "fallback_event_count": self._fallback_event_count,
        }
