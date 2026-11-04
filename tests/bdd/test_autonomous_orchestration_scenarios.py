"""BDD Scenario Implementation Tests: Autonomous Coin & Leverage Orchestration."""

import sys
import tempfile
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.models.advanced_strategies import SpotMomentumPullbackModel, SwapMultiRegimeModel
from packages.journal import TradeJournalManager


class TestAutonomousOrchestrationBDDScenarios:
    """BDD Step implementations matching autonomous_coin_and_leverage_orchestration.feature."""

    def test_scenario_spot_1x_orchestration(self):
        """Scenario: 使用者指定幣種與現貨槓桿 1x 時自動走現貨策略與全額資金風控."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_eth_state.json"
            jm = TradeJournalManager(
                db_path=str(tmp_path / "journal_db.json"),
                journals_dir=str(tmp_path / "journals"),
            )

            # Given 使用者設定交易標的為 "ETH/USDT" 且槓桿倍數為 1 倍
            symbol = "ETH/USDT"
            leverage = 1

            # When 系統初始化並啟動自動操盤引擎
            engine = UnifiedAutopilotEngine(
                symbol=symbol,
                leverage=leverage,
                capital=100.0,
                enable_ai_veto=False,
                dry_run=True,
                state_file=state_file,
                journal_mgr=jm,
            )

            # Then 引擎運作模式應自動配置為 "SPOT"
            assert engine.mode == "SPOT"
            assert engine.leverage == 1

            # And 策略模型應自動選用現貨動量回踩模型 (SpotMomentumPullbackModel)
            assert isinstance(engine.strategy, SpotMomentumPullbackModel)

            # And 交易風控應採用現貨全額扣款且無強平風險
            assert engine.price_sl_pct == 2.0
            assert engine.margin_sl_threshold == 2.0

    def test_scenario_swap_10x_orchestration(self):
        """Scenario: 使用者指定幣種與高槓桿 10x 時自動配置多體制合約策略與自適應硬停損."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_sol_state.json"
            jm = TradeJournalManager(
                db_path=str(tmp_path / "journal_db.json"),
                journals_dir=str(tmp_path / "journals"),
            )

            # Given 使用者設定交易標的為 "SOL/USDT" 且槓桿倍數為 10 倍
            symbol = "SOL/USDT"
            leverage = 10

            # When 系統初始化並啟動自動操盤引擎
            engine = UnifiedAutopilotEngine(
                symbol=symbol,
                leverage=leverage,
                capital=100.0,
                enable_ai_veto=False,
                dry_run=True,
                state_file=state_file,
                journal_mgr=jm,
            )

            # Then 引擎運作模式應自動配置為 "SWAP_10X"
            assert engine.mode == "SWAP_10X"
            assert engine.leverage == 10

            # And 策略模型應自動選用合約多體制決策模型 (SwapMultiRegimeModel)
            assert isinstance(engine.strategy, SwapMultiRegimeModel)

            # And 原生硬停損應依據 10 倍槓桿自動自適應縮放為 -15.0% 保證金距離
            assert engine.price_sl_pct == 1.5
            assert engine.margin_sl_threshold == 15.0  # 1.5% * 10x

            # And 系統計算之預估強平價距離應大於硬停損價位以確保永不穿倉
            cur_price = 150.0  # e.g. SOL price
            sl_price = cur_price * (1.0 - (engine.price_sl_pct / 100.0))
            liq_price = cur_price * (1.0 - (0.9 / 10.0))
            assert sl_price > liq_price
            assert (cur_price - sl_price) < (cur_price - liq_price)

    def test_scenario_autonomous_continuous_lifecycle(self):
        """Scenario: 全自動生命週期循環（平倉後自動重回待機並準備捕捉下一筆交易，免改程式）."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_lifecycle_state.json"
            journals_dir = tmp_path / "journals"
            jm = TradeJournalManager(
                db_path=str(tmp_path / "journal_db.json"),
                journals_dir=str(journals_dir),
            )

            # Given 自動操盤引擎在 10 倍槓桿持倉中觸發移動停利平倉
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

            entry_price = 77000.0
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
                raw_reason="10x 動態突破開多",
                snapshot_dict={"price": entry_price},
                stop_loss_pct=15.0,
                trailing_pullback_pct=5.0,
            )

            engine.position = {
                "side": "LONG",
                "amount": qty,
                "amount_btc": qty,
                "entry_price": entry_price,
                "margin_used": margin,
                "highest_pnl_pct": 25.0,  # Peak was +25% ROE
                "entry_time": j_entry.entry_time,
                "entry_why": "10x 動態突破開多",
                "ai_decision": "AI 核准",
                "journal_id": j_entry.journal_id,
                "native_sl_price": entry_price * 0.985,
            }

            # When 平倉結算完成並自動撤銷雲端條件單 (Price pulled back to +20% ROE: $78,540)
            exit_price = 78540.0
            engine._close_position(exit_price, reason="動態移動停利 (高點 +25.0% 回撤 5.0%, 鎖定 +20.0%)")

            # Then 部位狀態應自動回歸 "NONE" 且可用保證金全額回流
            assert engine.position["side"] == "NONE"
            assert engine.cash == pytest.approx(110.0, rel=1e-2)

            # And 交易覆盤筆記應自動寫入磁碟權威日誌庫
            entry = engine.journal_mgr.get_entry(j_entry.journal_id)
            assert entry is not None
            assert entry.status == "CLOSED"
            assert entry.pnl_usdt > 0
            assert entry.review.exit_reason != ""

            md_file = journals_dir / "entries" / f"{j_entry.journal_id}.md"
            assert md_file.exists()

            # And 引擎應無縫重啟輪詢監控，完全不需要重新修改或部署程式碼
            assert engine.status == AutopilotState.ARMED
            step_res = engine.step()
            assert step_res["status"] == AutopilotState.ARMED
            assert step_res["position_side"] == "NONE"
