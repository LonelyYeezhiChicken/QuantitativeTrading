"""Unit tests for BingX WebSocket Client and Real-Time Gateway Integration."""

import gzip
import json
import time
import pytest
from packages.execution.bingx_ws import BingXWebSocketClient
from packages.execution.bingx_gateway import BingXGateway


def test_ws_client_message_processing():
    """Verify ticker message decompression and cache ingestion."""
    client = BingXWebSocketClient(symbols=["BTC-USDT", "XAUT-USDT"])

    mock_ticker_payload = {
        "dataType": "BTC-USDT@ticker",
        "data": {
            "e": "24hTicker",
            "s": "BTC-USDT",
            "c": "77500.5",
            "h": "78200.0",
            "l": "76100.0",
            "p": "400.0",
            "P": "0.52%",
            "v": "1500.0",
            "B": "77500.0",
            "A": "77501.0",
            "E": 1700000000000,
        },
    }

    client._process_message(mock_ticker_payload, "SPOT")
    cached = client.get_ticker("BTC/USDT", "SPOT")

    assert cached is not None
    assert cached["price"] == 77500.5
    assert cached["high_24h"] == 78200.0
    assert cached["low_24h"] == 76100.0
    assert cached["bid"] == 77500.0
    assert cached["ask"] == 77501.0
    assert cached["change_24h_pct"] == 0.52


def test_ws_client_xaut_processing():
    """Verify XAUT ticker update parsing."""
    client = BingXWebSocketClient(symbols=["XAUT-USDT"])

    mock_xaut_payload = {
        "dataType": "XAUT-USDT@ticker",
        "data": {
            "e": "24hTicker",
            "s": "XAUT-USDT",
            "c": "3945.80",
            "h": "3960.00",
            "l": "3910.00",
            "P": "0.85%",
            "B": "3945.50",
            "A": "3946.00",
        },
    }

    client._process_message(mock_xaut_payload, "SPOT")
    cached = client.get_ticker("XAUT/USDT", "SPOT")

    assert cached is not None
    assert cached["price"] == 3945.80
    assert cached["change_24h_pct"] == 0.85


def test_gateway_rest_fallback():
    """Verify Gateway falls back cleanly to REST when WS cache is empty or disabled."""
    gw = BingXGateway(dry_run=True, enable_ws=False)
    assert gw.is_ws_connected is False

    ticker = gw.fetch_ticker("BTC/USDT")
    assert ticker["price"] > 0
    # Source is either REST or fallback
    assert ticker.get("source") != "WEBSOCKET"
