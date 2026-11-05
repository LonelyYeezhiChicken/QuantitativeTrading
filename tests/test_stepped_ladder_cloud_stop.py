"""Unit & Regression tests for Stepped Cloud Stop-Loss Ladder (慢慢階梯式雲端套保鎖利)."""

from pathlib import Path
import sys
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import (
    UnifiedAutopilotEngine,
    get_laddered_cloud_stop_tier,
    get_tier_locked_margin_pct,
    sync_breakeven_stop_loss,
)
from packages.journal import TradeJournalManager


def test_ladder_tier_calculations():
    """Verify wide, conservative tier trigger milestones and locked profits."""
    # 50x SWAP: margin_tp_threshold = 25.0%
    tp_50x = 25.0
    assert get_laddered_cloud_stop_tier(peak_pct=5.0, tp_threshold=tp_50x) == 0
    assert get_laddered_cloud_stop_tier(peak_pct=13.0, tp_threshold=tp_50x) == 1   # >= 12.5%
    assert get_laddered_cloud_stop_tier(peak_pct=38.0, tp_threshold=tp_50x) == 2   # >= 37.5%
    assert get_laddered_cloud_stop_tier(peak_pct=80.0, tp_threshold=tp_50x) == 3   # >= 75.0%
    assert get_laddered_cloud_stop_tier(peak_pct=130.0, tp_threshold=tp_50x) == 4  # >= 125.0%

    # Locked profits per tier for 50x
    assert get_tier_locked_margin_pct(1, tp_50x) == 1.5   # Breakeven + fee floor
    assert get_tier_locked_margin_pct(2, tp_50x) == 12.5  # Lock +12.5% ROE
    assert get_tier_locked_margin_pct(3, tp_50x) == 37.5  # Lock +37.5% ROE
    assert get_tier_locked_margin_pct(4, tp_50x) == 75.0  # Lock +75.0% ROE


def test_stepped_cloud_stop_ladder_lifecycle(tmp_path, monkeypatch):
    """Verify full lifecycle of cloud stop-loss advancing step-by-step without premature exit."""
    jm = TradeJournalManager(
        db_path=str(tmp_path / "journal_db.json"),
        journals_dir=str(tmp_path / "journals"),
    )
    engine = UnifiedAutopilotEngine(
        symbol="BTC/USDT",
        leverage=50,
        capital=100.0,
        enable_ai_veto=False,
        dry_run=True,
        state_file=tmp_path / "state_50x.json",
        journal_mgr=jm,
    )
    engine.arm()

    entry_price = 80000.0
    qty = 0.05
    margin = 80.0

    j_entry = jm.on_trade_open(
        symbol="BTC/USDT",
        market_type="SWAP",
        side="LONG",
        entry_price=entry_price,
        amount_btc=qty,
        margin_used=margin,
        leverage=50,
        raw_reason="50x 趨勢開多",
        snapshot_dict={"price": entry_price},
        stop_loss_pct=15.0,
        trailing_pullback_pct=5.0,
    )

    engine.position = {
        "side": "LONG",
        "amount": qty,
        "amount_btc": qty,
        "entry_price": entry_price,
        "margin_used": margin,
        "highest_pnl_pct": 0.0,
        "entry_time": j_entry.entry_time,
        "entry_why": "50x 趨勢開多",
        "ai_decision": "EXECUTE",
        "journal_id": j_entry.journal_id,
        "native_sl_price": 77600.0,
        "breakeven_synced": False,
        "cloud_sl_tier": 0,
    }

    # Step 1: Rally to 80,240 (+15.0% ROE) -> Triggers Tier 1 (保本套保, > 80,000)
    p1 = 80240.0
    monkeypatch.setattr(engine.gw, "fetch_ticker", lambda symbol, market_type="SWAP": {"price": p1, "bid": p1, "ask": p1})
    res1 = engine.step()
    assert engine.position["cloud_sl_tier"] == 1
    tier1_sl = engine.position["native_sl_price"]
    assert tier1_sl > entry_price
    assert "保本" in res1["message"]

    # Step 2: Rally to 80,640 (+40.0% ROE) -> Triggers Tier 2 (第一階大鎖利)
    p2 = 80640.0
    monkeypatch.setattr(engine.gw, "fetch_ticker", lambda symbol, market_type="SWAP": {"price": p2, "bid": p2, "ask": p2})
    res2 = engine.step()
    assert engine.position["cloud_sl_tier"] == 2
    tier2_sl = engine.position["native_sl_price"]
    assert tier2_sl > tier1_sl
    assert "第 2 階鎖利" in res2["message"]

    # Step 3: Normal healthy pullback to 80,450 (+28% ROE) -> Must NOT trigger cloud stop (which is at ~80,200)
    p3 = 80450.0
    monkeypatch.setattr(engine.gw, "fetch_ticker", lambda symbol, market_type="SWAP": {"price": p3, "bid": p3, "ask": p3})
    res3 = engine.step()
    assert engine.position["side"] == "LONG"  # Position still open!
    assert engine.position["cloud_sl_tier"] == 2  # Tier preserved!

    # Step 4: Mega rally to 81,300 (+81.25% ROE) -> Triggers Tier 3 (翻倍鎖利)
    p4 = 81300.0
    monkeypatch.setattr(engine.gw, "fetch_ticker", lambda symbol, market_type="SWAP": {"price": p4, "bid": p4, "ask": p4})
    res4 = engine.step()
    assert engine.position["cloud_sl_tier"] == 3
    tier3_sl = engine.position["native_sl_price"]
    assert tier3_sl > tier2_sl
    assert "第 3 階鎖利" in res4["message"]
