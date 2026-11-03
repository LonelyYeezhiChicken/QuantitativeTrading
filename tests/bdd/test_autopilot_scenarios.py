"""BDD Scenario Implementation Tests: Autopilot Standby Safety, Manual Arming, Ollama Choice & 3-Question Journal."""

import sys
import tempfile
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.models.ollama_agent import OllamaDecisionAgent
from packages.journal import TradeJournalManager
from apps.dashboard.app import get_unified_journal_entries


class TestAutopilotBDDScenarios:
    """BDD Step implementations matching autopilot_manual_arm_and_ai_decision.feature."""

    def test_scenario_standby_default_safety(self):
        """Scenario: 系統啟動時預設為待機模式 (STANDBY) 且絕不主動下單."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"

            # Given 系統啟動自動操盤引擎
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                state_file=state_file,
                dry_run=True,
            )

            # Then 引擎運作狀態應為 "STANDBY"
            assert engine.status == AutopilotState.STANDBY

            # When 引擎處於預設狀態且執行輪詢心跳
            step = engine.step()

            # Then 系統不應發出任何開倉訂單且持倉方向維持為 "NONE"
            assert step["status"] == AutopilotState.STANDBY
            assert step["action_taken"] == "NONE"
            assert engine.position["side"] == "NONE"
            assert "待機中 (STANDBY)" in step["message"]

    def test_scenario_manual_arm_enables_trading(self):
        """Scenario: 交易員手動啟動 (ARM) 後方可執行開倉撮合."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"

            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                state_file=state_file,
                dry_run=True,
            )
            # Given 引擎處於 "STANDBY" 待機模式
            assert engine.status == AutopilotState.STANDBY

            # When 交易員發出手動啟動指令 "ARM"
            arm_msg = engine.arm()

            # Then 引擎狀態切換為 "ARMED"
            assert engine.status == AutopilotState.ARMED
            assert "ARMED" in arm_msg

            # And 引擎處於 ARMED 狀態時被允許執行交易邏輯
            step = engine.step()
            assert step["status"] == AutopilotState.ARMED

            # And 可以隨時手動 disarm 切回 STANDBY
            disarm_msg = engine.disarm()
            assert engine.status == AutopilotState.STANDBY
            assert "STANDBY" in disarm_msg

    def test_scenario_ollama_multiple_choice_veto(self):
        """Scenario: 現況時序參數整理為選擇題並由 Ollama 守門員進行審查."""
        agent = OllamaDecisionAgent(timeout=2.0)

        # Given 引擎已處於 "ARMED" 狀態且候選策略發出 "LONG" 進場訊號
        market_signals = {
            "price": 77600.0,
            "rsi": 54.0,
            "ema21": 77200.0,
            "bias_pct": 0.52,
            "reason": "站穩EMA21均線多頭動態確認",
        }

        # When 系統將當前價格、RSI、EMA21 乖離度整理為選擇題提交給 Ollama
        choice_eval = agent.evaluate_signal_choice("BTC/USDT", "LONG", market_signals)

        # Then Ollama 決策模型應返回結構化的 "EXECUTE" 或 "VETO" 二選一決策
        assert choice_eval["choice"] in ["EXECUTE", "VETO"]
        assert "reason" in choice_eval
        assert len(choice_eval["reason"]) > 3

        # And 若處於高風險超買環境時應被否決 (VETO)
        high_risk_signals = {
            "price": 85000.0,
            "rsi": 78.5,
            "ema21": 80000.0,
            "bias_pct": 6.25,
            "reason": "乖離率極大追高",
        }
        veto_eval = agent.evaluate_signal_choice("BTC/USDT", "LONG", high_risk_signals)
        assert veto_eval["choice"] == "VETO"
        assert "超買" in veto_eval["reason"] or "乖離" in veto_eval["reason"]

    def test_scenario_noise_free_three_question_trade_journal(self):
        """Scenario: 平倉後自動生成極簡三問交易覆盤日誌 (嚴格端到端真實持久化驗證)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"
            db_file = tmp_path / "trade_journal_db.json"
            journals_dir = tmp_path / "journals"

            # 1. 建立真實的 TradeJournalManager
            jm = TradeJournalManager(
                db_path=str(db_file),
                journals_dir=str(journals_dir),
            )

            # 2. 建立整合 TradeJournalManager 的 UnifiedAutopilotEngine
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                state_file=state_file,
                journal_mgr=jm,
                dry_run=True,
            )

            # 3. 模擬真實開倉：透過 TradeJournalManager 建立正式持倉日誌
            open_entry = jm.on_trade_open(
                symbol="BTC/USDT",
                market_type="SWAP",
                side="LONG",
                entry_price=77200.0,
                amount_btc=0.001938,
                margin_used=50.0,
                leverage=3,
                raw_reason="站穩均線多頭動量 (RSI=52.0, 價穩EMA21)",
                snapshot_dict={
                    "price": 77200.0,
                    "rsi": 52.0,
                    "ema21": 77000.0,
                    "atr": 1100.0,
                },
                stop_loss_pct=4.0,
                trailing_pullback_pct=1.0,
            )
            journal_id = open_entry.journal_id

            # 驗證開倉當下磁碟持久化：db 檔案、markdown 檔案存在且狀態為 OPEN
            assert db_file.exists(), "trade_journal_db.json 必須即時寫入磁碟"
            entry_md = journals_dir / "entries" / f"{journal_id}.md"
            assert entry_md.exists(), "開倉當下必須生成 Markdown 覆盤卡"
            assert open_entry.status == "OPEN"

            # 驗證在 OPEN 狀態下，儀表板計算的浮動盈虧與市價動態即時對齊
            test_cur_price = 77500.0  # 比進場高 300 點
            open_cards, open_realized, open_upnl = get_unified_journal_entries(jm, test_cur_price)
            assert len(open_cards) == 1
            expected_upnl = (test_cur_price - 77200.0) * 0.001938
            assert abs(open_upnl - expected_upnl) < 1e-4, "看板浮動盈虧必須與真實持倉公式絕對一致"
            assert open_cards[0]["status"] == "OPEN"
            assert abs(open_cards[0]["pnl_usdt"] - expected_upnl) < 1e-4

            # 4. 綁定引擎倉位並執行軌跡更新
            engine.position = {
                "side": "LONG",
                "amount_btc": 0.001938,
                "entry_price": 77200.0,
                "margin_used": 50.0,
                "highest_pnl_pct": 5.5,
                "entry_time": open_entry.entry_time,
                "entry_why": "站穩均線多頭動量 (RSI=52.0, 價穩EMA21)",
                "ai_decision": "Ollama EXECUTE: 技術回踩未破支撐，風險受控",
                "journal_id": journal_id,
            }
            engine.journal_mgr.on_trade_update(journal_id, 78500.0)
            assert open_entry.trajectory.highest_price == 78500.0

            # 5. 執行真實平倉撮合與 AI 覆盤摘要流程
            exit_price = 78500.0
            exit_reason = "動態移動停利 (最高獲利 +5.5% 回撤 0.4%)"
            engine._close_position(exit_price=exit_price, reason=exit_reason)

            # 6. 嚴格驗證平倉後磁碟持久化與資料庫狀態
            closed_entry = jm.get_entry(journal_id)
            assert closed_entry is not None
            assert closed_entry.status == "CLOSED", "磁碟資料庫中狀態必須更新為 CLOSED"
            expected_realized = (exit_price - 77200.0) * 0.001938
            assert abs(closed_entry.pnl_usdt - round(expected_realized, 2)) < 0.1, "實現盈虧計算必須精準"

            # 7. 驗證日誌三大核心問題欄位 (無雜訊精簡覆盤)
            assert len(engine.closed_trades) == 1
            card = engine.closed_trades[0]
            assert "why_enter" in card and len(card["why_enter"]) > 0
            assert "ai_decision" in card and len(card["ai_decision"]) > 0
            assert "exit_result" in card and len(card["exit_result"]) > 0
            assert card["pnl_usdt"] > 0

            # 8. 驗證 Markdown 檔案內容已同步更新實現盈虧與核心三問
            md_content = entry_md.read_text(encoding="utf-8")
            assert "狀態：`CLOSED`" in md_content
            assert f"{closed_entry.pnl_usdt:,.2f} USDT" in md_content
            assert (journals_dir / "INDEX.md").exists(), "INDEX.md 索引表必須生成"
            index_content = (journals_dir / "INDEX.md").read_text(encoding="utf-8")
            assert journal_id in index_content

            # 9. 驗證儀表板數據同步：已平倉狀態下實現盈虧 100% 吻合
            cards, total_real, total_unreal = get_unified_journal_entries(jm, exit_price)
            assert len(cards) == 1
            assert cards[0]["status"] == "CLOSED"
            assert abs(cards[0]["pnl_usdt"] - closed_entry.pnl_usdt) < 1e-4
            assert abs(total_real - closed_entry.pnl_usdt) < 1e-4
            assert total_unreal == 0.0
