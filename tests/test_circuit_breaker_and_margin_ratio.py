"""Unit tests for Capital Allocation Ratio (75%) and Global Circuit Breaker (50% Max Loss)."""

import json
from pathlib import Path
import pytest

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.core.state_repository import BotStateRepository


class TestCircuitBreakerAndMarginRatio:
    """Validate 75% margin allocation and 50% loss circuit breaker."""

    def test_default_allocation_and_circuit_breaker_parameters(self, tmp_path):
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            dry_run=True,
            state_file=tmp_path / "state.json",
        )
        assert engine.capital_allocation_ratio == 0.75
        assert engine.max_loss_pct == 50.0
        assert engine.circuit_breaker_triggered is False
        assert engine.circuit_breaker_reason == ""

    def test_margin_calculation_scales_to_75_percent(self, tmp_path):
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            capital_allocation_ratio=0.75,
            dry_run=True,
            state_file=tmp_path / "state.json",
        )
        # Margin should be 200 * 0.75 = 150
        margin = min(max(10.0, engine.capital * engine.capital_allocation_ratio), engine.cash * 0.90)
        assert margin == 150.0

    def test_state_persistence_preserves_circuit_breaker_state(self, tmp_path):
        state_file = tmp_path / "state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=10,
            capital=200.0,
            capital_allocation_ratio=0.75,
            max_loss_pct=50.0,
            dry_run=True,
            state_file=state_file,
        )
        engine.circuit_breaker_triggered = True
        engine.circuit_breaker_reason = "帳戶淨值 $92.50 USDT 跌破熔斷閾值 $100.00 USDT"
        engine.save_state()

        # Load back into fresh engine
        engine2 = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=10,
            capital=100.0,
            dry_run=True,
            state_file=state_file,
        )
        engine2.load_state()

        assert engine2.circuit_breaker_triggered is True
        assert engine2.circuit_breaker_reason == "帳戶淨值 $92.50 USDT 跌破熔斷閾值 $100.00 USDT"
        assert engine2.capital_allocation_ratio == 0.75
        assert engine2.max_loss_pct == 50.0

    def test_circuit_breaker_triggers_when_empty_position_and_cash_below_threshold(self, tmp_path):
        state_file = tmp_path / "state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            max_loss_pct=50.0,
            dry_run=True,
            state_file=state_file,
        )
        engine.arm()
        engine.cash = 80.0  # Already < 200 * 0.5 = 100
        engine.position = {"side": "NONE", "amount": 0.0, "entry_price": 0.0, "margin_used": 0.0}

        res = engine.step(override_price=70000.0)
        assert engine.circuit_breaker_triggered is True
        assert engine.status == AutopilotState.STANDBY
        assert res["action_taken"] == "CIRCUIT_BREAKER_HALTED"

    def test_circuit_breaker_alert_sent_only_once(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=3,
            capital=200.0,
            max_loss_pct=50.0,
            dry_run=True,
            state_file=state_file,
        )
        engine.arm()
        engine.cash = 80.0
        engine.position = {"side": "NONE", "amount": 0.0, "entry_price": 0.0, "margin_used": 0.0}

        calls = []
        monkeypatch.setattr(engine, "_dispatch_circuit_breaker_alert", lambda *args: calls.append(args))

        engine.step(override_price=70000.0)
        assert len(calls) == 1

        # Second step should not re-dispatch alert
        engine.step(override_price=70000.0)
        assert len(calls) == 1
