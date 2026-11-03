"""BingX Official OpenAPI REST Client with HMAC-SHA256 Authentication and Multi-Domain Fallback."""

import hashlib
import hmac
import re
import time
from typing import Any, Dict, List, Optional
import requests


class BingXClient:
    """Low-level REST client communicating directly with BingX OpenAPI (v1/v2).

    Conforms to the official BingX AI Skill specifications:
    - Primary domain: https://open-api.bingx.com
    - Fallback domain: https://open-api.bingx.pro (for timeout or network errors)
    - Custom header: X-SOURCE-KEY: BX-AI-SKILL
    - HMAC-SHA256 parameter sorting in ascending alphabetical order
    """

    BASE_URLS = [
        "https://open-api.bingx.com",
        "https://open-api.bingx.pro",
    ]

    FORBIDDEN_PARAM_CHARS = re.compile(r"[&=?#\r\n]")

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_urls: Optional[List[str]] = None,
        timeout: int = 10,
    ):
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_urls = [u.rstrip("/") for u in (base_urls or self.BASE_URLS)]
        self.timeout = timeout
        self.session = requests.Session()

    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate parameter values to prevent injection and malformed query strings."""
        for k, v in params.items():
            s = str(v)
            if self.FORBIDDEN_PARAM_CHARS.search(s):
                raise ValueError(f"Param '{k}' contains forbidden characters in value: '{s}'")

    def sign_params(self, params: Dict[str, Any]) -> tuple[str, str, str]:
        """Sign request parameters using HMAC-SHA256.

        Steps:
        1. Inject millisecond timestamp if not present.
        2. Validate parameter constraints.
        3. Sort query parameter keys in ascending ASCII alphabetical order.
        4. Compute HMAC-SHA256 hex digest using secret key.
        5. Return (query_string, signature_hex, signed_payload).
        """
        all_params = dict(params)
        if "timestamp" not in all_params:
            all_params["timestamp"] = int(time.time() * 1000)

        self.validate_params(all_params)

        sorted_keys = sorted(all_params.keys())
        query_string = "&".join(f"{k}={all_params[k]}" for k in sorted_keys)

        signature_hex = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        signed_payload = f"{query_string}&signature={signature_hex}"
        return query_string, signature_hex, signed_payload

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        is_private: bool = False,
    ) -> Dict[str, Any]:
        """Execute HTTP request with multi-domain fallback and optional HMAC authentication.

        Domain priority: open-api.bingx.com -> open-api.bingx.pro.
        """
        method = method.upper()
        req_params = dict(params) if params else {}

        headers: Dict[str, str] = {
            "X-SOURCE-KEY": "BX-AI-SKILL",
            "User-Agent": "CryptoAIQuant/2.0 (BingXGateway)",
        }

        body_data: Optional[str] = None
        signed_qs: Optional[str] = None

        if is_private:
            if not self.api_key or not self.api_secret:
                raise ValueError("API Key and Secret Key are required for authenticated BingX endpoints.")
            headers["X-BX-APIKEY"] = self.api_key
            _, _, signed_qs = self.sign_params(req_params)
        else:
            if req_params:
                signed_qs = "&".join(f"{k}={req_params[k]}" for k in sorted(req_params.keys()))

        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body_data = signed_qs or ""

        last_exception: Optional[Exception] = None

        for idx, base in enumerate(self.base_urls):
            is_last = idx == (len(self.base_urls) - 1)
            try:
                if method == "POST":
                    url = f"{base}{path}"
                    resp = self.session.post(
                        url,
                        data=body_data,
                        headers=headers,
                        timeout=self.timeout,
                    )
                elif method == "DELETE":
                    url = f"{base}{path}?{signed_qs}" if signed_qs else f"{base}{path}"
                    resp = self.session.delete(
                        url,
                        headers=headers,
                        timeout=self.timeout,
                    )
                else:  # GET
                    url = f"{base}{path}?{signed_qs}" if signed_qs else f"{base}{path}"
                    resp = self.session.get(
                        url,
                        headers=headers,
                        timeout=self.timeout,
                    )

                resp.raise_for_status()
                data = resp.json()

                # BingX success code is 0
                if isinstance(data, dict) and data.get("code") not in (0, None):
                    raise RuntimeError(f"BingX API Error {data.get('code')}: {data.get('msg')}")

                return data

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                if is_last:
                    raise RuntimeError(f"All BingX domains failed. Last error: {e}") from e
                continue
            except Exception as e:
                raise

        raise RuntimeError(f"BingX request dispatch failed: {last_exception}")

    # ================= Public Market Data Endpoints =================

    def fetch_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest price ticker for a symbol (e.g. 'BTC-USDT').

        GET /openApi/spot/v1/ticker/price
        """
        return self.request(
            method="GET",
            path="/openApi/spot/v1/ticker/price",
            params={"symbol": symbol},
            is_private=False,
        )

    def fetch_book_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch best order book bid/ask ticker for a symbol.

        GET /openApi/spot/v1/ticker/bookTicker
        """
        return self.request(
            method="GET",
            path="/openApi/spot/v1/ticker/bookTicker",
            params={"symbol": symbol},
            is_private=False,
        )

    def fetch_depth(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Fetch order book depth.

        GET /openApi/spot/v1/market/depth
        """
        return self.request(
            method="GET",
            path="/openApi/spot/v1/market/depth",
            params={"symbol": symbol, "limit": limit},
            is_private=False,
        )

    def fetch_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """Fetch candlestick / Kline data.

        GET /openApi/spot/v2/market/kline
        """
        return self.request(
            method="GET",
            path="/openApi/spot/v2/market/kline",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            is_private=False,
        )

    # ================= Authenticated Account & Trade Endpoints =================

    def get_account_balance(self) -> Dict[str, Any]:
        """Fetch current spot account balance.

        GET /openApi/spot/v1/account/balance
        """
        return self.request(
            method="GET",
            path="/openApi/spot/v1/account/balance",
            is_private=True,
        )

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        quote_order_qty: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a spot order.

        POST /openApi/spot/v1/trade/order
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
        }

        if quote_order_qty is not None and quote_order_qty > 0:
            params["quoteOrderQty"] = quote_order_qty
        elif quantity > 0:
            params["quantity"] = quantity

        if price is not None and price > 0:
            params["price"] = price

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        if order_type.upper() == "LIMIT":
            params.setdefault("timeInForce", "GTC")

        return self.request(
            method="POST",
            path="/openApi/spot/v1/trade/order",
            params=params,
            is_private=True,
        )

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an open spot order.

        POST /openApi/spot/v1/trade/cancel
        """
        params: Dict[str, Any] = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["clientOrderID"] = client_order_id

        return self.request(
            method="POST",
            path="/openApi/spot/v1/trade/cancel",
            params=params,
            is_private=True,
        )

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Query current open orders.

        GET /openApi/spot/v1/trade/openOrders
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        return self.request(
            method="GET",
            path="/openApi/spot/v1/trade/openOrders",
            params=params,
            is_private=True,
        )

    # ================= Perpetual Swap (Futures) Endpoints =================

    def fetch_swap_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch perpetual swap ticker (price, 24h stats, mark price).

        GET /openApi/swap/v2/quote/ticker
        """
        return self.request(
            method="GET",
            path="/openApi/swap/v2/quote/ticker",
            params={"symbol": symbol},
            is_private=False,
        )

    def fetch_swap_depth(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Fetch perpetual swap order book depth.

        GET /openApi/swap/v2/quote/depth
        """
        return self.request(
            method="GET",
            path="/openApi/swap/v2/quote/depth",
            params={"symbol": symbol, "limit": limit},
            is_private=False,
        )

    def fetch_swap_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """Fetch perpetual swap candlestick / Kline data.

        GET /openApi/swap/v3/quote/klines
        """
        return self.request(
            method="GET",
            path="/openApi/swap/v3/quote/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            is_private=False,
        )

    def get_swap_balance(self) -> Dict[str, Any]:
        """Fetch perpetual swap account balance, equity, and margin info.

        GET /openApi/swap/v3/user/balance
        """
        return self.request(
            method="GET",
            path="/openApi/swap/v3/user/balance",
            is_private=True,
        )

    def get_swap_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch current open swap positions with PnL, leverage, and liquidation price.

        GET /openApi/swap/v2/user/positions
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        return self.request(
            method="GET",
            path="/openApi/swap/v2/user/positions",
            params=params,
            is_private=True,
        )

    def create_swap_order(
        self,
        symbol: str,
        side: str,                            # 'BUY' or 'SELL'
        position_side: str,                   # 'LONG' or 'SHORT' or 'BOTH'
        order_type: str,                      # 'LIMIT' or 'MARKET'
        quantity: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a perpetual swap order (supports LONG / SHORT).

        POST /openApi/swap/v2/trade/order
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "positionSide": position_side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }

        if price is not None and price > 0:
            params["price"] = price

        if client_order_id:
            params["clientOrderId"] = client_order_id

        if order_type.upper() == "LIMIT":
            params.setdefault("timeInForce", "GTC")

        return self.request(
            method="POST",
            path="/openApi/swap/v2/trade/order",
            params=params,
            is_private=True,
        )

    def cancel_swap_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an open swap order.

        DELETE /openApi/swap/v2/trade/order
        """
        params: Dict[str, Any] = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_order_id:
            params["clientOrderId"] = client_order_id

        return self.request(
            method="DELETE",
            path="/openApi/swap/v2/trade/order",
            params=params,
            is_private=True,
        )

    def set_swap_leverage(self, symbol: str, leverage: int, side: str = "BOTH") -> Dict[str, Any]:
        """Set leverage for a perpetual swap contract.

        POST /openApi/swap/v2/trade/leverage
        """
        return self.request(
            method="POST",
            path="/openApi/swap/v2/trade/leverage",
            params={"symbol": symbol, "leverage": leverage, "side": side},
            is_private=True,
        )

    def set_swap_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> Dict[str, Any]:
        """Set margin type ('ISOLATED' or 'CROSSED') for a swap contract.

        POST /openApi/swap/v2/trade/marginType
        """
        return self.request(
            method="POST",
            path="/openApi/swap/v2/trade/marginType",
            params={"symbol": symbol, "marginType": margin_type.upper()},
            is_private=True,
        )
