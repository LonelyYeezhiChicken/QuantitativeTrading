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

    def test_scenario_cloud_breakeven_stop_order_sync_for_open_positions(self, tmp_path, monkeypatch):
        """Scenario: 持倉浮盈突破半程保本門檻時自動將雲端 STOP_MARKET 掛單與日誌停損價同步上移至成本價上方 (雲端套保同步)."""
        state_file = tmp_path / "autopilot_10x_cloud_be.json"
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

        # Given 10 倍槓桿合約持有一筆開倉價為 76000 的 "LONG" 倉位且初始停損價為 74860 (-15.0% 保證金)
        entry_price = 76000.0
        initial_sl_price = 74860.0
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
            stop_loss_price=initial_sl_price,
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
            raw_reason="10x 順勢開多",
            snapshot_dict={"price": entry_price},
            stop_loss_pct=15.0,
            trailing_pullback_pct=5.0,
        )
        assert j_entry.risk_plan.stop_loss_price == pytest.approx(initial_sl_price, rel=1e-3)

        engine.position = {
            "side": "LONG",
            "amount": qty,
            "amount_btc": qty,
            "entry_price": entry_price,
            "margin_used": margin,
            "highest_pnl_pct": 0.0,
            "entry_time": j_entry.entry_time,
            "entry_why": "10x 順勢開多",
            "ai_decision": "EXECUTE",
            "journal_id": j_entry.journal_id,
            "native_sl_price": initial_sl_price,
            "breakeven_synced": False,
        }

        # When 市場行情上漲至 77200 使浮動盈虧達到 +15.79% (突破 +10.0% 半程保本門檻，且繼續持倉中)
        rally_price = 77200.0
        monkeypatch.setattr(
            engine.gw,
            "fetch_ticker",
            lambda symbol, market_type="SWAP": {"price": rally_price, "bid": rally_price, "ask": rally_price},
        )
        step_res = engine.step()

        # Then 系統應自動向交易所發送更新後的雲端 STOP_MARKET 保本停損單且新停損觸發價必須高於開倉價 76000
        assert engine.position["side"] == "LONG"
        assert engine.position.get("breakeven_synced") is True
        new_sl_price = engine.position.get("native_sl_price", 0.0)
        assert new_sl_price > entry_price

        # And 權威交易日誌庫與持倉狀態中的 stop_loss_price 必須同步更新為該保本鎖利價位
        updated_entry = jm.get_entry(j_entry.journal_id)
        assert updated_entry is not None
        assert updated_entry.risk_plan.stop_loss_price == pytest.approx(new_sl_price, rel=1e-4)
        assert updated_entry.risk_plan.max_loss_usdt == 0.0

    def test_scenario_max_ema21_bias_blocks_overextended_top_chasing(self):
        """Scenario: 均線正乖離率超過 +0.45% 時禁止追高突破並強制等待回踩貼近 EMA21 (防針尖追高護欄)."""
        # Given 市場處於雙均線多頭排列 (EMA21 為 77320、EMA50 為 76800) 且 RSI 為 59.5 位於動能區間
        # When 最新市價急拉至 78114 使 EMA21 正乖離率高達 +1.03% (重現 055114_LONG 針尖追高情境)
        overextended_signals = {
            "price": 78114.0,
            "rsi": 59.5,
            "ema21": 77320.65,
            "ema50": 76800.0,
            "prev_close": 77900.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        sig_chase, chase_reason = evaluate_structural_entry("SWAP", 78114.0, overextended_signals)
        # Then 系統應拒絕發出 "LONG" 開倉訊號並回傳均線正乖離過大禁止追高之原因
        assert sig_chase is None
        assert "乖離" in chase_reason and "追高" in chase_reason

        # And 當市價回踩收斂至 77450 (EMA21 正乖離率降至 +0.17% 小於 +0.45%) 且 RSI 為 59.0 時
        pullback_signals = {
            "price": 77450.0,
            "rsi": 59.0,
            "ema21": 77320.65,
            "ema50": 76800.0,
            "prev_close": 77380.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }
        sig_ok, ok_reason = evaluate_structural_entry("SWAP", 77450.0, pullback_signals)
        # Then 系統應核准發出 "LONG" 順勢進場訊號
        assert sig_ok == "LONG"
        assert "多頭排列" in ok_reason or "順勢" in ok_reason

    def test_scenario_post_exit_cooldown_prevents_immediate_rechase(self):
        """Scenario: 平倉出場後 15 分鐘冷卻期內禁止原地重新追單 (Post-Exit Cooldown Guard)."""
        from datetime import datetime, timezone

        # Given 帳戶剛在 "2026-11-04 05:49:00 UTC" 因動態移動停利於 77764 平倉出場一筆 "LONG" 部位
        recent_history = [
            {
                "closed_at": "2026-11-04 05:49:00 UTC",
                "side": "LONG",
                "entry_price": 77278.2,
                "exit_price": 77764.0,
                "pnl_usdt": 15.72,
                "pnl_pct": 31.43,
                "reason": "動態移動停利 (高點 +36.71% 回撤 5.28%, 鎖定 +31.43%)",
            }
        ]
        valid_signals = {
            "price": 77420.0,
            "rsi": 54.0,
            "ema21": 77320.0,
            "ema50": 76800.0,
            "prev_close": 77350.0,
            "in_bull_golden_pocket": False,
            "in_bear_golden_pocket": False,
        }

        # When 僅間隔 2 分鐘 ("2026-11-04 05:51:00 UTC"，未滿 15 分鐘冷卻期) 市場出現多頭候選訊號
        now_2min_later = datetime(2026, 11, 4, 5, 51, 0, tzinfo=timezone.utc)
        sig_cooldown, cooldown_reason = evaluate_structural_entry(
            "SWAP",
            77420.0,
            valid_signals,
            history=recent_history,
            now_utc=now_2min_later,
            cooldown_minutes=15,
        )
        # Then 系統應啟動平倉後冷卻保護並拒絕立即重新開倉
        assert sig_cooldown is None
        assert "冷卻" in cooldown_reason

        # And 當時間推進至 "2026-11-04 06:06:00 UTC" (已滿 15 分鐘冷卻期) 且市價貼近 EMA21 出現合格訊號時
        now_17min_later = datetime(2026, 11, 4, 6, 6, 0, tzinfo=timezone.utc)
        sig_after_cooldown, reason_after = evaluate_structural_entry(
            "SWAP",
            77420.0,
            valid_signals,
            history=recent_history,
            now_utc=now_17min_later,
            cooldown_minutes=15,
        )
        # Then 系統應解除冷卻限制並核准發出 "LONG" 開倉訊號
        assert sig_after_cooldown == "LONG"
        assert "順勢" in reason_after
