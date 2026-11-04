"""BDD Scenario Implementation Tests: Autopilot runtime safety (autopilot_runtime_safety.feature)."""

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import (
    AutopilotState,
    UnifiedAutopilotEngine,
    evaluate_structural_entry,
)
from packages.execution import BingXGateway
from packages.journal import TradeJournalManager

ENTRY_PRICE = 100000.0
MARGIN = 50.0
LEVERAGE = 3
QTY = MARGIN * LEVERAGE / ENTRY_PRICE
NEUTRAL_PRICE = 100100.0       # +0.1% price, no exit rule fires
STOP_PRICE = 98000.0           # -2.0% price = -6% margin on 3x (hard stop is -4.5%)


class _StubAI:
    """Offline AI agent so scenarios never reach a local Ollama server."""

    def evaluate_signal_choice(self, *args, **kwargs) -> Dict[str, Any]:
        return {"choice": "EXECUTE", "reason": "stub"}

    def summarize_trade_journal(self, raw_record: Dict[str, Any]) -> Dict[str, Any]:
        return {}


def _journal(tmp_path: Path) -> TradeJournalManager:
    return TradeJournalManager(db_path=str(tmp_path / "journal_db.json"), journals_dir=str(tmp_path / "journals"))


def _engine(tmp_path: Path, jm: TradeJournalManager, gateway: Any = None, **kwargs) -> UnifiedAutopilotEngine:
    gw = gateway or BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False)
    return UnifiedAutopilotEngine(
        mode="SWAP_3X",
        symbol="BTC/USDT",
        leverage=LEVERAGE,
        capital=100.0,
        enable_ai_veto=False,
        dry_run=True,
        state_file=tmp_path / "autopilot_state.json",
        journal_mgr=jm,
        gateway=gw,
        ai_agent=_StubAI(),
        **kwargs,
    )


def _open_long(engine: UnifiedAutopilotEngine) -> str:
    """Open a simulated LONG on the dry-run gateway and record it on the engine + journal."""
    res = engine.gw.create_order(
        symbol="BTC/USDT", side="BUY", order_type="MARKET", size=QTY, market_type="SWAP",
        position_side="LONG", leverage=LEVERAGE, simulation_price=ENTRY_PRICE,
    )
    assert res["result"] is True
    engine._record_open_position("LONG", QTY, ENTRY_PRICE, MARGIN, "BDD 開倉", "EXECUTE", ENTRY_PRICE * 0.985, {})
    return engine.position["journal_id"]


class TestAutopilotRuntimeSafetyBDDScenarios:
    """BDD Step implementations matching autopilot_runtime_safety.feature."""

    def test_scenario_close_exception_does_not_crash_and_is_retried(self, tmp_path, monkeypatch):
        """Scenario: 平倉請求拋出例外時引擎不崩潰並交由對帳決定結果."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        engine.arm()
        journal_id = _open_long(engine)

        # When 平倉市價單因斷網或交易所拒單拋出例外
        real_create = engine.gw.create_order

        def _raise(*args, **kwargs):
            raise RuntimeError("All BingX domains failed. Last error: timeout")

        monkeypatch.setattr(engine.gw, "create_order", _raise)
        # Then 引擎不得拋出例外 (previously UnboundLocalError on close_res)
        assert engine._close_position(STOP_PRICE, "BDD 停損") is False
        # And 本機持倉保留並記錄無訂單編號之待確認平倉
        assert engine.position["side"] == "LONG"
        assert engine.pending_order["action"] == "CLOSE"
        assert engine.pending_order["order_id"] == ""

        # And 下一個心跳查詢交易所部位仍在時解除待確認並允許風控重新平倉
        monkeypatch.setattr(engine.gw, "create_order", real_create)
        res = engine.step(override_price=STOP_PRICE)
        assert res["action_taken"] == "ORDER_PENDING"
        assert engine.pending_order is None
        assert engine.position["side"] == "LONG"

        res = engine.step(override_price=STOP_PRICE)
        assert res["action_taken"] == "STOP_LOSS"
        assert engine.position["side"] == "NONE"
        assert jm.get_entry(journal_id).status == "CLOSED"

    def test_scenario_untracked_close_settles_when_exchange_is_flat(self, tmp_path, monkeypatch):
        """Scenario: 無訂單編號之待確認平倉在交易所已歸零時完成結算."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        journal_id = _open_long(engine)
        engine.pending_order = {"action": "CLOSE", "order_id": "", "quantity": QTY, "price": STOP_PRICE, "reason": "BDD 停損"}

        # When 對帳查詢交易所該方向部位已歸零
        monkeypatch.setattr(engine.gw, "get_positions", lambda symbol=None: [])
        res = engine.step(override_price=STOP_PRICE)

        # Then 引擎應完成本機平倉並將權威日誌更新為 "CLOSED"
        assert res["action_taken"] == "ORDER_RESOLVED"
        assert engine.position["side"] == "NONE"
        assert engine.pending_order is None
        assert jm.get_entry(journal_id).status == "CLOSED"

    def test_scenario_ack_without_order_id_never_freezes_engine(self, tmp_path, monkeypatch):
        """Scenario: 交易所回應成功但缺少訂單編號時不得永久凍結."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        engine.arm()
        price = 100000.0
        monkeypatch.setattr(engine, "_compute_market_signals", lambda p: {
            "price": p, "rsi": 50.0, "ema21": p * 0.999, "ema50": p * 0.995, "atr": p * 0.01,
            "prev_close": p * 0.998, "in_bull_golden_pocket": False, "in_bear_golden_pocket": False,
        })
        # Given 交易所對開倉請求回應 code 0 但未提供 orderId
        monkeypatch.setattr(engine.gw, "create_order", lambda *a, **k: {"code": 0, "result": False, "data": {}})
        res = engine.step(override_price=price)
        assert res["action_taken"] == "ORDER_PENDING"
        assert engine.pending_order["order_id"] == ""

        # When 交易所查無對應部位 (the dry-run gateway holds no position)
        res = engine.step(override_price=price)
        # Then 待確認開倉應被解除，引擎恢復正常心跳
        assert engine.pending_order is None
        assert engine.position["side"] == "NONE"

    def test_scenario_vst_gateway_is_reconciled_even_when_engine_dry_run(self, tmp_path, monkeypatch):
        """Scenario: BingX VST 模擬盤即使引擎 dry_run 為 True 仍須與交易所對帳."""
        jm = _journal(tmp_path)
        gw = BingXGateway(api_key="k", api_secret="s", dry_run=True, use_vst=True,
                          default_market_type="SWAP", enable_ws=False)
        monkeypatch.setattr(gw, "set_leverage", lambda *a, **k: True)
        engine = _engine(tmp_path, jm, gateway=gw)

        # Given 網關路由至 BingX VST 且引擎以預設 dry_run=True 建立
        assert gw.is_dry_run is False
        assert engine.dry_run is True
        assert engine.is_exchange_backed is True

        # And 本機持有 "LONG" 部位但交易所原生停損已於雲端平倉
        entry = jm.on_trade_open(symbol="BTC/USDT", market_type="SWAP", side="LONG", entry_price=ENTRY_PRICE,
                                 amount_btc=QTY, margin_used=MARGIN, leverage=LEVERAGE, raw_reason="BDD VST")
        engine.position = {
            "side": "LONG", "amount_btc": QTY, "entry_price": ENTRY_PRICE, "margin_used": MARGIN,
            "highest_pnl_pct": 0.0, "journal_id": entry.journal_id,
        }
        engine.cash = 50.0
        monkeypatch.setattr(gw, "get_positions", lambda symbol=None: [])
        monkeypatch.setattr(gw, "fetch_ticker", lambda *a, **k: {"price": 98500.0})
        monkeypatch.setattr(gw, "cancel_all_orders", lambda *a, **k: True)

        # When 引擎執行心跳
        res = engine.step(override_price=98500.0)

        # Then 本機持倉歸零且日誌標註原生停損
        assert res["action_taken"] == "NATIVE_STOP_LOSS"
        assert engine.position["side"] == "NONE"
        closed = jm.get_entry(entry.journal_id)
        assert closed.status == "CLOSED"
        assert "交易所原生硬停損觸發平倉" in closed.review.exit_reason

    def test_scenario_external_standby_disarms_running_engine(self, tmp_path):
        """Scenario: 另一進程下達 STANDBY 指令時運行中的操盤中樞於下一個心跳解除武裝."""
        jm = _journal(tmp_path)
        # Process B (e.g. `just standby`) was created while the state file was still flat.
        engine_b = _engine(tmp_path, jm)
        engine_a = _engine(tmp_path, jm)
        engine_a.arm()
        _open_long(engine_a)
        assert engine_a.status == AutopilotState.ARMED

        # When 另一進程 B 以相同狀態檔執行 disarm
        engine_b.disarm()

        # Then B 不得以其過期記憶體狀態覆寫 A 的持倉
        persisted = UnifiedAutopilotEngine(
            mode="SWAP_3X", leverage=LEVERAGE, capital=100.0, dry_run=True,
            state_file=tmp_path / "autopilot_state.json", journal_mgr=jm,
            gateway=BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False),
            ai_agent=_StubAI(), enable_ai_veto=False,
        )
        assert persisted.position["side"] == "LONG"

        # And A 於下一個心跳切換為 "STANDBY"
        engine_a.step(override_price=NEUTRAL_PRICE)
        assert engine_a.status == AutopilotState.STANDBY
        assert engine_a.position["side"] == "LONG"

    def test_scenario_stale_control_command_ignored_on_startup(self, tmp_path):
        """Scenario: 啟動前遺留之控制指令不得影響新進程."""
        jm = _journal(tmp_path)
        # Given 控制檔已存在一筆舊的 "STANDBY" 指令
        _engine(tmp_path, jm).send_control_command("STANDBY")

        # When 新進程啟動並手動武裝
        engine = _engine(tmp_path, jm)
        engine.arm()
        assert engine._apply_external_controls() is None

        # Then 新進程維持 "ARMED" 不被舊指令解除
        assert engine.status == AutopilotState.ARMED

    def test_scenario_dashboard_emergency_stop_executed_by_daemon(self, tmp_path):
        """Scenario: 控制台緊急全平指令由運行中的操盤中樞執行."""
        jm = _journal(tmp_path)
        daemon = _engine(tmp_path, jm)
        daemon.arm()
        journal_id = _open_long(daemon)

        # When 控制台以相同狀態檔送出緊急全平指令
        dashboard = _engine(tmp_path, jm)
        msg = dashboard.request_emergency_stop()
        assert "緊急全平" in msg

        # Then A 於下一個心跳完成市價平倉並切換為 "STANDBY"
        daemon.step(override_price=NEUTRAL_PRICE)
        assert daemon.status == AutopilotState.STANDBY
        assert daemon.position["side"] == "NONE"
        assert jm.get_entry(journal_id).status == "CLOSED"

    def test_scenario_concurrent_steps_submit_single_close(self, tmp_path, monkeypatch):
        """Scenario: 多執行緒同時觸發心跳時僅送出一張平倉單."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        engine.arm()
        _open_long(engine)
        monkeypatch.setattr(engine, "_compute_market_signals", lambda p: {
            "price": p, "rsi": 50.0, "ema21": p, "ema50": p, "atr": p * 0.01, "prev_close": p,
            "in_bull_golden_pocket": False, "in_bear_golden_pocket": False,
        })

        calls: List[Dict[str, Any]] = []
        real_create = engine.gw.create_order

        def _slow_create(*args, **kwargs):
            calls.append(kwargs)
            time.sleep(0.3)
            return real_create(*args, **kwargs)

        monkeypatch.setattr(engine.gw, "create_order", _slow_create)

        # When 兩個執行緒同時呼叫 step
        errors: List[BaseException] = []

        def _run():
            try:
                engine.step(override_price=STOP_PRICE)
            except BaseException as exc:  # pragma: no cover - surfaced by the assertion below
                errors.append(exc)

        threads = [threading.Thread(target=_run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Then 交易所僅收到一張平倉市價單
        assert not errors
        assert len(calls) == 1
        assert calls[0]["side"] == "SELL"
        assert engine.position["side"] == "NONE"

        # And 事件驅動心跳在引擎忙碌時直接略過而不阻塞推播執行緒
        held = threading.Event()
        release = threading.Event()

        def _hold_lock():
            with engine._step_lock:
                held.set()
                release.wait(timeout=5)

        holder = threading.Thread(target=_hold_lock)
        holder.start()
        held.wait(timeout=5)

        class _Ev:
            symbol = "BTC/USDT"
            price = NEUTRAL_PRICE

        started = time.monotonic()
        assert engine.on_ticker_event(_Ev()) is None
        assert time.monotonic() - started < 0.5
        release.set()
        holder.join(timeout=5)

    def test_scenario_cooldown_survives_restart(self, tmp_path):
        """Scenario: 平倉冷卻期在進程重啟後仍然生效."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        _open_long(engine)
        # Given 引擎剛完成一筆平倉
        assert engine._close_position(NEUTRAL_PRICE, "BDD 平倉") is True
        assert engine.closed_trades

        # When 進程重新啟動
        restarted = _engine(tmp_path, jm)

        # Then 最近平倉紀錄應自磁碟還原且 15 分鐘冷卻期持續生效
        assert restarted.closed_trades
        assert restarted.closed_trades[0]["symbol"] == "BTC/USDT"
        signal, reason = evaluate_structural_entry(
            restarted.mode, NEUTRAL_PRICE,
            {"rsi": 50.0, "ema21": NEUTRAL_PRICE, "ema50": NEUTRAL_PRICE, "prev_close": NEUTRAL_PRICE - 1},
            history=restarted.closed_trades,
        )
        assert signal is None
        assert "冷卻" in reason

    def test_scenario_status_peek_is_read_only(self, tmp_path):
        """Scenario: 狀態查詢為唯讀不得改寫共享狀態."""
        jm = _journal(tmp_path)
        engine = _engine(tmp_path, jm)
        _open_long(engine)
        engine.pending_order = {"action": "CLOSE", "order_id": "", "quantity": QTY, "price": STOP_PRICE, "reason": "x"}
        engine.save_state()
        state_file = tmp_path / "autopilot_state.json"
        before = state_file.read_bytes()

        # When 執行 peek 狀態查詢 (as `just status` does from a separate process)
        observer = _engine(tmp_path, jm)
        observer.load_state(restore_status=True)
        snap = observer.peek(override_price=STOP_PRICE)

        # Then 狀態檔與待確認訂單均不得被修改
        assert snap["position_side"] == "LONG"
        assert snap["pending_order"] is True
        assert state_file.read_bytes() == before
        assert observer.pending_order["action"] == "CLOSE"
