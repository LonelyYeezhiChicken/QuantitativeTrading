"""Pionex Broker Gateway: High-level exchange gateway conforming to BaseBrokerGateway."""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from packages.execution.base import BaseBrokerGateway
from packages.execution.pionex_client import PionexClient

class PionexGateway(BaseBrokerGateway):
    """High-level Pionex execution gateway with Dry-Run safety mechanisms."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://api.pionex.com",
        dry_run: bool = True,  # Default to True for maximum safety
    ):
        # Allow loading credentials from environment variables if not passed explicitly
        self.api_key = api_key or os.getenv("PIONEX_API_KEY", "")
        self.api_secret = api_secret or os.getenv("PIONEX_API_SECRET", "")
        self._dry_run = dry_run
        
        self.client = PionexClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            base_url=base_url,
        )

        # In-memory simulated state when running in dry_run mode
        self._simulated_cash = 10000.0
        self._simulated_positions: Dict[str, float] = {}
        self._simulated_orders: List[Dict] = []

    @property
    def exchange_name(self) -> str:
        return "Pionex"

    @property
    def is_dry_run(self) -> bool:
        return self._dry_run

    @staticmethod
    def to_pionex_symbol(symbol: str) -> str:
        """Convert standard 'BTC/USDT' to Pionex 'BTC_USDT' format."""
        return symbol.replace("/", "_").replace(":", "_").upper()

    @staticmethod
    def from_pionex_symbol(symbol: str) -> str:
        """Convert Pionex 'BTC_USDT' to standard 'BTC/USDT'."""
        return symbol.replace("_", "/").upper()

    def fetch_ticker(self, symbol: str, market_type: Optional[str] = None) -> Dict[str, float]:
        """Fetch current ticker price from Pionex public market endpoint."""
        p_symbol = self.to_pionex_symbol(symbol)
        resp = self.client.get_market_tickers(symbol=p_symbol)

        if resp.get("result") and resp.get("data") and resp["data"].get("tickers"):
            ticker = resp["data"]["tickers"][0]
            price = float(ticker.get("close", 0.0))
            bid = float(ticker.get("bid", price))
            ask = float(ticker.get("ask", price))
            return {
                "price": price,
                "bid": bid,
                "ask": ask,
                "timestamp": int(ticker.get("time", int(datetime.now(timezone.utc).timestamp() * 1000))),
            }

        # Fallback or offline check
        return {"price": 0.0, "bid": 0.0, "ask": 0.0, "timestamp": 0}

    def get_balance(self, asset: str = "USDT", market_type: Optional[str] = None) -> float:
        """Get available balance of an asset (USDT, BTC, ETH, etc.)."""
        asset_clean = asset.upper()

        if self.is_dry_run or not self.api_key:
            # Return simulated balance in dry run mode
            if asset_clean == "USDT":
                return self._simulated_cash
            return self._simulated_positions.get(asset_clean, 0.0)

        resp = self.client.get_account_balances()
        if resp.get("result") and resp.get("data") and resp["data"].get("balances"):
            for item in resp["data"]["balances"]:
                if item.get("coin", "").upper() == asset_clean:
                    return float(item.get("free", 0.0))
        return 0.0

    def create_order(
        self,
        symbol: str,
        side: str,          # 'BUY' or 'SELL'
        order_type: str,    # 'LIMIT' or 'MARKET'
        size: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        market_type: Optional[str] = None,
        position_side: str = "LONG",
        leverage: int = 1,
        **kwargs,
    ) -> Dict:
        """Submit an order to Pionex (safely simulated if dry_run=True)."""
        p_symbol = self.to_pionex_symbol(symbol)
        side_clean = side.upper()
        type_clean = order_type.upper()

        if self.is_dry_run or not self.api_key:
            # Dry run execution: simulate order execution
            ticker = self.fetch_ticker(symbol)
            exec_price = price if (type_clean == "LIMIT" and price) else ticker.get("price", 50000.0)

            sim_order_id = f"DRY_RUN_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            order_record = {
                "order_id": sim_order_id,
                "client_order_id": client_order_id or sim_order_id,
                "symbol": symbol,
                "pionex_symbol": p_symbol,
                "side": side_clean,
                "type": type_clean,
                "size": size,
                "price": exec_price,
                "status": "FILLED",
                "is_dry_run": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._simulated_orders.append(order_record)
            return {
                "result": True,
                "data": order_record,
                "message": "Order executed in DRY_RUN mode (No real funds deducted).",
            }

        # Real Live Execution on Pionex
        return self.client.create_order(
            symbol=p_symbol,
            side=side_clean,
            order_type=type_clean,
            size=size,
            price=price,
            client_order_id=client_order_id,
        )

    def cancel_order(self, symbol: str, order_id: str, market_type: Optional[str] = None) -> bool:
        """Cancel an open order."""
        p_symbol = self.to_pionex_symbol(symbol)

        if self.is_dry_run or not self.api_key:
            # Simulated cancellation
            return True

        resp = self.client.cancel_order(symbol=p_symbol, order_id=order_id)
        return bool(resp.get("result", False))

    def get_open_orders(self, symbol: str, market_type: Optional[str] = None) -> List[Dict]:
        """Fetch open orders for symbol."""
        p_symbol = self.to_pionex_symbol(symbol)

        if self.is_dry_run or not self.api_key:
            return [o for o in self._simulated_orders if o.get("status") == "OPEN"]

        resp = self.client.get_open_orders(symbol=p_symbol)
        if resp.get("result") and resp.get("data") and resp["data"].get("orders"):
            return resp["data"]["orders"]
        return []
