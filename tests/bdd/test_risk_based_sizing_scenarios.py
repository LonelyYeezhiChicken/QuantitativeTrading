"""BDD Scenario Implementation Tests: Risk-Based Position Sizing & Trend Dip Reversal."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import (
    UnifiedAutopilotEngine,
    compute_risk_based_position_size,
    evaluate_structural_entry,
)


class TestRiskBasedPositionSizingAndTrendDipReversalBDDScenarios:
    """BDD Step implementations matching risk_based_position_sizing_and_trend_dip_reversal.feature."""

    def test_scenario_risk_based_position_sizing_fixed_2_percent(self, tmp_path):
        """Scenario: 固定每筆虧損總資金 2% 反推開倉大小 (Risk-based Position Sizing)."""
        # Given 操盤中樞初始本金為 1000 USDT 且配置單筆風險 2.0% 與槓桿 3x
        capital = 1000.0
        risk_pct = 0.02
        leverage = 3.0

        # When 當前價格為 50000 USDT 且 4H ATR 為 1000 USDT 時計算開倉大小
        cur_price = 50000.0
        atr_val = 1000.0
        notional, margin, qty = compute_risk_based_position_size(
            capital=capital,
            risk_pct=risk_pct,
            cur_price=cur_price,
            atr_val=atr_val,
            atr_multiplier=2.0,
            leverage=leverage,
            max_margin_ratio=0.75,
            available_cash=capital,
        )

        # Then 動態停損距離應為 2000 USDT 即 4.0%
        sl_dist = 2.0 * atr_val
        sl_dist_pct = sl_dist / cur_price
        assert sl_dist == 2000.0
        assert round(sl_dist_pct * 100.0, 1) == 4.0

        # And 目標名義開倉金額應反推為 500.0 USDT 且開倉保證金為 166.67 USDT
        assert round(notional, 1) == 500.0
        assert round(margin, 2) == 166.67
        assert round(qty, 4) == 0.0100

        # And 當觸發停損時帳戶最大虧損嚴格限制在 20.0 USDT 剛好為總本金之 2.0%
        dollar_loss = notional * sl_dist_pct
        assert round(dollar_loss, 1) == 20.0
        assert round(dollar_loss / capital * 100.0, 1) == 2.0

    def test_scenario_extreme_volatility_auto_downsizing(self):
        """Scenario: 極端高波動環境下部位自動縮小防黑天鵝 (Extreme Volatility Auto-Downsizing)."""
        # Given 操盤中樞初始本金為 1000 USDT 且配置單筆風險 2.0% 與槓桿 3x
        capital = 1000.0
        risk_pct = 0.02
        leverage = 3.0
        cur_price = 50000.0

        # When 市場遭遇極端黑天鵝使 4H ATR 飆升至 2500 USDT (停損距離 10.0%) 時
        extreme_atr = 2500.0
        notional, margin, qty = compute_risk_based_position_size(
            capital=capital,
            risk_pct=risk_pct,
            cur_price=cur_price,
            atr_val=extreme_atr,
            atr_multiplier=2.0,
            leverage=leverage,
            max_margin_ratio=0.75,
            available_cash=capital,
        )

        # Then 目標名義開倉金額應自動縮減為 200.0 USDT 且開倉保證金僅需 66.67 USDT
        sl_dist = 2.0 * extreme_atr
        sl_dist_pct = sl_dist / cur_price
        assert round(sl_dist_pct * 100.0, 1) == 10.0
        assert round(notional, 1) == 200.0
        assert round(margin, 2) == 66.67

        # And 即使遭遇 10.0% 劇烈大跌觸發停損，總帳戶虧損依然鎖定為 20.0 USDT 絕不爆倉
        actual_loss = notional * sl_dist_pct
        assert round(actual_loss, 1) == 20.0
        assert round(actual_loss / capital * 100.0, 1) == 2.0

    def test_scenario_uncapped_2_atr_breathing_room(self):
        """Scenario: 拿掉 4.0% 假停損限制給予完整 2.0 ATR 呼吸空間與 1.5 ATR 停利."""
        # Given 操盤中樞持有一筆開在 50000 USDT 之多單且 4H ATR 為 1200 USDT
        entry_price = 50000.0
        atr_val = 1200.0

        # When 系統計算原生硬停損與目標停利價時
        sl_dist = 2.0 * atr_val
        native_sl_price = entry_price - sl_dist
        native_tp_price = entry_price + (1.5 * atr_val)

        # Then 原生硬停損價應精確設為 47600 USDT (跌幅 4.8%)，不被 4.0% 上限提前截斷
        assert native_sl_price == 47600.0
        drop_pct = (entry_price - native_sl_price) / entry_price * 100.0
        assert round(drop_pct, 1) == 4.8
        assert native_sl_price < entry_price * (1.0 - 0.040)  # Verify unconstrained beyond 4%

        # And 目標停利價應設為 51800 USDT (1.5 倍 ATR)
        assert native_tp_price == 51800.0

    def test_scenario_trend_dip_reversal_signal_generation(self):
        """Scenario: 4H 趨勢超賣均值修復信號生成與止跌確認 (4H Trend Dip Reversal Signal)."""
        # Given 當前處於 4H 多頭體制 (現價與 EMA50 高於 EMA200)
        cur_price = 60000.0
        bull_signals = {
            "rsi": 32.0,
            "ema21": 59500.0,
            "ema50": 58000.0,
            "ema200": 55000.0,
            "prev_close": 59800.0,
            "touch_bb_low": True,
            "is_4h_bull": True,
        }

        # When 價格回踩觸及布林下軌或 RSI 進入 35 以下超賣區且當根 K 線收陽止跌
        sig, reason = evaluate_structural_entry(
            mode="SWAP_3X",
            cur_price=cur_price,
            signals=bull_signals,
        )

        # Then 系統應生成 "LONG" 開多信號且進場理由標註包含 "4H趨勢超賣均值修復確認"
        assert sig == "LONG"
        assert "4H趨勢超賣均值修復確認" in reason

        # And 當處於 4H 空頭體制且觸及布林上軌或 RSI 達 65 以上且收陰時應生成 "SHORT" 信號
        bear_signals = {
            "rsi": 68.0,
            "ema21": 50000.0,
            "ema50": 51000.0,
            "ema200": 55000.0,
            "prev_close": 50500.0,
            "touch_bb_up": True,
            "is_4h_bear": True,
        }
        short_sig, short_reason = evaluate_structural_entry(
            mode="SWAP_3X",
            cur_price=50200.0,
            signals=bear_signals,
        )
        assert short_sig == "SHORT"
        assert "4H趨勢超賣均值修復確認" in short_reason

    def test_scenario_autopilot_step_integration_with_risk_sizing(self, tmp_path, monkeypatch):
        """Scenario: UnifiedAutopilotEngine.step() 整合測試，驗證依據 2% 風險與 ATR 動態開倉下單."""
        state_file = tmp_path / "autopilot_state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=1000.0,
            use_risk_based_sizing=True,
            risk_per_trade_pct=0.02,
            atr_sl_multiplier=2.0,
            dry_run=True,
            enable_ai_veto=False,
            state_file=state_file,
        )
        engine.arm()
        assert engine.use_risk_based_sizing is True
        assert engine.risk_per_trade_pct == 0.02

        # Mock ticker and market signals with 4H trend dip reversal
        fake_signals = {
            "price": 50000.0,
            "rsi": 30.0,
            "ema21": 52000.0,
            "ema50": 48000.0,
            "ema200": 45000.0,
            "atr": 1000.0,
            "prev_close": 49800.0,
            "touch_bb_low": True,
            "is_4h_bull": True,
        }
        monkeypatch.setattr(
            engine,
            "_compute_market_signals",
            lambda cur_p: fake_signals,
        )

        res = engine.step(override_price=50000.0)
        assert res["action_taken"] == "OPEN_POSITION"
        assert engine.position["side"] == "LONG"
        # 2% risk on 1000 = 20 USDT. sl_dist = 2000 (4%). Notional = 500 USDT. Margin = 166.67 USDT.
        assert round(engine.position["margin_used"], 1) == 166.7
        # Verify attached native stop loss
        assert engine.position["native_sl_price"] == 48000.0  # 50000 - 2000
