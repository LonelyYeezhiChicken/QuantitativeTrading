"""BDD Scenario Implementation Tests: Daily (08:00/18:00) and Weekly (Monday) Quantitative Reports."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.journal.manager import TradeJournalManager
from packages.journal.report_generator import QuantReportGenerator, TZ_TAIPEI


def _seed_four_autopilot_bots(base_dir: Path) -> None:
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    bots = [
        ("autopilot_BTC_USDT_spot_100u.json", "SPOT", 1, 99.43),
        ("autopilot_state.json", "SWAP_3X", 3, 106.42),
        ("autopilot_BTC_USDT_swap_10x_100u.json", "SWAP_10X", 10, 122.36),
        ("autopilot_BTC_USDT_swap_50x_100u.json", "SWAP_50X", 50, 118.58),
    ]
    for fname, mode, lev, cash in bots:
        payload = {
            "status": "ARMED",
            "mode": mode,
            "capital": 100.0,
            "cash": cash,
            "leverage": lev,
            "position": {
                "side": "NONE",
                "amount": 0.0,
                "amount_btc": 0.0,
                "entry_price": 0.0,
                "margin_used": 0.0,
                "highest_pnl_pct": 0.0,
                "entry_time": "",
                "entry_why": "",
                "ai_decision": "",
            },
            "pending_order": None,
        }
        (data_dir / fname).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class TestDailyAndWeeklyReportsBDDScenarios:
    """BDD Step implementations matching daily_and_weekly_reports.feature."""

    def test_scenario_daily_am_and_pm_reports_inverted_pyramid_and_disk_persistence(self, tmp_path):
        """Scenario: 產出每日早報與晚報並驗證前重後輕倒金字塔結構與真實磁碟落盤."""
        # Given 系統存在 4 台活躍的自動操盤守護進程 (1x, 3x, 10x, 50x) 且總本金為 400.0 USDT
        _seed_four_autopilot_bots(tmp_path)

        # And 權威交易日誌庫中已有 2 筆近 12 小時內已平倉的實戰交易紀錄
        jm = TradeJournalManager(
            db_path=str(tmp_path / "data" / "trade_journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        t_base = datetime(2026, 11, 4, 0, 0, 0, tzinfo=timezone.utc)
        e1 = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=76000.0,
            amount_btc=0.0065,
            margin_used=50.0,
            leverage=10,
            raw_reason="斐波那契黃金口袋低接",
            entry_time_str=(t_base - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        jm.on_trade_update(e1.journal_id, 77500.0)
        jm.on_trade_close(
            e1.journal_id,
            exit_price=77200.0,
            exit_reason="動態移動停利",
            exit_time_str=(t_base - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        e2 = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=77000.0,
            amount_btc=0.002,
            margin_used=50.0,
            leverage=3,
            raw_reason="均線回踩確認",
            entry_time_str=(t_base - timedelta(hours=1, minutes=30)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        jm.on_trade_update(e2.journal_id, 77800.0)
        jm.on_trade_close(
            e2.journal_id,
            exit_price=77600.0,
            exit_reason="動態移動停利",
            exit_time_str=(t_base - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        # When 報表引擎於台北時間 08:00 執行早報 (AM) 與 18:00 執行晚報 (PM) 產出時
        gen = QuantReportGenerator(root_dir=tmp_path, journal_mgr=jm)
        am_dt = datetime(2026, 11, 4, 8, 0, 0, tzinfo=TZ_TAIPEI)
        pm_dt = datetime(2026, 11, 4, 18, 0, 0, tzinfo=TZ_TAIPEI)

        am_report = gen.generate_daily_report(
            current_price=78300.0,
            session="AM",
            now_local=am_dt,
            market_signals={"rsi": 62.5, "ema21": 77500.0, "ema50": 76800.0},
        )
        pm_report = gen.generate_daily_report(
            current_price=78500.0,
            session="PM",
            now_local=pm_dt,
            market_signals={"rsi": 64.0, "ema21": 77600.0, "ema50": 76900.0},
        )

        # Then 系統應於 "journals/reports/daily/" 目錄下分別生成獨立的早報與晚報 Markdown 檔案
        am_path = Path(am_report["path"])
        pm_path = Path(pm_report["path"])
        assert am_path.exists()
        assert pm_path.exists()
        assert am_path != pm_path
        assert am_path.name.endswith("_AM.md")
        assert pm_path.name.endswith("_PM.md")

        # And 報告前半段必須先呈現「一、核心摘要與關鍵數字（必讀區）」與四張單即時健康度總表
        md = am_path.read_text(encoding="utf-8")
        assert "## 一、核心摘要與關鍵數字（必讀區）" in md
        assert "### 1. 一句話戰況結論" in md
        assert "### 2. 四張單即時健康度與關鍵指標總表" in md
        assert "全自動現貨中樞 (SPOT 1x)" in md
        assert "全自動高槓桿中樞 (SWAP 10x)" in md

        # And 報告後半段才呈現「二、附錄：近 12 小時交易日誌明細（備查區，有空再看）」且順序嚴格位於摘要之後
        idx_summary = md.index("## 一、核心摘要與關鍵數字（必讀區）")
        idx_appendix = md.index("## 二、附錄：近 12 小時交易日誌明細（備查區，有空再看）")
        assert idx_summary < idx_appendix

        # And 報告中的總資產淨值與期間已實現損益必須與磁碟狀態檔及日誌庫 100% 數學對齊
        expected_eq = 99.43 + 106.42 + 122.36 + 118.58
        assert am_report["capital_base"] == pytest.approx(400.0)
        assert am_report["total_equity"] == pytest.approx(expected_eq)
        assert am_report["window_trades_count"] == 2
        expected_window_pnl = (77200.0 - 76000.0) * 0.0065 + (77600.0 - 77000.0) * 0.002
        assert am_report["window_pnl_usdt"] == pytest.approx(expected_window_pnl)

    def test_scenario_monday_morning_separate_daily_and_weekly_reports(self, tmp_path):
        """Scenario: 週一早上同時觸發時早報與週報必須分開為兩份獨立檔案且週報包含賽馬排行與調參建議."""
        # Given 系統存在 4 台活躍的自動操盤守護進程且過去 7 天內累積了多筆獲利與停損交易
        _seed_four_autopilot_bots(tmp_path)
        jm = TradeJournalManager(
            db_path=str(tmp_path / "data" / "trade_journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        mon_utc = datetime(2026, 11, 9, 0, 0, 0, tzinfo=timezone.utc)
        e_win = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=75000.0,
            amount_btc=0.0066,
            margin_used=50.0,
            leverage=10,
            raw_reason="黃金口袋支撐",
            entry_time_str=(mon_utc - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        jm.on_trade_update(e_win.journal_id, 78000.0)
        jm.on_trade_close(
            e_win.journal_id,
            exit_price=77500.0,
            exit_reason="動態移動停利",
            exit_time_str=(mon_utc - timedelta(days=2, hours=20)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        e_loss = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=77800.0,
            amount_btc=0.032,
            margin_used=50.0,
            leverage=50,
            raw_reason="超賣反彈",
            entry_time_str=(mon_utc - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        jm.on_trade_update(e_loss.journal_id, 77500.0)
        jm.on_trade_close(
            e_loss.journal_id,
            exit_price=77550.0,
            exit_reason="自適應保證金停損觸發",
            exit_time_str=(mon_utc - timedelta(hours=22)).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        # When 系統於週一早上 08:00 同時執行日報與週報產出時
        published_issues = []

        def _fake_issue_pub(title, body_file, labels):
            published_issues.append((title, Path(body_file), list(labels)))
            return f"https://github.com/example/repo/issues/{len(published_issues)}"

        gen = QuantReportGenerator(root_dir=tmp_path, journal_mgr=jm, issue_publisher=_fake_issue_pub)
        mon_tp = datetime(2026, 11, 9, 8, 0, 0, tzinfo=TZ_TAIPEI)
        mon_daily = gen.generate_daily_report(current_price=78300.0, session="AM", now_local=mon_tp, publish_issue=True)
        mon_weekly = gen.generate_weekly_report(current_price=78300.0, now_local=mon_tp, publish_issue=True)

        # Then 日報應獨立寫入 "journals/reports/daily/" 而週報應獨立寫入 "journals/reports/weekly/" 互不覆蓋或混寫
        d_path = Path(mon_daily["path"])
        w_path = Path(mon_weekly["path"])
        assert d_path.exists()
        assert w_path.exists()
        assert d_path.parent.name == "daily"
        assert w_path.parent.name == "weekly"
        assert d_path != w_path

        # And 當啟用 GitHub Issue 發布時應分別建立兩張獨立的 GitHub Issues (一張量化日報、一張量化週報)
        assert len(published_issues) == 2
        assert published_issues[0][0].startswith("[量化日報]")
        assert published_issues[1][0].startswith("[量化週報]")
        assert mon_daily["issue_url"].endswith("/issues/1")
        assert mon_weekly["issue_url"].endswith("/issues/2")

        # And 週報前半段必讀區應包含「四張單 7 日績效賽馬排行榜（由高至低）」與「下週具體優化與行動建議」
        w_md = w_path.read_text(encoding="utf-8")
        assert "## 一、核心摘要與關鍵數字（必讀區）" in w_md
        assert "### 2. 四張單 7 日績效賽馬排行榜（由高至低）" in w_md
        assert "### 3. 下週具體優化與行動建議" in w_md
        ranked = mon_weekly["ranked_bots"]
        assert ranked[0]["leverage"] == 10
        assert ranked[-1]["leverage"] == 1

        # And 週報後半段附錄才列出本週完整交易日誌清單與 MFE/MAE 數據
        idx_front = w_md.index("## 一、核心摘要與關鍵數字（必讀區）")
        idx_back = w_md.index("## 二、附錄：本週（近 7 日）完整交易日誌清單（備查區，有空再看）")
        assert idx_front < idx_back
        assert "MFE / MAE" in w_md
