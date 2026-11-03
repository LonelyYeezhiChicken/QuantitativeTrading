"""Pionex Official OpenAPI REST Client with HMAC-SHA256 Authentication."""

import hashlib
import hmac
import json
import time
from typing import Dict, List, Optional, Any
import requests

class PionexClient:
    """Low-level REST client communicating directly with Pionex OpenAPI."""

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = "https://api.pionex.com",
        timeout: int = 15,
    ):
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def generate_signature(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> tuple[str, str]:
        """Generate official Pionex HMAC-SHA256 signature and full PATH_URL.
        
        Returns:
            (path_url, signature_hex)
        """
        # 1. Format and sort query parameters alphabetically
        query_string = ""
        if params:
            sorted_params = sorted(params.items(), key=lambda x: str(x[0]))
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])

        # 2. Build PATH_URL
        path_url = f"{endpoint}?{query_string}" if query_string else endpoint

        # 3. Prepend HTTP method in uppercase
        signature_payload = f"{method.upper()}{path_url}"

        # 4. Append compact JSON body for POST / DELETE
        if method.upper() in ["POST", "DELETE"] and body:
            signature_payload += json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        # 5. Generate HMAC-SHA256 hex digest
        signature_hex = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return path_url, signature_hex

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        is_private: bool = False,
    ) -> Dict:
        """Execute HTTP request with optional authentication."""
        params = params.copy() if params else {}

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CryptoAIQuant/2.0 (PionexGateway)",
        }

        if is_private:
            if not self.api_key or not self.api_secret:
                raise ValueError("API Key and Secret are required for private Pionex requests.")

            # Required millisecond timestamp
            params["timestamp"] = int(time.time() * 1000)

            path_url, signature = self.generate_signature(method, endpoint, params=params, body=body)
            headers["PIONEX-KEY"] = self.api_key
            headers["PIONEX-SIGNATURE"] = signature
            full_url = f"{self.base_url}{path_url}"
        else:
            query_str = "&".join([f"{k}={v}" for k, v in params.items()]) if params else ""
            full_url = f"{self.base_url}{endpoint}?{query_str}" if query_str else f"{self.base_url}{endpoint}"

        try:
            if method.upper() == "GET":
                resp = self.session.get(full_url, headers=headers, timeout=self.timeout)
            elif method.upper() == "POST":
                resp = self.session.post(full_url, headers=headers, json=body, timeout=self.timeout)
            elif method.upper() == "DELETE":
                resp = self.session.delete(full_url, headers=headers, json=body, timeout=self.timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            data = resp.json()
            return data
        except Exception as e:
            return {
                "result": False,
                "message": f"HTTP Request Error: {str(e)}",
                "data": None,
            }

    # ================= PUBLIC MARKET ENDPOINTS =================

    INTERVAL_MAP = {
        "1m": "1M",
        "5m": "5M",
        "15m": "15M",
        "30m": "30M",
        "1h": "60M",
        "60m": "60M",
        "4h": "4H",
        "12h": "12H",
        "1d": "1D",
    }

    def get_server_time(self) -> Dict:
        """Get Pionex server timestamp (ms)."""
        res = self.get_market_tickers(symbol="BTC_USDT")
        if res.get("timestamp"):
            return {"result": True, "data": {"timestamp": res["timestamp"]}}
        return res

    def get_market_tickers(self, symbol: Optional[str] = None) -> Dict:
        """Get current ticker price for a symbol or all symbols."""
        params = {"symbol": symbol} if symbol else {}
        return self.request("GET", "/api/v1/market/tickers", params=params, is_private=False)

    def get_market_depth(self, symbol: str, limit: int = 20) -> Dict:
        """Get order book depth."""
        params = {"symbol": symbol, "limit": limit}
        return self.request("GET", "/api/v1/market/depth", params=params, is_private=False)

    def get_market_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        end_time: Optional[int] = None,
    ) -> Dict:
        """Get historical K-line candles (intervals: 1m, 5m, 15m, 1h, 4h, 1d)."""
        mapped_interval = self.INTERVAL_MAP.get(interval.lower(), interval.upper())
        params = {"symbol": symbol, "interval": mapped_interval, "limit": limit}
        if end_time:
            params["endTime"] = end_time
        return self.request("GET", "/api/v1/market/klines", params=params, is_private=False)

    # ================= PRIVATE ACCOUNT & TRADE ENDPOINTS =================

    def get_account_balances(self) -> Dict:
        """Get asset balances (free and frozen)."""
        return self.request("GET", "/api/v1/account/balances", is_private=True)

    def create_order(
        self,
        symbol: str,
        side: str,          # 'BUY' or 'SELL'
        order_type: str,    # 'LIMIT' or 'MARKET'
        size: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict:
        """Place an order on Pionex."""
        body = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "size": str(size),
        }
        if price is not None and order_type.upper() == "LIMIT":
            body["price"] = str(price)
        if client_order_id:
            body["clientOrderId"] = client_order_id

        return self.request("POST", "/api/v1/trade/order", body=body, is_private=True)

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict:
        """Cancel an open order by ID."""
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = str(order_id)
        if client_order_id:
            params["clientOrderId"] = client_order_id

        return self.request("DELETE", "/api/v1/trade/order", params=params, is_private=True)

    def get_open_orders(self, symbol: str) -> Dict:
        """Query active open orders for symbol."""
        return self.request("GET", "/api/v1/trade/openOrders", params={"symbol": symbol}, is_private=True)
