"""BDD Scenario Implementation Tests: Automated Trade Journal & Educational Review."""

import sys
import tempfile
import shutil
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.journal.manager import TradeJournalManager
from packages.journal.models import TradeJournalEntry


class TestTradeJournalBDDScenarios:
    """BDD Step implementations matching trade_journal.feature."""

    def test_scenario_trade_open_and_pre_trade_context(self):
        """Scenario: 開倉時自動記錄進場立論與前置風控計畫."""
        temp_dir = Path(tempfile.mkdtemp())
        db_file = temp_dir / "bdd_db.json"
        journals_dir = temp_dir / "journals"

        try:
            # Given 交易守護進程準備發動一筆 "SWAP" 市場的 "LONG" 交易
            mgr = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))

            # When 系統偵測到價格站穩 EMA21 且 RSI 為 56.5 時執行開倉
            entry = mgr.on_trade_open(
                symbol="BTC/USDT",
                market_type="SWAP",
                side="LONG",
                entry_price=77200.0,
                amount_btc=0.00194,
                margin_used=50.0,
                leverage=3,
                raw_reason="EMA21 breakout & momentum confirmation",
                snapshot_dict={"price": 77200.0, "rsi": 56.5, "ema21": 77000.0, "atr": 1150.0},
                stop_loss_pct=2.5,
                trailing_pullback_pct=1.2,
            )

            # Then 系統應自動建立交易日誌草稿
            assert entry.status == "OPEN"
            assert entry.journal_id is not None
            card_path = journals_dir / "entries" / f"{entry.journal_id}.md"
            assert card_path.exists()

            # And 日誌中應包含完整的進場環境快照與立論假說
            assert entry.snapshot.rsi == 56.5
            assert "動能健康區間" in entry.review.thesis
            assert len(entry.review.thesis) > 20

            # And 應設定明確的停損價位與追蹤停利回撤參數
            assert entry.risk_plan.stop_loss_pct == 2.5
            assert entry.risk_plan.trailing_pullback_pct == 1.2
            assert entry.risk_plan.stop_loss_price > 0.0
            assert entry.risk_plan.max_loss_usdt > 0.0

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_scenario_trade_close_and_pedagogical_reflection(self):
        """Scenario: 平倉時自動產出勝敗覆盤反思與學習筆記."""
        temp_dir = Path(tempfile.mkdtemp())
        db_file = temp_dir / "bdd_db2.json"
        journals_dir = temp_dir / "journals"

        try:
            # Given 系統存在一筆進行中的多單交易日誌
            mgr = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))
            entry = mgr.on_trade_open(
                symbol="BTC/USDT",
                market_type="SWAP",
                side="LONG",
                entry_price=77000.0,
                amount_btc=0.00194,
                margin_used=50.0,
                leverage=3,
                raw_reason="EMA21 breakout confirmation",
                snapshot_dict={"price": 77000.0, "rsi": 55.0, "ema21": 76800.0},
                stop_loss_pct=2.5,
                trailing_pullback_pct=1.2,
            )
            # 盤中價格漲至 77900
            mgr.on_trade_update(entry.journal_id, 77900.0)

            # When 價格達標後回撤觸發 "動態追蹤止盈" 平倉
            closed = mgr.on_trade_close(
                journal_id=entry.journal_id,
                exit_price=77600.0,
                exit_reason="動態追蹤止盈觸發 (回撤1.2%離場)",
            )

            # Then 系統應結算實現盈虧與實際 R 倍數
            assert closed.status == "CLOSED"
            assert closed.pnl_usdt > 0.0
            assert closed.realized_r_multiple > 0.0

            # And 應自動產生包含操盤心得與心理啟發的學習報告
            card_md = closed.to_markdown()
            assert "給操盤手的學習心得與啟發" in card_md
            assert "順勢與時機" in closed.review.pedagogical_takeaway

            # And 應在硬碟生成該筆交易獨立的 Markdown 覆盤卡片
            card_path = journals_dir / "entries" / f"{closed.journal_id}.md"
            assert card_path.exists()
            content = card_path.read_text(encoding="utf-8")
            assert "實現盈虧 (PnL)" in content

            # And 應即時更新交易日誌索引總表 INDEX.md
            index_path = journals_dir / "INDEX.md"
            assert index_path.exists()
            index_content = index_path.read_text(encoding="utf-8")
            assert closed.journal_id in index_content
            assert "總交易筆數" in index_content
            assert "閱讀學習覆盤" in index_content

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
