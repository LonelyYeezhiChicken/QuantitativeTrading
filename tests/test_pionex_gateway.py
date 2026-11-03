"""Unit tests for PionexGateway and PionexClient."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import PionexGateway, PionexClient

def test_symbol_normalization():
    """Verify bidirectional symbol translation."""
    assert PionexGateway.to_pionex_symbol("BTC/USDT") == "BTC_USDT"
    assert PionexGateway.to_pionex_symbol("ETH/USDT") == "ETH_USDT"
    assert PionexGateway.to_pionex_symbol("SOL/USDT:USDT") == "SOL_USDT_USDT"
    assert PionexGateway.from_pionex_symbol("BTC_USDT") == "BTC/USDT"

def test_signature_with_json_body():
    """Verify POST request signature with JSON payload."""
    client = PionexClient(api_key="key_abc", api_secret="secret_xyz")
    body = {"symbol": "BTC_USDT", "side": "BUY", "type": "LIMIT", "size": "0.1", "price": "50000"}
    params = {"timestamp": 1700000000000}

    path_url, sig = client.generate_signature("POST", "/api/v1/trade/order", params=params, body=body)

    assert path_url == "/api/v1/trade/order?timestamp=1700000000000"
    assert len(sig) == 64

def test_dry_run_balance_and_cancel():
    """Verify dry_run balance query and order cancellation."""
    gw = PionexGateway(dry_run=True)
    assert gw.get_balance("USDT") == 10000.0

    cancel_res = gw.cancel_order("BTC/USDT", "DRY_RUN_123")
    assert cancel_res is True

    open_orders = gw.get_open_orders("BTC/USDT")
    assert isinstance(open_orders, list)
