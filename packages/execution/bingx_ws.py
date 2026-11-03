"""BingX WebSocket Client for Real-Time Market Data Streaming (SPOT & SWAP).

Features:
- Dual-channel support: Spot (wss://open-api-ws.bingx.com/market) and Swap (wss://open-api-swap.bingx.com/swap-market)
- GZIP binary decompression
- Automated Ping/Pong heartbeat response
- Multi-symbol streaming: BTC-USDT, ETH-USDT, SOL-USDT, XAUT-USDT
- Thread-safe memory cache for instant, zero-latency price retrieval
- Exponential backoff automatic reconnection
"""

import asyncio
import gzip
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List

import websockets

logger = logging.getLogger(__name__)

SPOT_WS_URL = "wss://open-api-ws.bingx.com/market"
SWAP_WS_URL = "wss://open-api-swap.bingx.com/swap-market"

DEFAULT_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "XAUT-USDT"]


class BingXWebSocketClient:
    """Manages real-time WebSocket market data connections to BingX."""

    _instance: Optional["BingXWebSocketClient"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, symbols: Optional[List[str]] = None) -> "BingXWebSocketClient":
        """Singleton accessor for shared background WebSocket client."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(symbols=symbols)
                cls._instance.start()
            return cls._instance

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = [s.replace("/", "-").upper() for s in (symbols or DEFAULT_SYMBOLS)]
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._spot_connected = False
        self._swap_connected = False
        self._last_ping_time = time.time()

    def start(self):
        """Start WebSocket worker thread in background."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="BingX-WS-Worker")
        self._thread.start()

    def stop(self):
        """Stop WebSocket connections."""
        self._running = False

    def is_connected(self) -> bool:
        """True if either Spot or Swap connection is actively streaming."""
        return self._spot_connected or self._swap_connected

    def get_status(self) -> Dict[str, Any]:
        """Get connection diagnostic status."""
        return {
            "spot_connected": self._spot_connected,
            "swap_connected": self._swap_connected,
            "cached_symbols_count": len(self._cache),
            "is_running": self._running,
        }

    def get_ticker(self, symbol: str, market_type: str = "SPOT") -> Optional[Dict[str, Any]]:
        """Retrieve latest ticker from cache if fresh (within 15s)."""
        clean_sym = symbol.replace("/", "-").replace("_", "-").upper()
        cache_key = f"{clean_sym}:{market_type.upper()}"
        with self._cache_lock:
            data = self._cache.get(cache_key)
            if data and (time.time() - data.get("local_timestamp", 0) < 15.0):
                return data
        return None

    def get_all_tickers(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve copy of all currently cached tickers."""
        with self._cache_lock:
            return dict(self._cache)

    def _update_cache(self, symbol: str, market_type: str, data: Dict[str, Any]):
        """Thread-safe update of ticker cache."""
        clean_sym = symbol.replace("/", "-").upper()
        cache_key = f"{clean_sym}:{market_type.upper()}"
        data["local_timestamp"] = time.time()
        with self._cache_lock:
            self._cache[cache_key] = data

    def _run_event_loop(self):
        """Run asyncio event loop in dedicated background thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                asyncio.gather(
                    self._maintain_connection(SPOT_WS_URL, "SPOT"),
                    self._maintain_connection(SWAP_WS_URL, "SWAP"),
                )
            )
        except Exception as e:
            logger.warning(f"BingX WebSocket event loop exited: {e}")
        finally:
            loop.close()

    async def _maintain_connection(self, url: str, market_type: str):
        """Connection lifecycle manager with exponential backoff."""
        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=None,  # BingX uses custom application-layer Ping/Pong
                    ping_timeout=None,
                    close_timeout=5,
                ) as ws:
                    if market_type == "SPOT":
                        self._spot_connected = True
                    else:
                        self._swap_connected = True
                    backoff = 1.0

                    # Subscribe to ticker and lastPrice channels for all symbols
                    for sym in self.symbols:
                        # Ticker channel
                        sub_ticker = {
                            "id": f"sub_{market_type.lower()}_{sym}_ticker",
                            "reqType": "sub",
                            "dataType": f"{sym}@ticker",
                        }
                        await ws.send(json.dumps(sub_ticker))

                        # LastPrice channel
                        sub_last = {
                            "id": f"sub_{market_type.lower()}_{sym}_last",
                            "reqType": "sub",
                            "dataType": f"{sym}@lastPrice",
                        }
                        await ws.send(json.dumps(sub_last))
                        await asyncio.sleep(0.05)

                    # Ingestion loop
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=25.0)
                        except asyncio.TimeoutError:
                            # Send application ping if idle
                            try:
                                await ws.send("Ping")
                            except Exception:
                                break
                            continue

                        # Decompress GZIP binary message if needed
                        if isinstance(msg, bytes):
                            try:
                                text = gzip.decompress(msg).decode("utf-8")
                            except Exception:
                                continue
                        else:
                            text = str(msg)

                        # Handle BingX application-level heartbeat
                        if text == "Ping":
                            await ws.send("Pong")
                            self._last_ping_time = time.time()
                            continue
                        elif text == "Pong":
                            continue

                        # Parse JSON payload
                        try:
                            payload = json.loads(text)
                            self._process_message(payload, market_type)
                        except Exception:
                            continue

            except Exception as e:
                logger.debug(f"BingX WS [{market_type}] connection dropped ({e}), retrying in {backoff:.1f}s...")
            finally:
                if market_type == "SPOT":
                    self._spot_connected = False
                else:
                    self._swap_connected = False

            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)

    def _process_message(self, payload: Dict[str, Any], market_type: str):
        """Parse ticker or lastPrice update and update memory cache."""
        data_type = payload.get("dataType", "")
        data = payload.get("data")
        if not data or not isinstance(data, dict):
            return

        # Extract symbol from channel or payload
        raw_symbol = data.get("s", "")
        if not raw_symbol and "@" in data_type:
            raw_symbol = data_type.split("@")[0]

        if not raw_symbol:
            return

        clean_symbol = raw_symbol.replace("-", "/").upper()

        # Handle 24h Ticker data
        if "ticker" in data_type.lower() or data.get("e") == "24hTicker":
            try:
                price = float(data.get("c", data.get("lastPrice", 0.0)))
                high_24h = float(data.get("h", data.get("highPrice", price)))
                low_24h = float(data.get("l", data.get("lowPrice", price)))
                bid = float(data.get("B", data.get("bidPrice", price)))
                ask = float(data.get("A", data.get("askPrice", price)))
                vol = float(data.get("v", data.get("volume", 0.0)))
                change_pct = float(str(data.get("P", data.get("priceChangePercent", "0.0"))).replace("%", ""))

                cached = {
                    "symbol": clean_symbol,
                    "market_type": market_type,
                    "price": price,
                    "bid": bid,
                    "ask": ask,
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "change_24h_pct": change_pct,
                    "volume_24h": vol,
                    "timestamp": int(data.get("E", data.get("time", time.time() * 1000))),
                }
                self._update_cache(clean_symbol, market_type, cached)
            except Exception:
                pass

        # Handle LastPrice data
        elif "lastprice" in data_type.lower() or data.get("e") == "lastPriceUpdate":
            try:
                price = float(data.get("c", 0.0))
                if price > 0:
                    cache_key = f"{clean_symbol.replace('/', '-')}:{market_type.upper()}"
                    with self._cache_lock:
                        existing = self._cache.get(cache_key, {})
                        existing["symbol"] = clean_symbol
                        existing["market_type"] = market_type
                        existing["price"] = price
                        existing["local_timestamp"] = time.time()
                        self._cache[cache_key] = existing
            except Exception:
                pass
