"""BingX Broker Gateway: High-level exchange gateway conforming to BaseBrokerGateway."""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from packages.execution.base import BaseBrokerGateway, MarketType
from packages.execution.bingx_client import BingXClient
from packages.execution.bingx_ws import BingXWebSocketClient
from packages.execution.precision import (
    decimals_from_step,
    fallback_price_decimals,
    floor_quantity,
    round_price,
)

load_dotenv()


class BingXGateway(BaseBrokerGateway):
    """High-level BingX execution gateway with Dry-Run safety mechanisms.

    Conforms to BaseBrokerGateway. Supports both SPOT and SWAP (Perpetual Futures)
    markets with seamless safety verification and dry-run execution.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_urls: Optional[List[str]] = None,
        dry_run: bool = True,  # Default to True for maximum safety
        use_vst: bool = False, # True to route to BingX official VST simulation server
        default_market_type: str = MarketType.SPOT.value,
        enable_ws: bool = True,
    ):
        self.api_key = api_key or os.getenv("BINGX_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BINGX_API_SECRET", "")
        self._dry_run = dry_run
        self._use_vst = use_vst or (os.getenv("BINGX_USE_VST", "false").lower() in ("true", "1"))
        self._default_market_type = default_market_type.upper()
        self._enable_ws = enable_ws
        self._ws_client: Optional[BingXWebSocketClient] = None
        if enable_ws:
            try:
                self._ws_client = BingXWebSocketClient.get_instance()
            except Exception:
                self._ws_client = None

        self.client = BingXClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            base_urls=base_urls,
            use_vst=self._use_vst,
        )

        # In-memory simulated SPOT state
        self._simulated_cash = 10000.0
        self._simulated_positions: Dict[str, float] = {}
        self._simulated_orders: List[Dict[str, Any]] = []

        # In-memory simulated SWAP (Futures) state
        self._simulated_swap_margin = 10000.0  # USDT margin balance
        self._simulated_swap_positions: Dict[str, Dict[str, Any]] = {}
        self._leverage_map: Dict[str, int] = {}
        # (bx_symbol, market_type) -> (price_decimals, qty_decimals); None = unknown
        self._precision_cache: Dict[tuple, tuple] = {}

    # ----------------- Exchange precision -----------------

    def get_precision(self, symbol: str, market_type: Optional[str] = None) -> tuple:
        """Return (price_decimals, qty_decimals) from exchange rules, (None, None) if unknown.

        Fetched once per symbol for exchange-backed gateways; the local dry-run simulator
        never hits the network for this and uses the significant-digit fallback.
        """
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)
        key = (bx_symbol, m_type)
        if key in self._precision_cache:
            return self._precision_cache[key]
        if self.is_dry_run:
            return (None, None)

        result: tuple = (None, None)
        try:
            if m_type == MarketType.SWAP.value:
                data = self.client.fetch_swap_contracts(bx_symbol).get("data", [])
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and str(item.get("symbol", "")).upper() == bx_symbol:
                        result = (int(item["pricePrecision"]), int(item["quantityPrecision"]))
                        break
            else:
                data = self.client.fetch_spot_symbols(bx_symbol).get("data", {})
                items = data.get("symbols", []) if isinstance(data, dict) else data
                for item in items or []:
                    if isinstance(item, dict) and str(item.get("symbol", "")).upper() == bx_symbol:
                        result = (decimals_from_step(item.get("tickSize")), decimals_from_step(item.get("stepSize")))
                        break
        except Exception:
            return (None, None)  # transient: do not cache, retry next time
        self._precision_cache[key] = result
        return result

    def round_price(self, symbol: str, price: float, market_type: Optional[str] = None) -> float:
        """Round a trigger / limit price to the symbol's tick precision (any price magnitude)."""
        price_dec, _ = self.get_precision(symbol, market_type)
        return round_price(price, price_dec if price_dec is not None else fallback_price_decimals(price))

    def floor_quantity(self, symbol: str, quantity: float, market_type: Optional[str] = None) -> float:
        """Round an order quantity down to the symbol's step precision."""
        _, qty_dec = self.get_precision(symbol, market_type)
        return floor_quantity(quantity, qty_dec)

    @property
    def exchange_name(self) -> str:
        return "BingX"

    @property
    def is_vst(self) -> bool:
        """True if operating against BingX official VST simulation server."""
        return self._use_vst

    @property
    def is_dry_run(self) -> bool:
        """True if operating in purely local simulated mode (no external network orders)."""
        return self._dry_run and not self._use_vst

    @property
    def default_market_type(self) -> str:
        return self._default_market_type

    @property
    def is_ws_connected(self) -> bool:
        """True if real-time WebSocket stream is active."""
        return self._ws_client.is_connected() if self._ws_client else False

    @property
    def ws_client(self) -> Optional[BingXWebSocketClient]:
        """Accessor for underlying WebSocket client."""
        return self._ws_client

    @property
    def supports_websocket(self) -> bool:
        """BingX natively provides real-time WebSocket streams for both SPOT and SWAP."""
        return True

    def create_market_feed(
        self,
        event_bus: Any,
        symbols: List[str],
        market_type: Optional[str] = None,
        poll_interval_sec: float = 5.0,
    ) -> Any:
        """Return a HybridWebSocketFeedAdapter (WebSocket push primary + REST polling fallback)."""
        from packages.execution.market_feed import HybridWebSocketFeedAdapter

        return HybridWebSocketFeedAdapter(
            gateway=self,
            event_bus=event_bus,
            symbols=symbols,
            market_type=market_type or self.default_market_type,
            fallback_poll_interval_sec=poll_interval_sec,
        )

    @staticmethod
    def to_bingx_symbol(symbol: str) -> str:
        """Convert standard 'BTC/USDT' or 'BTC_USDT' to BingX 'BTC-USDT' format."""
        return symbol.replace("/", "-").replace("_", "-").replace(":", "-").upper()

    @staticmethod
    def from_bingx_symbol(symbol: str) -> str:
        """Convert BingX 'BTC-USDT' to standard 'BTC/USDT'."""
        return symbol.replace("-", "/").upper()

    def fetch_ticker(self, symbol: str, market_type: Optional[str] = None) -> Dict[str, float]:
        """Fetch current ticker price from BingX (prioritizes real-time WebSocket, falls back to REST)."""
        m_type = (market_type or self.default_market_type).upper()

        # 1. Fast-path: Check real-time WebSocket memory cache (< 1ms latency)
        if self._ws_client:
            cached = self._ws_client.get_ticker(symbol, m_type)
            if cached and cached.get("price", 0.0) > 0:
                p = cached["price"]
                return {
                    "price": p,
                    "bid": cached.get("bid", p),
                    "ask": cached.get("ask", p),
                    "high_24h": cached.get("high_24h", p),
                    "low_24h": cached.get("low_24h", p),
                    "change_24h_pct": cached.get("change_24h_pct", 0.0),
                    "volume_24h": cached.get("volume_24h", 0.0),
                    "timestamp": cached.get("timestamp", int(datetime.now(timezone.utc).timestamp() * 1000)),
                    "source": "WEBSOCKET",
                }

        # 2. Fallback path: REST API query
        bx_symbol = self.to_bingx_symbol(symbol)
        price = 0.0
        bid = 0.0
        ask = 0.0
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)

        if m_type == MarketType.SWAP.value:
            # Query Swap Ticker
            try:
                resp = self.client.fetch_swap_ticker(symbol=bx_symbol)
                data = resp.get("data")
                if isinstance(data, dict):
                    price = float(data.get("lastPrice", 0.0))
                    bid = float(data.get("bidPrice", price))
                    ask = float(data.get("askPrice", price))
                    ts = int(data.get("time", ts))
                elif isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    price = float(first.get("lastPrice", 0.0))
                    bid = float(first.get("bidPrice", price))
                    ask = float(first.get("askPrice", price))
                    ts = int(first.get("time", ts))
            except Exception:
                pass

            if price > 0:
                return {"price": price, "bid": bid, "ask": ask, "timestamp": ts}

        # SPOT (or fallback) Ticker
        # 1. Fetch latest price
        try:
            price_resp = self.client.fetch_ticker_price(symbol=bx_symbol)
            data = price_resp.get("data")
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    if "price" in first:
                        price = float(first["price"])
                    elif "trades" in first and isinstance(first["trades"], list) and len(first["trades"]) > 0:
                        price = float(first["trades"][0].get("price", 0.0))
            elif isinstance(data, dict):
                price = float(data.get("price", 0.0))
        except Exception:
            pass

        # 2. Fetch order book best bid/ask
        try:
            book_resp = self.client.fetch_book_ticker(symbol=bx_symbol)
            bdata = book_resp.get("data")
            first_b = bdata[0] if isinstance(bdata, list) and len(bdata) > 0 else (bdata if isinstance(bdata, dict) else {})
            if isinstance(first_b, dict):
                bid = float(first_b.get("bidPrice", price))
                ask = float(first_b.get("askPrice", price))
                if price == 0.0:
                    price = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else (bid or ask)
                ts = int(first_b.get("time", ts))
        except Exception:
            bid = price
            ask = price

        return {
            "price": price,
            "bid": bid,
            "ask": ask,
            "timestamp": ts,
        }

    def get_balance(self, asset: str = "USDT", market_type: Optional[str] = None) -> float:
        """Get available balance for SPOT asset or SWAP margin."""
        m_type = (market_type or self.default_market_type).upper()
        asset_clean = asset.upper()

        if m_type == MarketType.SWAP.value:
            if self.is_dry_run or not self.api_key:
                return self._simulated_swap_margin

            # Live/VST Swap Balance
            try:
                resp = self.client.get_swap_balance()
                data = resp.get("data", [])
                target_asset = "VST" if self.is_vst else asset_clean
                if isinstance(data, list):
                    for item in data:
                        coin = item.get("asset") or item.get("coin", "")
                        if str(coin).upper() == target_asset:
                            return float(item.get("availableMargin", item.get("balance", 0.0)))
                elif isinstance(data, dict):
                    balance_info = data.get("balance", data)
                    return float(balance_info.get("availableMargin", balance_info.get("balance", 0.0)))
            except Exception:
                pass
            return 0.0

        # SPOT Balance
        if self.is_dry_run or not self.api_key:
            if asset_clean == "USDT":
                return self._simulated_cash
            return self._simulated_positions.get(asset_clean, 0.0)

        resp = self.client.get_account_balance()
        data = resp.get("data", {})
        balances = data.get("balances", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

        for item in balances:
            coin = item.get("asset") or item.get("coin", "")
            if str(coin).upper() == asset_clean:
                return float(item.get("free", 0.0))

        return 0.0

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for perpetual swap contract."""
        bx_symbol = self.to_bingx_symbol(symbol)
        self._leverage_map[bx_symbol] = leverage

        if not self.is_dry_run and self.api_key:
            try:
                resp = self.client.set_swap_leverage(symbol=bx_symbol, leverage=leverage, side="ALL")
                return resp.get("code") == 0
            except Exception:
                return False
        return True

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve open perpetual swap contract positions."""
        bx_symbol = self.to_bingx_symbol(symbol) if symbol else None

        if self.is_dry_run:
            if bx_symbol:
                return [p for p in self._simulated_swap_positions.values() if p.get("symbol") == bx_symbol]
            return list(self._simulated_swap_positions.values())

        if self.api_key:
            resp = self.client.get_swap_positions(symbol=bx_symbol)
            data = resp.get("data", [])
            if isinstance(data, dict):
                data = data.get("positions", data.get("list", []))
            if not isinstance(data, list):
                raise RuntimeError("BingX returned an invalid positions payload")
            return data
        raise RuntimeError("BingX API credentials are unavailable; positions cannot be reconciled")

    def create_order(
        self,
        symbol: str,
        side: str,                            # 'BUY' or 'SELL'
        order_type: str,                      # 'LIMIT' or 'MARKET'
        size: float,                          # Base asset quantity (e.g. BTC amount)
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        market_type: Optional[str] = None,     # 'SPOT' or 'SWAP'
        position_side: str = "LONG",          # 'LONG' or 'SHORT' (for SWAP)
        leverage: Optional[int] = None,       # Leverage multiplier (for SWAP)
        stop_loss_price: Optional[float] = None,   # Native STOP_MARKET price on exchange
        take_profit_price: Optional[float] = None, # Native TAKE_PROFIT_MARKET price on exchange
        **kwargs,
    ) -> Dict[str, Any]:
        """Submit an order to BingX (supports SPOT and SWAP with atomic Native SL/TP)."""
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)
        side_clean = side.upper()
        type_clean = order_type.upper()
        # SPOT callers legitimately pass position_side=None (no hedge side on spot).
        pos_side = (position_side or "LONG").upper()

        actual_leverage = leverage or self._leverage_map.get(bx_symbol, 1)

        # ----------------- 1. SWAP (Perpetual Futures) Execution -----------------
        if m_type == MarketType.SWAP.value:
            if self.is_dry_run:
                simulation_price = kwargs.get("simulation_price")
                ticker = {} if simulation_price else self.fetch_ticker(symbol, market_type=MarketType.SWAP.value)
                fill_price = float(simulation_price or (price if type_clean == "LIMIT" else 0) or ticker.get("price", 0.0) or 50000.0)
                order_id = f"BINGX_SWAP_DRY_RUN_{uuid.uuid4().hex[:10].upper()}"
                pos_key = f"{bx_symbol}_{pos_side}"
                existing_pos = self._simulated_swap_positions.get(pos_key)

                closing_side = "SELL" if pos_side == "LONG" else "BUY"
                opening_side = "BUY" if pos_side == "LONG" else "SELL"
                if not existing_pos and side_clean != opening_side:
                    return {"result": False, "code": 400, "msg": "No simulated position exists to close"}
                if existing_pos and side_clean == closing_side:
                    current_size = float(existing_pos["positionAmt"])
                    if size > current_size + 1e-12:
                        return {"result": False, "code": 400, "msg": "Close quantity exceeds simulated position"}
                    close_size = min(size, current_size)
                    entry_price = float(existing_pos["entryPrice"])
                    if pos_side == "LONG":
                        realized_pnl = (fill_price - entry_price) * close_size
                    else:
                        realized_pnl = (entry_price - fill_price) * close_size
                    margin_release = float(existing_pos["initialMargin"]) * close_size / current_size
                    remaining_size = current_size - close_size
                    self._simulated_swap_margin += margin_release + realized_pnl
                    if remaining_size <= 1e-12:
                        self._simulated_swap_positions.pop(pos_key, None)
                    else:
                        existing_pos["positionAmt"] = remaining_size
                        existing_pos["initialMargin"] -= margin_release
                    order_record = {
                        "orderId": order_id,
                        "clientOrderId": client_order_id or f"dry_swap_{uuid.uuid4().hex[:8]}",
                        "symbol": bx_symbol,
                        "side": side_clean,
                        "positionSide": pos_side,
                        "type": type_clean,
                        "price": fill_price,
                        "avgPrice": fill_price,
                        "origQty": size,
                        "executedQty": close_size,
                        "realizedPnl": realized_pnl,
                        "status": "FILLED",
                        "time": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "is_dry_run": True,
                        "market_type": MarketType.SWAP.value,
                    }
                    self._simulated_orders.append(order_record)
                    return {"result": True, "code": 0, "data": order_record}

                notional = size * fill_price
                margin_required = notional / actual_leverage

                if self._simulated_swap_margin < margin_required:
                    return {
                        "result": False,
                        "code": 400,
                        "msg": f"Insufficient swap margin: required {margin_required:.2f} USDT, have {self._simulated_swap_margin:.2f} USDT",
                    }

                # Deduct initial margin
                self._simulated_swap_margin -= margin_required

                # Calculate estimated liquidation price (approximate 90% margin threshold)
                if pos_side == "LONG":
                    liq_price = fill_price * (1.0 - (1.0 / actual_leverage) * 0.9)
                else:  # SHORT
                    liq_price = fill_price * (1.0 + (1.0 / actual_leverage) * 0.9)

                existing_pos = self._simulated_swap_positions.get(pos_key, {
                    "symbol": bx_symbol,
                    "positionSide": pos_side,
                    "positionAmt": 0.0,
                    "entryPrice": fill_price,
                    "leverage": actual_leverage,
                    "initialMargin": 0.0,
                    "liquidationPrice": liq_price,
                    "unrealizedProfit": 0.0,
                    "stopLossPrice": stop_loss_price,
                })

                total_amt = existing_pos["positionAmt"] + size
                existing_pos["positionAmt"] = total_amt
                existing_pos["initialMargin"] += margin_required
                existing_pos["entryPrice"] = fill_price
                existing_pos["leverage"] = actual_leverage
                existing_pos["liquidationPrice"] = liq_price
                existing_pos["stopLossPrice"] = stop_loss_price

                self._simulated_swap_positions[pos_key] = existing_pos

                order_record = {
                    "orderId": order_id,
                    "clientOrderId": client_order_id or f"dry_swap_{uuid.uuid4().hex[:8]}",
                    "symbol": bx_symbol,
                    "side": side_clean,
                    "positionSide": pos_side,
                    "type": type_clean,
                    "price": fill_price,
                    "origQty": size,
                    "executedQty": size,
                    "leverage": actual_leverage,
                    "marginRequired": margin_required,
                    "stopLossPrice": stop_loss_price,
                    "takeProfitPrice": take_profit_price,
                    "status": "FILLED",
                    "time": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "is_dry_run": True,
                    "market_type": MarketType.SWAP.value,
                }
                self._simulated_orders.append(order_record)
                return {"result": True, "code": 0, "data": order_record}

            # Live or VST Swap Execution via BingX REST API with Atomic Native SL/TP
            clean_size = self.floor_quantity(symbol, size, MarketType.SWAP.value)
            if clean_size <= 0:
                return {"result": False, "code": 400, "msg": f"Order quantity {size} rounds to zero at exchange precision"}
            response = self.client.create_swap_order(
                symbol=bx_symbol,
                side=side_clean,
                position_side=pos_side,
                order_type=type_clean,
                quantity=clean_size,
                price=self.round_price(symbol, price, MarketType.SWAP.value) if price else price,
                client_order_id=client_order_id,
                stop_loss_price=self.round_price(symbol, stop_loss_price, MarketType.SWAP.value) if stop_loss_price else stop_loss_price,
                take_profit_price=self.round_price(symbol, take_profit_price, MarketType.SWAP.value) if take_profit_price else take_profit_price,
            )
            return self._normalize_order_response(response)

        # ----------------- 2. SPOT Execution -----------------
        if self.is_dry_run:
            simulation_price = kwargs.get("simulation_price")
            ticker = {} if simulation_price else self.fetch_ticker(symbol, market_type=MarketType.SPOT.value)
            fill_price = float(simulation_price or (price if type_clean == "LIMIT" else 0) or ticker.get("price", 0.0) or 50000.0)
            cost = size * fill_price
            order_id = f"BINGX_DRY_RUN_{uuid.uuid4().hex[:12].upper()}"

            base_asset = symbol.split("/")[0].split("-")[0].upper()
            if side_clean == "BUY":
                if self._simulated_cash >= cost:
                    self._simulated_cash -= cost
                    self._simulated_positions[base_asset] = self._simulated_positions.get(base_asset, 0.0) + size
                else:
                    return {
                        "result": False,
                        "code": 400,
                        "msg": f"Insufficient dry-run funds: required {cost:.2f} USDT, have {self._simulated_cash:.2f} USDT",
                    }
            elif side_clean == "SELL":
                current_qty = self._simulated_positions.get(base_asset, 0.0)
                if current_qty >= size:
                    self._simulated_positions[base_asset] -= size
                    self._simulated_cash += cost
                else:
                    return {
                        "result": False,
                        "code": 400,
                        "msg": f"Insufficient dry-run position: required {size} {base_asset}, have {current_qty}",
                    }

            order_record = {
                "orderId": order_id,
                "clientOrderID": client_order_id or f"dry_{uuid.uuid4().hex[:8]}",
                "symbol": bx_symbol,
                "side": side_clean,
                "type": type_clean,
                "price": fill_price,
                "origQty": size,
                "executedQty": size,
                "cummulativeQuoteQty": cost,
                "status": "FILLED",
                "time": int(datetime.now(timezone.utc).timestamp() * 1000),
                "is_dry_run": True,
                "market_type": MarketType.SPOT.value,
            }
            self._simulated_orders.append(order_record)
            return {"result": True, "code": 0, "data": order_record}

        # Live SPOT Execution
        spot_qty = self.floor_quantity(symbol, size, MarketType.SPOT.value)
        if spot_qty <= 0:
            return {"result": False, "code": 400, "msg": f"Order quantity {size} rounds to zero at exchange precision"}
        response = self.client.create_order(
            symbol=bx_symbol,
            side=side_clean,
            order_type=type_clean,
            quantity=spot_qty,
            price=self.round_price(symbol, price, MarketType.SPOT.value) if price else price,
            client_order_id=client_order_id,
        )
        return self._normalize_order_response(response)

    @staticmethod
    def _normalize_order_response(response: Dict[str, Any]) -> Dict[str, Any]:
        """Expose a consistent result flag while retaining the exchange payload."""
        if not isinstance(response, dict):
            return {"result": False, "msg": "Invalid exchange order response"}
        data = response.get("data")
        order_payload = data if isinstance(data, dict) else {}
        order_dict = order_payload.get("order") if isinstance(order_payload.get("order"), dict) else order_payload
        has_order_id = bool(order_dict.get("orderId")) or bool(order_payload.get("orderId"))
        accepted = response.get("code") == 0 and has_order_id
        return {**response, "result": bool(response.get("result", accepted))}

    def get_order(self, symbol: str, order_id: str, market_type: Optional[str] = None) -> Dict[str, Any]:
        """Query order status using the appropriate market endpoint."""
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)
        if self.is_dry_run:
            for order in self._simulated_orders:
                if str(order.get("orderId")) == str(order_id):
                    return {"result": True, "code": 0, "data": order}
            return {"result": False, "code": 404, "msg": "Simulated order not found"}
        response = (
            self.client.get_swap_order(bx_symbol, order_id)
            if m_type == MarketType.SWAP.value
            else self.client.get_order(bx_symbol, order_id)
        )
        return self._normalize_order_response(response)

    def cancel_order(self, symbol: str, order_id: str, market_type: Optional[str] = None) -> bool:
        """Cancel an open order."""
        m_type = (market_type or self.default_market_type).upper()
        if self.is_dry_run:
            for o in self._simulated_orders:
                if str(o.get("orderId")) == str(order_id):
                    o["status"] = "CANCELED"
                    return True
            return False

        bx_symbol = self.to_bingx_symbol(symbol)
        if m_type == MarketType.SWAP.value:
            resp = self.client.cancel_swap_order(symbol=bx_symbol, order_id=order_id)
            return resp.get("code") == 0

        resp = self.client.cancel_order(symbol=bx_symbol, order_id=order_id)
        return resp.get("code") == 0

    def cancel_all_orders(self, symbol: str, market_type: Optional[str] = None) -> bool:
        """Cancel all open orders and conditional orders for a symbol."""
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)
        if self.is_dry_run:
            for o in self._simulated_orders:
                if o.get("symbol") == bx_symbol and o.get("status") in ["NEW", "PENDING"]:
                    o["status"] = "CANCELED"
            return True

        if m_type == MarketType.SWAP.value:
            resp = self.client.cancel_all_swap_orders(symbol=bx_symbol)
            return resp.get("code") == 0
        return True

    def update_stop_loss_order(
        self,
        symbol: str,
        position_side: str,
        stop_price: float,
        quantity: float,
        old_sl_order_id: Optional[str] = None,
        market_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a new STOP_MARKET order on exchange, then cancel the previous one (Break-Even Sync).

        The new stop is placed FIRST so the position is never left without exchange-side
        protection; the old stop is only cancelled once the replacement is confirmed.
        """
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)
        pos_side = position_side.upper()
        clean_stop = self.round_price(symbol, stop_price, m_type)

        def _cancel_old() -> None:
            if old_sl_order_id:
                try:
                    self.cancel_order(symbol, str(old_sl_order_id), market_type=m_type)
                except Exception:
                    pass

        if self.is_dry_run or m_type != MarketType.SWAP.value:
            _cancel_old()
            pos_key = f"{bx_symbol}_{pos_side}"
            if pos_key in self._simulated_swap_positions:
                self._simulated_swap_positions[pos_key]["stopLossPrice"] = clean_stop
            order_id = f"BINGX_BE_SL_{uuid.uuid4().hex[:10].upper()}"
            order_record = {
                "orderId": order_id,
                "symbol": bx_symbol,
                "side": "SELL" if pos_side == "LONG" else "BUY",
                "positionSide": pos_side,
                "type": "STOP_MARKET",
                "stopPrice": clean_stop,
                "origQty": quantity,
                "status": "NEW",
                "is_dry_run": True,
                "market_type": m_type,
            }
            self._simulated_orders.append(order_record)
            return {"result": True, "code": 0, "data": order_record}

        try:
            resp = self.client.create_swap_stop_order(
                symbol=bx_symbol,
                position_side=pos_side,
                stop_price=clean_stop,
                quantity=self.floor_quantity(symbol, quantity, m_type),
            )
            normalized = self._normalize_order_response(resp)
        except Exception as e:
            return {"result": False, "msg": str(e)}
        if normalized.get("result"):
            _cancel_old()
        return normalized

    def get_open_orders(self, symbol: str, market_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve open orders."""
        m_type = (market_type or self.default_market_type).upper()
        bx_symbol = self.to_bingx_symbol(symbol)

        if self.is_dry_run:
            return [
                o for o in self._simulated_orders
                if o.get("symbol") == bx_symbol and o.get("status") in ["NEW", "PENDING", "PARTIALLY_FILLED"]
            ]

        if m_type == MarketType.SWAP.value:
            try:
                resp = self.client.request("GET", "/openApi/swap/v2/trade/openOrders", params={"symbol": bx_symbol}, is_private=True)
                data = resp.get("data", {})
                if isinstance(data, dict):
                    return data.get("orders", [])
                return data if isinstance(data, list) else []
            except Exception:
                return []

        resp = self.client.get_open_orders(symbol=bx_symbol)
        data = resp.get("data", [])
        if isinstance(data, dict):
            return data.get("orders", [])
        return data if isinstance(data, list) else []
