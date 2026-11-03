"""Unit tests for Trade Journal Management and Educational Review Engine."""

import pytest
import tempfile
import shutil
from pathlib import Path

from packages.journal.models import MarketSnapshot, RiskPlan, TradeTrajectory, TradeJournalEntry
from packages.journal.analyzer import JournalAnalyzer
from packages.journal.manager import TradeJournalManager


@pytest.fixture
def temp_journal_env():
    """Create a temporary directory for isolated journal tests."""
    temp_dir = Path(tempfile.mkdtemp())
    db_file = temp_dir / "test_db.json"
    journals_dir = temp_dir / "journals"
    yield db_file, journals_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_market_snapshot_and_risk_plan():
    """Verify MarketSnapshot and RiskPlan creation and conversion."""
    snap = MarketSnapshot(price=77500.0, rsi=58.5, ema21=77200.0, bias_pct=0.39)
    d = snap.to_dict()
    assert d["price"] == 77500.0
    assert d["rsi"] == 58.5
    restored = MarketSnapshot.from_dict(d)
    assert restored.price == snap.price
    assert restored.rsi == snap.rsi

    risk = RiskPlan(stop_loss_price=75500.0, stop_loss_pct=2.5, max_loss_usdt=1.25)
    r_dict = risk.to_dict()
    assert r_dict["stop_loss_pct"] == 2.5
    assert RiskPlan.from_dict(r_dict).stop_loss_price == 75500.0


def test_journal_analyzer_thesis():
    """Verify JournalAnalyzer thesis generation for long and short setups."""
    snap_oversold = MarketSnapshot(price=76000.0, rsi=28.0, ema21=77000.0, bias_pct=-1.3)
    thesis_long = JournalAnalyzer.generate_entry_thesis(snap_oversold, "LONG", "SPOT", "RSI oversold bounce")
    assert "超賣極值區" in thesis_long
    assert "SPOT" in thesis_long

    snap_breakout = MarketSnapshot(price=78000.0, rsi=62.0, ema21=77500.0, bias_pct=0.65)
    thesis_breakout = JournalAnalyzer.generate_entry_thesis(snap_breakout, "LONG", "SWAP", "EMA breakout")
    assert "動能健康區間" in thesis_breakout
    assert "SWAP" in thesis_breakout


def test_trade_lifecycle_in_manager(temp_journal_env):
    """Test full trade lifecycle: Open -> Update -> Close -> Render Markdown."""
    db_file, journals_dir = temp_journal_env
    mgr = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))

    # 1. Open Trade
    entry = mgr.on_trade_open(
        symbol="BTC/USDT",
        market_type="SWAP",
        side="LONG",
        entry_price=77000.0,
        amount_btc=0.00194,
        margin_used=50.0,
        leverage=3,
        raw_reason="EMA21 breakout & RSI confirmation",
        snapshot_dict={"price": 77000.0, "rsi": 55.0, "ema21": 76800.0},
        stop_loss_pct=2.5,
        trailing_pullback_pct=1.2,
    )
    assert entry.status == "OPEN"
    assert entry.journal_id in mgr._entries
    assert (journals_dir / "entries" / f"{entry.journal_id}.md").exists()
    assert (journals_dir / "INDEX.md").exists()

    # 2. Update Trajectory (Price moves up to 78000, then down to 76900)
    mgr.on_trade_update(entry.journal_id, 78000.0)
    mgr.on_trade_update(entry.journal_id, 76900.0)

    updated = mgr.get_entry(entry.journal_id)
    assert updated.trajectory.highest_price == 78000.0
    assert updated.trajectory.lowest_price == 76900.0
    assert updated.trajectory.mfe_pct > 0.0
    assert updated.trajectory.mae_pct < 0.0

    # 3. Close Trade (Take profit at 77800)
    closed = mgr.on_trade_close(
        journal_id=entry.journal_id,
        exit_price=77800.0,
        exit_reason="動態追蹤止盈觸發",
    )
    assert closed.status == "CLOSED"
    assert closed.pnl_usdt > 0.0
    assert closed.realized_r_multiple > 0.0
    assert closed.review.quality_score >= 3
    assert "追蹤止盈" in closed.review.exit_reason
    assert "順勢與時機" in closed.review.pedagogical_takeaway

    # 4. Check Markdown file content
    entry_md_path = journals_dir / "entries" / f"{entry.journal_id}.md"
    assert entry_md_path.exists()
    with open(entry_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "交易學習日誌" in content
    assert "實現盈虧 (PnL)" in content
    assert "進場立論假說" in content
    assert "給操盤手的學習心得與啟發" in content

    # 5. Check Summary Stats
    stats = mgr.get_summary_stats()
    assert stats["total_trades"] == 1
    assert stats["closed_trades"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_pnl"] > 0
