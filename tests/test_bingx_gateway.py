"""Unit tests for BingXGateway and BingXClient."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import BingXGateway, BingXClient


def test_symbol_normalization():
    """Verify bidirectional symbol translation."""
    assert BingXGateway.to_bingx_symbol("BTC/USDT") == "BTC-USDT"
    assert BingXGateway.to_bingx_symbol("ETH_USDT") == "ETH-USDT"
    assert BingXGateway.to_bingx_symbol("SOL:USDT") == "SOL-USDT"
    assert BingXGateway.from_bingx_symbol("BTC-USDT") == "BTC/USDT"


def test_param_validation():
    """Verify param injection detection."""
    client = BingXClient(api_key="k", api_secret="s")
    with pytest.raises(ValueError, match="forbidden characters"):
        client.validate_params({"symbol": "BTC-USDT&malicious=true"})


def test_domain_fallback():
    """Verify domain fallback from primary to secondary URL on connection error."""
    client = BingXClient(
        base_urls=["https://fake1.bingx.com", "https://fake2.bingx.com"],
        timeout=1,
    )

    call_counts = {"count": 0}

    def fake_get(url, *args, **kwargs):
        call_counts["count"] += 1
        if "fake1" in url:
            raise requests.exceptions.ConnectionError("Primary domain connection failed")
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        mock.json.return_value = {"code": 0, "msg": "SUCCESS", "data": {"price": "77000.0"}}
        return mock

    with patch.object(client.session, "get", side_effect=fake_get):
        res = client.request("GET", "/openApi/spot/v1/ticker/price")
        assert call_counts["count"] == 2
        assert res["code"] == 0
        assert res["data"]["price"] == "77000.0"


def test_dry_run_buy_sell_and_cancel():
    """Verify dry_run trading cycle, balance mutations, and cancellations."""
    gw = BingXGateway(dry_run=True)
    assert gw.is_dry_run is True
    assert gw.get_balance("USDT") == 10000.0
    assert gw.get_balance("BTC") == 0.0

    # 1. Buy 0.01 BTC
    buy_res = gw.create_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="LIMIT",
        size=0.01,
        price=50000.0,
    )
    assert buy_res["result"] is True
    order_id = buy_res["data"]["orderId"]
    assert order_id.startswith("BINGX_DRY_RUN_")
    assert gw.get_balance("BTC") == 0.01
    assert gw.get_balance("USDT") == 9500.0  # 10000 - (0.01 * 50000)

    # 2. Sell 0.005 BTC
    sell_res = gw.create_order(
        symbol="BTC/USDT",
        side="SELL",
        order_type="LIMIT",
        size=0.005,
        price=60000.0,
    )
    assert sell_res["result"] is True
    assert gw.get_balance("BTC") == 0.005
    assert gw.get_balance("USDT") == 9800.0  # 9500 + (0.005 * 60000)

    # 3. Cancel order
    cancel_res = gw.cancel_order("BTC/USDT", order_id)
    assert cancel_res is True

    # 4. Open orders
    open_orders = gw.get_open_orders("BTC/USDT")
    assert isinstance(open_orders, list)


def test_server_time_skew_calibration():
    """Verify that BingXClient calibrates timestamp skew if local and server clocks drift > 200ms."""
    import time
    client = BingXClient(base_urls=["https://fake.bingx.com"])
    assert client._server_time_offset_ms == 0

    # Simulate response with server timestamp 5000ms ahead
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    future_server_ts = int(time.time() * 1000) + 5000
    mock_resp.json.return_value = {
        "code": 0,
        "msg": "SUCCESS",
        "data": {},
        "timestamp": future_server_ts,
    }

    with patch.object(client.session, "get", return_value=mock_resp):
        client.request("GET", "/openApi/spot/v1/ticker/price")

    # Offset should have been updated to ~5000ms
    assert 4500 <= client._server_time_offset_ms <= 5500

    # Subsequent request signed params should incorporate this offset
    query_string, sig, payload = client.sign_params({})
    assert "timestamp=" in query_string
    ts_val = int(query_string.split("timestamp=")[1].split("&")[0])
    now_ms = int(time.time() * 1000)
    assert ts_val >= now_ms + 4000

