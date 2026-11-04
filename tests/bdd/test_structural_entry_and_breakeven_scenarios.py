"""BDD Scenario Implementation Tests: Structural Entry Filter & 3-Stage Break-Even Shield."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import (
    UnifiedAutopilotEngine,
    evaluate_structural_entry,
    evaluate_three_stage_exit,
)
from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager
import apps.cli.overnight_swap_bot as swap_bot


class TestStructuralEntryAndBreakevenBDDScenarios:
    """BDD Step implementations matching structural_entry_and_breakeven_shield.feature."""

    def test_scenario_trend_alignment_blocks_counter_trend_entries(self):
        """Scenario: 空頭排列下禁止僅因價格短暫站上 EMA21 而盲目追多且多頭排列下禁止逆勢開空."""
        # Given 市場處於中長線空頭排列 (EMA21 < EMA50) 且最新市價微幅高於 EMA21、RSI 為 50.0
        bear_trend_signals = {
            "price": 76100.0,
            "rsi": 50.0,
            "ema21": 76000.0,
            "ema50": 77200.0,  # EMA21 < EMA50 (Bearish macro structure)
            "prev_close": 76050.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        # When 結構化進場評估器檢驗最新市場狀態
        sig_side, sig_reason = evaluate_structural_entry("SWAP", 76100.0, bear_trend_signals)
        # Then 系統應拒絕發出 "LONG" 開倉訊號以避免逆大勢追高
        assert sig_side is None

        # And 當市場處於中長線多頭排列 (EMA21 > EMA50) 且價格短暫跌破 EMA21、RSI 為 44.0 時
        bull_trend_pullback_signals = {
            "price": 76800.0,
            "rsi": 44.0,
            "ema21": 77300.0,
            "ema50": 76500.0,  # EMA21 > EMA50 (Bullish macro structure)
            "prev_close": 76900.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        sig_side_2, _ = evaluate_structural_entry("SWAP", 76800.0, bull_trend_pullback_signals)
        # Then 系統應拒絕發出 "SHORT" 開倉訊號以避免在多頭回檔中摸頂被嘎
        assert sig_side_2 is None

    def test_scenario_oversold_requires_candle_turn_confirmation(self):
        """Scenario: 超賣區 (RSI < 35) 必須確認 K 線止跌勾頭方可進場低接 (防盲目接飛刀)."""
        # Given 市場發生急跌導致 RSI 降至 31.0 (小於 35 超賣門檻)
        # When 最新市價仍低於或等於前一根 K 線收盤價 (瀑布破底進行中)
        falling_knife_signals = {
            "price": 74500.0,
            "rsi": 31.0,
            "ema21": 76500.0,
            "ema50": 77000.0,
            "prev_close": 74900.0,  # price <= prev_close (still crashing)
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        sig_knife, _ = evaluate_structural_entry("SWAP", 74500.0, falling_knife_signals)
        # Then 系統應拒絕發出 "LONG" 訊號以防止伸手接飛刀
        assert sig_knife is None

        # And 當最新市價高於前一根 K 線收盤價 (確認止跌勾頭反彈) 時
        rebound_confirmed_signals = {
            "price": 75100.0,
            "rsi": 31.0,
            "ema21": 76500.0,
            "ema50": 77000.0,
            "prev_close": 74900.0,  # price > prev_close (rebound tick confirmed)
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        sig_rebound, reason = evaluate_structural_entry("SWAP", 75100.0, rebound_confirmed_signals)
        # Then 系統應核准發出 "LONG" 超賣止跌反彈進場訊號
        assert sig_rebound == "LONG"
        assert "超賣" in reason and "止跌" in reason

    def test_scenario_fibonacci_golden_pocket_support_entry(self):
        """Scenario: 斐波那契黃金口袋 (0.50 ~ 0.65) 結構支撐回踩進場."""
        # Given 過去 48 小時波段高點為 78000、波段低點為 74000 且長線趨勢向上 (EMA21 >= EMA50)
        # 0.50 ~ 0.65 Golden Pocket from 78000 (range 4000) is [75400, 76000]
        gp_signals = {
            "price": 75800.0,
            "rsi": 43.0,
            "ema21": 76100.0,  # Price dipped slightly below EMA21 into Fib Golden Pocket!
            "ema50": 75500.0,
            "prev_close": 75650.0,
            "swing_high_48": 78000.0,
            "swing_low_48": 74000.0,
            "in_bull_golden_pocket": True,
            "in_bear_golden_pocket": False,
        }
        # When 最新市價回踩至 75800 且高於前一根收盤價
        sig_gp, reason = evaluate_structural_entry("SWAP", 75800.0, gp_signals)
        # Then 系統應識別出黃金口袋支撐並核准發出 "LONG" 進場訊號
        assert sig_gp == "LONG"
        assert "黃金口袋" in reason

    def test_scenario_stage_two_breakeven_ratchet_prevents_roundtrip_loss(self, tmp_path, monkeypatch):
        """Scenario: 持倉浮盈突破半程門檻後大幅回落時自動觸發階段二保本推移鎖利 (拒絕由盈轉虧)."""
        state_file = tmp_path / "autopilot_10x_be.json"
        jm = TradeJournalManager(
            db_path=str(tmp_path / "journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=10,
            capital=100.0,
            enable_ai_veto=False,
            dry_run=True,
            state_file=state_file,
            journal_mgr=jm,
        )
        engine.arm()

        # Given 10 倍槓桿合約持有一筆 "LONG" 倉位且全程停利目標為 +20.0% 保證金 (半程保本門檻為 +10.0%)
        entry_price = 76000.0
        margin = 50.0
        qty = (margin * 10) / entry_price
        engine.cash = 50.0
        open_res = engine.gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=qty,
            market_type="SWAP",
            position_side="LONG",
            leverage=10,
            stop_loss_price=entry_price * 0.985,
            simulation_price=entry_price,
        )
        assert open_res["result"] is True
        j_entry = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=entry_price,
            amount_btc=qty,
            margin_used=margin,
            leverage=10,
            raw_reason="雙均線多頭動量開倉",
            snapshot_dict={"price": entry_price},
            stop_loss_pct=15.0,
            trailing_pullback_pct=5.0,
        )
        # And 該倉位盤中最高浮動盈虧曾達到 +14.5% (突破 +10.0% 保本門檻，未達 +20.0% 移動停利門檻)
        engine.position = {
            "side": "LONG",
            "amount": qty,
            "amount_btc": qty,
            "entry_price": entry_price,
            "margin_used": margin,
            "highest_pnl_pct": 14.5,
            "entry_time": j_entry.entry_time,
            "entry_why": "雙均線多頭動量開倉",
            "ai_decision": "EXECUTE",
            "journal_id": j_entry.journal_id,
            "native_sl_price": entry_price * 0.985,
        }

        # When 市場行情突然反轉回落導致當前浮動盈虧降至 +1.2% ($76,091.20 -> +0.12% price = +1.2% margin)
        reversal_price = 76091.2
        monkeypatch.setattr(
            engine.gw,
            "fetch_ticker",
            lambda symbol, market_type="SWAP": {"price": reversal_price, "bid": reversal_price, "ask": reversal_price},
        )
        step_res = engine.step()

        # Then 系統必須立即執行保本推移市價平倉並撤銷雲端停損掛單
        assert step_res["action_taken"] == "BREAKEVEN_STOP"
        assert engine.position["side"] == "NONE"
        assert engine.cash > 100.0  # Total cash after closing is strictly profitable (> initial $100U)

        # And 結算實現盈虧必須為正數且交易日誌應記錄「保本推移鎖利」原因
        closed_entry = jm.get_entry(j_entry.journal_id)
        assert closed_entry is not None
        assert closed_entry.status == "CLOSED"
        assert closed_entry.pnl_usdt > 0
        assert "保本" in closed_entry.review.exit_reason
