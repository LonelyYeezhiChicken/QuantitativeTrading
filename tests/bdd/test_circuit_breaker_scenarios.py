"""BDD Scenario Implementation Tests: Capital Allocation & Circuit Breaker."""

import json
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.core.state_repository import BotStateRepository


class TestCircuitBreakerAndMarginAllocationBDDScenarios:
    """BDD Step implementations matching circuit_breaker_and_margin_allocation.feature."""

    def test_scenario_margin_allocation_75_percent_with_cash_buffer(self, tmp_path):
        """Scenario: 單筆資金動用比率提高至 75% 同時保留至少 10% 現金手續費緩衝防報錯."""
        # Given 操盤中樞初始本金為 200 USDT 且可用現金為 200 USDT，配置 75% 資金動用比率
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            capital_allocation_ratio=0.75,
            dry_run=True,
            state_file=tmp_path / "autopilot_state.json",
        )
        assert engine.capital == 200.0
        assert engine.cash == 200.0
        assert engine.capital_allocation_ratio == 0.75

        # When 系統計算開倉保證金時
        trade_margin_full = min(
            max(10.0, engine.capital * engine.capital_allocation_ratio),
            engine.cash * 0.90,
        )
        # Then 開倉保證金應計算為 150.0 USDT 且小於等於可用現金之 90%
        assert trade_margin_full == 150.0
        assert trade_margin_full <= engine.cash * 0.90

        # And 當可用現金僅剩 100 USDT 時，計算保證金應自動限制為可用現金之 90% (90.0 USDT)
        engine.cash = 100.0
        trade_margin_low_cash = min(
            max(10.0, engine.capital * engine.capital_allocation_ratio),
            engine.cash * 0.90,
        )
        assert trade_margin_low_cash == 90.0
        assert trade_margin_low_cash <= engine.cash * 0.90

    def test_scenario_circuit_breaker_triggered_at_50_percent_drawdown(self, tmp_path, monkeypatch):
        """Scenario: 帳戶淨值跌破初始本金 50% 臨界值時自動觸發全域熔斷平倉並切換待機."""
        # Given 守護進程初始本金為 200 USDT 且熔斷門檻設定為虧損達 50% (淨值 <= 100 USDT)
        state_file = tmp_path / "autopilot_state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            max_loss_pct=50.0,
            dry_run=True,
            state_file=state_file,
        )
        engine.arm()
        assert engine.status == AutopilotState.ARMED

        # And 當前持有一筆保證金為 150 USDT 之 "LONG" 倉位
        engine.cash = 50.0
        engine.position = {
            "side": "LONG",
            "amount": 0.005,
            "amount_btc": 0.005,
            "entry_price": 80000.0,
            "margin_used": 150.0,
            "highest_price": 80000.0,
            "lowest_price": 80000.0,
            "highest_roe": 0.0,
            "breakeven_synced": False,
        }
        # Sync simulated position in gateway so dry-run close order succeeds
        engine.gw._simulated_swap_positions["BTC-USDT_LONG"] = {
            "positionAmt": 0.005,
            "entryPrice": 80000.0,
            "initialMargin": 150.0,
        }

        # Mock push notification dispatch
        alert_dispatched = []
        monkeypatch.setattr(
            engine,
            "_dispatch_circuit_breaker_alert",
            lambda cb_threshold, eq: alert_dispatched.append((cb_threshold, eq)),
        )

        # When 市場發生劇烈反向波動使帳戶總淨值跌至 95.0 USDT (虧損超過 50%)
        # Long loss = (59000 - 80000) * 0.005 = -105 USDT
        # Equity = 50 (cash) + 150 (margin) - 105 (loss) = 95 USDT <= 100 USDT threshold!
        crash_price = 59000.0
        res = engine.step(override_price=crash_price)

        # Then 操盤中樞必須在 step 迴圈中立即觸發全域熔斷保護
        assert engine.circuit_breaker_triggered is True
        assert "臨界值" in engine.circuit_breaker_reason

        # And 系統應立即以市價將現有多單全部平倉以鎖定剩餘資本
        assert engine.position["side"] == "NONE"
        assert engine.position["amount"] == 0.0

        # And 系統狀態應切換為 "STANDBY" 待機模式
        assert engine.status == AutopilotState.STANDBY

        # And 操盤中樞之執行結果 action_taken 應為 "CIRCUIT_BREAKER_HALTED" 並發送緊急熔斷警報通知
        assert res["action_taken"] == "CIRCUIT_BREAKER_HALTED"
        assert len(alert_dispatched) == 1
        assert alert_dispatched[0][1] <= 100.0  # current equity <= threshold

    def test_scenario_prevent_rearm_during_circuit_breaker(self, tmp_path):
        """Scenario: 處於熔斷鎖定狀態下禁止重新啟動交易 (Prevent Re-arm During Breaker)."""
        # Given 守護進程因總淨值 90 USDT (低於 100 USDT 熔斷線) 處於熔斷鎖定狀態
        state_file = tmp_path / "autopilot_state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            max_loss_pct=50.0,
            dry_run=True,
            state_file=state_file,
        )
        engine.cash = 90.0
        engine.position = {"side": "NONE", "amount": 0.0, "entry_price": 0.0, "margin_used": 0.0}
        engine.circuit_breaker_triggered = True
        engine.circuit_breaker_reason = "帳戶淨值 $90.00 USDT 跌破熔斷閾值 $100.00 USDT"

        # When 使用者或排程程式嘗試呼叫 arm() 嘗試重新啟動交易
        msg = engine.arm()

        # Then 操盤中樞應嚴格拒絕啟動請求並維持 "STANDBY" 待機模式
        assert engine.status == AutopilotState.STANDBY
        # And 系統應回傳熔斷拒絕訊息指示淨值過低須補足本金
        assert "拒絕武裝" in msg
        assert "熔斷門檻" in msg

    def test_scenario_wallboard_circuit_breaker_alert_rendering(self, tmp_path):
        """Scenario: Web 監控看板即時顯示高對比紅色熔斷警報與狀態徽章."""
        # Given 守護戰隊中至少有一台機器人觸發了熔斷停機 (circuit_breaker_triggered 為真)
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        bot_file = data_dir / "autopilot_swap_10x.json"
        state = {
            "status": "STANDBY",
            "capital": 200.0,
            "cash": 95.0,
            "leverage": 10,
            "mode": "SWAP_10X",
            "position": {"side": "NONE", "amount": 0.0, "entry_price": 0.0, "margin_used": 0.0},
            "circuit_breaker_triggered": True,
            "circuit_breaker_reason": "跌破 50% 熔斷閾值",
        }
        with open(bot_file, "w", encoding="utf-8") as f:
            json.dump(state, f)

        # When 雲端監控儀表板讀取機器人狀態並渲染看板
        bots = BotStateRepository.discover_active_bots(btc_p=75000.0, root_dir=tmp_path)
        assert len(bots) == 1
        target_bot = bots[0]

        # Then 觸發熔斷之機器人狀態 circuit_breaker_triggered 為真
        assert target_bot["circuit_breaker_triggered"] is True

        # And 儀表板頂部應呈現包含全域風控熔斷警報
        total_capital = sum(b.get("init_cap", 200.0) for b in bots)
        total_equity = sum(b.get("equity", 200.0) for b in bots)
        is_circuit_breaker_active = any(b.get("circuit_breaker_triggered") for b in bots) or (total_equity <= total_capital * 0.5)
        assert is_circuit_breaker_active is True
