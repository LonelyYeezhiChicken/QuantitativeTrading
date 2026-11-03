"""Test PaperBroker execution and accounting logic."""

import sys
from pathlib import Path
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from packages.execution import PaperBroker

def test_paper_broker_buy_and_sell(tmp_path):
    state_file = tmp_path / "paper_state_test.json"
    broker = PaperBroker(
        initial_balance=10000.0,
        fee_rate=0.001,   # 0.1%
        slippage=0.0005,  # 0.05%
        state_file=str(state_file),
    )

    # 1. Buy $1,000 worth of BTC at $50,000
    buy_order = broker.buy("BTC/USDT", current_price=50000.0, usdt_amount=1000.0)
    assert buy_order is not None
    assert broker.cash == 9000.0
    assert "BTC/USDT" in broker.positions
    assert broker.positions["BTC/USDT"]["amount"] > 0
    # Price paid with positive slippage: 50000 * 1.0005 = 50025
    assert buy_order["price"] == pytest.approx(50025.0)

    # 2. Sell 100% BTC at $60,000 (Profitable trade)
    sell_order = broker.sell("BTC/USDT", current_price=60000.0, pct_position=1.0)
    assert sell_order is not None
    assert "BTC/USDT" not in broker.positions
    assert sell_order["realized_pnl"] > 0
    assert broker.cash > 10000.0  # Profited overall

    # Summary check
    summary = broker.summary(current_prices={"BTC/USDT": 60000.0})
    assert summary["total_trades"] == 2
    assert summary["cash_usdt"] > 10000.0
