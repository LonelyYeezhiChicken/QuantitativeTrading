"""Unified Multi-Exchange Market EventBus & In-Memory Kline Rolling Cache.

Provides:
- Immutable domain events (`TickerUpdateEvent`, `KlineCacheUpdatedEvent`)
- Thread-safe `MarketEventBus` with isolated subscriber execution
- `InMemoryKlineRollingCache` for zero-API-overhead real-time indicator synthesis on every tick
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TickerUpdateEvent:
    """Standardized real-time ticker update emitted by either WebSocket push or REST polling adapter."""

    exchange: str
    symbol: str
    market_type: str  # "SPOT" or "SWAP"
    price: float
    bid: float
    ask: float
    timestamp_ms: int
    source: str = "WEBSOCKET"  # "WEBSOCKET" | "POLLING" | "POLLING_FALLBACK"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KlineCacheUpdatedEvent:
    """Emitted when the background 1h OHLC bar cache is refreshed."""

    exchange: str
    symbol: str
    market_type: str
    bars_count: int
    timestamp_ms: int


class MarketEventBus:
    """Thread-safe publish/subscribe event bus decoupling market feeds from trading engines."""

    def __init__(self):
        self._subscribers: Dict[Type[Any], List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()
        self._published_count = 0
        self._last_event_ts = 0.0

    def subscribe(self, event_type: Type[Any], handler: Callable[[Any], None]) -> None:
        """Subscribe a callback handler to a specific event class."""
        with self._lock:
            handlers = self._subscribers.setdefault(event_type, [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, event_type: Type[Any], handler: Callable[[Any], None]) -> None:
        """Unsubscribe a callback handler from an event class."""
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: Any) -> int:
        """Publish an event synchronously to all registered subscribers with fault isolation."""
        event_type = type(event)
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))
            self._published_count += 1
            self._last_event_ts = time.time()

        delivered = 0
        for handler in handlers:
            try:
                handler(event)
                delivered += 1
            except Exception as exc:
                logger.warning(f"MarketEventBus subscriber error on {event_type.__name__}: {exc}")
        return delivered

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic bus telemetry."""
        with self._lock:
            return {
                "published_count": self._published_count,
                "last_event_ts": self._last_event_ts,
                "subscriber_types": {k.__name__: len(v) for k, v in self._subscribers.items()},
            }


class InMemoryKlineRollingCache:
    """Maintains a rolling 100-bar 1h OHLC cache refreshed periodically via REST,
    while synthesizing the live unclosed bar in memory on every incoming WebSocket tick.
    """

    def __init__(
        self,
        kline_fetcher: Callable[[str, str], Dict[str, List[float]]],
        refresh_interval_sec: float = 60.0,
    ):
        self._kline_fetcher = kline_fetcher
        self._refresh_interval_sec = refresh_interval_sec
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(symbol: str, market_type: str) -> str:
        clean_sym = symbol.replace("-", "/").replace("_", "/").upper()
        return f"{clean_sym}:{market_type.upper()}"

    def refresh_if_needed(self, symbol: str, market_type: str, force: bool = False) -> Dict[str, List[float]]:
        """Fetch historical 1h OHLC bars via REST only if cache is missing or expired."""
        key = self._key(symbol, market_type)
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if (
                not force
                and entry is not None
                and (now - entry.get("fetched_at", 0.0) < self._refresh_interval_sec)
                and entry.get("closes")
            ):
                return entry

        fetched = self._kline_fetcher(symbol, market_type) or {}
        closes = list(fetched.get("closes", []))
        highs = list(fetched.get("highs", closes))
        lows = list(fetched.get("lows", closes))

        with self._lock:
            entry = {
                "closes": closes,
                "highs": highs if len(highs) == len(closes) else list(closes),
                "lows": lows if len(lows) == len(closes) else list(closes),
                "fetched_at": now,
            }
            self._cache[key] = entry
            return entry

    def compute_signals_on_tick(
        self,
        symbol: str,
        market_type: str,
        price: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update the latest bar's close/high/low in memory and compute structural indicators with zero extra REST calls."""
        from packages.core.autopilot_engine import compute_structural_indicators_from_ohlc

        entry = self.refresh_if_needed(symbol, market_type)
        with self._lock:
            closes = list(entry.get("closes", []))
            highs = list(entry.get("highs", []))
            lows = list(entry.get("lows", []))

            if closes:
                closes[-1] = price
                highs[-1] = max(highs[-1], price)
                lows[-1] = min(lows[-1], price)
                entry["closes"][-1] = price
                entry["highs"][-1] = highs[-1]
                entry["lows"][-1] = lows[-1]
            else:
                closes = [price]
                highs = [price]
                lows = [price]

        return compute_structural_indicators_from_ohlc(
            closes=closes,
            highs=highs,
            lows=lows,
            cur_price=price,
            bid=bid if bid is not None else price,
            ask=ask if ask is not None else price,
        )
