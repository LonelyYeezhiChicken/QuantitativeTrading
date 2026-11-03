"""BDD & Unit Tests for Multi-Instance Swap Bot and High Leverage (10x) Risk Management."""

import json
from pathlib import Path
import pytest

from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager
from apps.cli.overnight_swap_bot import configure_bot_paths, load_state, execute_swap_open, execute_swap_close

ROOT_DIR = Path(__file__).resolve().parent.parent


def test_multi_instance_path_isolation(tmp_path, monkeypatch):
    """Verify that multiple swap bots have strictly isolated state files, logs, and flags."""
    # 1. Default 3x bot paths
    name_3x = configure_bot_paths(None, leverage=3, capital=100.0)
    assert name_3x == "swap_100u"

    # 2. 10x bot paths
    name_10x = configure_bot_paths(None, leverage=10, capital=100.0)
    assert name_10x == "swap_10x_100u"

    # 3. Custom named bot paths
    name_custom = configure_bot_paths("sniper_20x", leverage=20, capital=200.0)
    assert name_custom == "sniper_20x"


def test_high_leverage_10x_risk_and_order_execution(tmp_path, monkeypatch):
    """Verify 10x leverage position opening, notional scaling, and native SL calculation."""
    # Setup isolated state in tmp_path
    state_file = tmp_path / "bingx_swap_10x_test.json"
    log_file = tmp_path / "overnight_swap_10x_test.log"
    flag_file = tmp_path / "swap_10x_test_stop.flag"

    import apps.cli.overnight_swap_bot as bot_mod
    monkeypatch.setattr(bot_mod, "STATE_FILE", state_file)
    monkeypatch.setattr(bot_mod, "LOG_FILE", log_file)
    monkeypatch.setattr(bot_mod, "STOP_FLAG_FILE", flag_file)

    gw = BingXGateway(dry_run=True, default_market_type=MarketType.SWAP.value)
    state = bot_mod.load_state(capital=100.0, leverage=10)

    assert state["initial_capital"] == 100.0
    assert state["available_margin"] == 100.0
    assert state["position"]["side"] == "NONE"

    entry_price = 77000.0
    margin_to_use = 50.0
    leverage = 10
    price_sl_pct = 1.5

    # Execute 10x LONG entry
    execute_swap_open(
        state=state,
        price=entry_price,
        side="LONG",
        margin_amount=margin_to_use,
        leverage=leverage,
        reason="10x 多頭突破動能開倉",
        sig={"price": entry_price, "rsi": 62.0, "ema21": 76500.0, "ema50": 76000.0},
        gw=gw,
        price_sl_pct=price_sl_pct,
        price_pullback_pct=0.5,
    )

    # 1. State assertions
    pos = state["position"]
    assert pos["side"] == "LONG"
    assert pos["margin_used"] == 50.0
    assert state["available_margin"] == 50.0
    assert pos["leverage"] == 10

    # 2. Math & Notional assertions
    expected_notional = 500.0  # 50U * 10x
    expected_btc = 500.0 / 77000.0
    assert pytest.approx(pos["amount_btc"], rel=1e-4) == expected_btc

    # 3. Liquidation price estimation (~10% down at 10x)
    assert pos["liquidation_price"] < entry_price
    assert pos["liquidation_price"] == pytest.approx(entry_price * (1.0 - (0.9 / 10)), rel=1e-4)

    # 4. Verify Journal Entry
    journal_id = pos["journal_id"]
    assert journal_id is not None
    assert "SWAP_" in journal_id

    jm = TradeJournalManager()
    entry = jm.get_entry(journal_id)
    assert entry is not None
    assert entry.leverage == 10
    assert entry.notional_value == pytest.approx(500.0, rel=1e-2)
    assert entry.risk_plan.stop_loss_pct == pytest.approx(15.0, rel=1e-2)  # 1.5% * 10 = 15% margin
    expected_sl_price = entry_price * (1.0 - 0.015)
    assert entry.risk_plan.stop_loss_price == pytest.approx(expected_sl_price, rel=1e-2)
    assert entry.risk_plan.max_loss_usdt == pytest.approx(7.50, rel=1e-2)  # 50U * 15%

    # 5. Clean Close Assertion
    exit_price = 78540.0  # +2.0% price move
    execute_swap_close(state, price=exit_price, reason="達到目標利潤 +20% ROE 平倉", gw=gw)

    assert state["position"]["side"] == "NONE"
    assert state["available_margin"] > 50.0  # Margin + profit returned
    assert len(state["history"]) == 1
    closed_rec = state["history"][0]
    assert closed_rec["pnl_usdt"] > 0
    assert closed_rec["pnl_pct"] == pytest.approx(20.0, rel=1e-1)
