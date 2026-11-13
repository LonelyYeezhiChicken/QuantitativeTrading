"""BDD Scenario Implementation Tests: Counter-Trend Moderate Tight Stop-Loss & Dual-Track Risk Shield."""

import json
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import (
    UnifiedAutopilotEngine,
    AutopilotState,
    evaluate_structural_entry,
    is_counter_trend_trade,
)
from packages.journal import TradeJournalManager


class TestCounterTrendTightStopLossBDDScenarios:
    """BDD Step implementations matching counter_trend_tight_stop_loss.feature."""

    def test_scenario_counter_trend_oversold_long_applies_1pct_tight_stop(self, tmp_path, monkeypatch):
        """Scenario: 空頭排列下觸發短線超賣反彈做多時自動識別為逆勢單並掛設 1.0% (-3.0% ROE) 適度窄損."""
        state_file = tmp_path / "autopilot_ct_swap_3x.json"
        jm = TradeJournalManager(
            db_path=str(tmp_path / "trade_journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=400.0,
            enable_ai_veto=False,
            dry_run=True,
            state_file=state_file,
            journal_mgr=jm,
            use_risk_based_sizing=False,
        )
        engine.arm()

        # Given 當前市場處於中長線空頭排列 (EMA21=72100 < EMA50=72800) 且 RSI=22.3 超賣區
        cur_price = 71100.0
        bear_oversold_signals = {
            "price": cur_price,
            "rsi": 22.3,
            "ema21": 72100.0,
            "ema50": 72800.0,
            "atr": 1066.0,
            "prev_close": 70950.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
            "is_4h_bull": False,
            "is_4h_bear": True,
        }
        monkeypatch.setattr(engine, "_compute_market_signals", lambda p: bear_oversold_signals)

        # When 最新市價於 71100 出現止跌勾頭反彈觸發開倉
        sig, reason = evaluate_structural_entry(engine.mode, cur_price, bear_oversold_signals)
        assert sig == "LONG"
        assert "[逆勢窄損保護]" in reason
        assert is_counter_trend_trade(sig, bear_oversold_signals, reason) is True

        step_res = engine.step(override_price=cur_price)

        # Then 系統應將此筆 LONG 交易識別為逆勢單且附加 -1.0% (70389.0) 原生硬停損
        assert step_res["action_taken"] == "OPEN_POSITION"
        assert engine.position["side"] == "LONG"
        assert engine.position["is_counter_trend"] is True
        assert engine.position["price_sl_pct"] == pytest.approx(1.0)
        assert engine.position["sl_threshold_pct"] == pytest.approx(3.0)

        expected_tight_sl = cur_price * 0.99  # 70389.0 (-1.0% price, NOT -1.5% / 2.0 ATR)
        assert engine.position["native_sl_price"] == pytest.approx(expected_tight_sl, rel=1e-4)

        # And 權威交易日誌與持倉狀態中的 stop_loss_pct 必須記錄為 3.0% ROE
        jid = engine.position["journal_id"]
        j_entry = jm.get_entry(jid)
        assert j_entry is not None
        assert j_entry.risk_plan.stop_loss_pct == pytest.approx(3.0)
        assert j_entry.risk_plan.stop_loss_price == pytest.approx(expected_tight_sl, rel=1e-4)

    def test_scenario_trend_aligned_long_retains_standard_1_5pct_stop(self, tmp_path, monkeypatch):
        """Scenario: 多頭排列下觸發順勢回踩做多時維持 1.5% (-4.5% ROE) 標準順勢停損空間."""
        state_file = tmp_path / "autopilot_trend_swap_3x.json"
        jm = TradeJournalManager(
            db_path=str(tmp_path / "trade_journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=400.0,
            enable_ai_veto=False,
            dry_run=True,
            state_file=state_file,
            journal_mgr=jm,
            use_risk_based_sizing=False,
        )
        engine.arm()

        # Given 當前市場處於中長線多頭排列 (EMA21=75000 > EMA50=74000) 且 RSI=50.0
        cur_price = 75100.0
        bull_pullback_signals = {
            "price": cur_price,
            "rsi": 50.0,
            "ema21": 75000.0,
            "ema50": 74000.0,
            "atr": 0.0,  # test standard price_sl_pct=1.5%
            "prev_close": 74950.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
            "is_4h_bull": True,
            "is_4h_bear": False,
        }
        monkeypatch.setattr(engine, "_compute_market_signals", lambda p: bull_pullback_signals)

        # When 最新市價回踩至 75100 貼近 EMA21 觸發順勢做多開倉
        step_res = engine.step(override_price=cur_price)

        # Then 系統應將此筆 LONG 交易識別為順勢單且維持 4.5% ROE 標準停損空間
        assert step_res["action_taken"] == "OPEN_POSITION"
        assert engine.position["is_counter_trend"] is False
        assert engine.position["price_sl_pct"] == pytest.approx(1.5)
        assert engine.position["sl_threshold_pct"] == pytest.approx(4.5)

        jid = engine.position["journal_id"]
        j_entry = jm.get_entry(jid)
        assert j_entry is not None
        assert j_entry.risk_plan.stop_loss_pct == pytest.approx(4.5)

    def test_scenario_hot_restart_takeover_and_tight_stop_execution(self, tmp_path):
        """Scenario: 逆勢單持倉期間跌破 -3.0% ROE 窄損門檻時立即平倉止血且支援無縫熱重啟接管."""
        state_file = tmp_path / "autopilot_BTC_USDT_swap_3x_400u.json"
        db_file = tmp_path / "trade_journal_db.json"
        journals_dir = tmp_path / "journals"

        jm = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))
        entry_price = 71102.3
        qty = 0.0137
        margin = 324.7005
        tight_sl_price = 70391.3

        # Given 3 倍槓桿合約持有一筆開倉價為 71102.3 之既有逆勢超賣 LONG 倉位且雲端停損設於 70391.3
        j_entry = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=entry_price,
            amount_btc=qty,
            margin_used=margin,
            leverage=3,
            raw_reason="短線超賣止跌勾頭反彈確認 (RSI=22.3<35, 現價高於前收)",
            snapshot_dict={"price": entry_price, "rsi": 22.3, "ema21": 72112.38},
            stop_loss_pct=3.0,
            trailing_pullback_pct=0.99,
            custom_id="SWAP_3X_20261113_012705_LONG",
            stop_loss_price=tight_sl_price,
        )

        legacy_state = {
            "status": "ARMED",
            "mode": "SWAP_3X",
            "capital": 400.0,
            "cash": 108.97,
            "leverage": 3,
            "position": {
                "side": "LONG",
                "amount": qty,
                "amount_btc": qty,
                "entry_price": entry_price,
                "margin_used": margin,
                "highest_pnl_pct": 0.0,
                "entry_time": "2026-11-13 01:27:05 UTC",
                "entry_why": "短線超賣止跌勾頭反彈確認 (RSI=22.3<35, 現價高於前收)",
                "ai_decision": "Ollama EXECUTE: 指標處於健康順勢區間 (RSI=22.3, 乖離=-1.4%)，核准開多",
                "journal_id": j_entry.journal_id,
                "native_sl_price": tight_sl_price,
                "sl_order_id": "2121061831967080448",
            },
            "pending_order": None,
            "circuit_breaker_triggered": False,
            "circuit_breaker_reason": "",
            "capital_allocation_ratio": 0.75,
            "max_loss_pct": 50.0,
        }
        state_file.write_text(json.dumps(legacy_state, ensure_ascii=False, indent=2), encoding="utf-8")

        # When 操盤守護進程執行短暫停機更新並重新載入磁碟狀態檔接管該筆持倉
        restarted_engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=400.0,
            enable_ai_veto=False,
            dry_run=True,
            state_file=state_file,
            journal_mgr=jm,
        )
        # Seed simulated exchange position on dry-run gateway (representing live BingX position surviving container restart)
        restarted_engine.gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=qty,
            market_type="SWAP",
            position_side="LONG",
            leverage=3,
            stop_loss_price=tight_sl_price,
            simulation_price=entry_price,
        )
        restarted_engine.arm()

        # Then 引擎必須無縫恢復該倉位之逆勢窄損標記且不重複下單
        assert restarted_engine.position["side"] == "LONG"
        assert restarted_engine.position["is_counter_trend"] is True
        assert restarted_engine.position["sl_threshold_pct"] == pytest.approx(3.0)
        assert restarted_engine.position["native_sl_price"] == pytest.approx(tight_sl_price)

        # Hold tick at 70850 (-1.06% ROE): still safely above -3.0% ROE tight stop
        hold_step = restarted_engine.step(override_price=70850.0)
        assert hold_step["action_taken"] == "NONE"
        assert restarted_engine.position["side"] == "LONG"

        # And 當市場價格下跌至 70380.0 使浮動虧損達 -3.05% ROE (跌破 -3.0% 窄損門檻但未達 -4.5%) 時
        stop_step = restarted_engine.step(override_price=70380.0)

        # Then 系統必須立即觸發硬停損平倉止血並將結算紀錄寫入權威交易日誌
        assert stop_step["action_taken"] == "STOP_LOSS"
        assert restarted_engine.position["side"] == "NONE"

        closed_entry = jm.get_entry(j_entry.journal_id)
        assert closed_entry is not None
        assert closed_entry.status == "CLOSED"
        assert closed_entry.pnl_pct == pytest.approx(-3.05, abs=0.1)


def test_scenario_anti_hourly_open_noise_falling_knife_and_45m_cooldown():
    """Verify counter-trend oversold rebound rejects <0.20% noise after a red 1H bar and enforces 45m cooldown after CT loss."""
    from datetime import datetime, timezone

    # Given 市場處於空頭排列 (EMA21 低於 EMA50) 且 RSI 跌至 17.2 超賣區
    # 而且 上一根已收盤之 1 小時 K 線為陰線 (prev_bar_is_green=False, prev_close=70212.0)
    bear_signals = {
        "price": 70260.0,
        "rsi": 17.2,
        "ema21": 71773.3,
        "ema50": 72650.0,
        "prev_close": 70212.0,
        "prev_prev_close": 70919.0,
        "prev_bar_is_green": False,
        "in_bull_golden_pocket": False,
        "in_bear_golden_pocket": False,
        "is_4h_bull": False,
        "is_4h_bear": True,
        "touch_bb_low": True,
        "touch_bb_up": False,
    }

    # When 整點剛換線市價僅微幅跳高至 70260.0 (+0.07%) 試圖觸發超賣反彈時
    sig_noise, _ = evaluate_structural_entry("SWAP", 70260.0, bear_signals)
    # Then 系統必須拒絕開倉以防止整點雜訊接刀
    assert sig_noise is None

    # When 實質反彈達 +0.21% (70360.0) 或上一根 1H 確定收紅陽線時才允許進場
    sig_real, reason_real = evaluate_structural_entry("SWAP", 70360.0, bear_signals)
    assert sig_real == "LONG"
    assert "[逆勢窄損保護]" in reason_real

    green_bar_signals = dict(bear_signals, prev_bar_is_green=True)
    sig_green, _ = evaluate_structural_entry("SWAP", 70260.0, green_bar_signals)
    assert sig_green == "LONG"

    # And 若剛經歷一筆逆勢停損出場，距離平倉 20 分鐘內再次出現反彈訊號時必須受 45 分鐘冷卻鎖定攔截
    history = [
        {
            "closed_at": "2026-11-13 03:15:42 UTC",
            "pnl_usd": -9.46,
            "why_enter": "短線超賣止跌勾頭反彈確認 [逆勢窄損保護]",
        }
    ]
    now_20m = datetime(2026, 11, 13, 3, 35, 42, tzinfo=timezone.utc)
    sig_cd, reason_cd = evaluate_structural_entry("SWAP", 70360.0, bear_signals, history=history, now_utc=now_20m)
    assert sig_cd is None
    assert "45 分鐘" in reason_cd

    now_46m = datetime(2026, 11, 13, 4, 1, 42, tzinfo=timezone.utc)
    sig_after, _ = evaluate_structural_entry("SWAP", 70360.0, bear_signals, history=history, now_utc=now_46m)
    assert sig_after == "LONG"
