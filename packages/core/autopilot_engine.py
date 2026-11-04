"""Unified Autopilot Engine: Autonomous Trading Controller with Manual Arming & Local AI Copilot.

Key Safety Guarantees:
1. Default STANDBY Mode: Boots in Standby; will NEVER place any order until user explicitly arms it.
2. AI-Assisted Veto Guard: Submits market parameters to local Ollama (Qwen2.5) for multiple-choice sanity check.
3. High-Signal Noise-Free Trade Journal:
   - 為什麼要進場 (Why Enter)
   - 決策是什麼 (AI Decision)
   - 出場與結果 (Exit & Result)
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import pandas as pd

from packages.execution import BingXGateway, MarketType
from packages.models.advanced_strategies import SwapMultiRegimeModel, SpotMomentumPullbackModel
from packages.models.ollama_agent import OllamaDecisionAgent
from packages.journal import TradeJournalManager


class AutopilotState:
    STANDBY = "STANDBY"    # 待機中：僅更新即時行情與資產，絕不主動下單
    ARMED = "ARMED"        # 守護中：已手動武裝，自動執行信號、AI風控審查與停損停利
    PAUSED = "PAUSED"      # 暫停中：維持當前部位，暫不開立新倉


class UnifiedAutopilotEngine:
    """Production-grade single autopilot trading engine."""

    def __init__(
        self,
        mode: Optional[str] = None,
        capital: float = 100.0,
        symbol: str = "BTC/USDT",
        leverage: int = 3,
        enable_ai_veto: bool = True,
        ollama_model: str = "qwen2.5:7b",
        state_file: Optional[Path] = None,
        journal_mgr: Optional[TradeJournalManager] = None,
        dry_run: bool = True,
        price_sl_pct: Optional[float] = None,
        price_tp_pct: Optional[float] = None,
        price_pullback_pct: Optional[float] = None,
        use_vst: bool = False,
    ):
        self.symbol = symbol
        self.capital = capital
        self.enable_ai_veto = enable_ai_veto
        self.dry_run = dry_run
        self.use_vst = use_vst or (os.getenv("BINGX_USE_VST", "false").lower() in ("true", "1"))

        # Auto-derive mode & leverage
        if mode:
            self.mode = mode.upper()
            if "SPOT" in self.mode:
                self.leverage = 1
            else:
                self.leverage = leverage if leverage > 1 else 3
        else:
            if leverage <= 1:
                self.leverage = 1
                self.mode = "SPOT"
            else:
                self.leverage = leverage
                self.mode = f"SWAP_{leverage}X"

        root_dir = Path(__file__).resolve().parent.parent.parent
        if state_file:
            self.state_file = state_file
        else:
            clean_sym = self.symbol.replace("/", "_").replace("-", "_")
            if self.mode == "SWAP_3X" and self.symbol == "BTC/USDT" and capital == 100.0:
                self.state_file = root_dir / "data" / "autopilot_state.json"
            else:
                self.state_file = root_dir / "data" / f"autopilot_{clean_sym}_{self.mode.lower()}_{int(capital)}u.json"

        self.journal_file = root_dir / "data" / "autopilot_journal.json"
        self.journal_mgr = journal_mgr or TradeJournalManager(
            db_path=str(root_dir / "data" / "trade_journal_db.json"),
            journals_dir=str(root_dir / "journals"),
        )

        # Hardware & Gateways
        self.gw = BingXGateway(
            dry_run=self.dry_run,
            use_vst=self.use_vst,
            enable_ws=True,
            default_market_type=MarketType.SWAP.value if "SWAP" in self.mode else MarketType.SPOT.value,
        )
        self.ai_agent = OllamaDecisionAgent(model=ollama_model)

        # Champion Strategy Models & Adaptive Volatility Risk Math
        if "SWAP" in self.mode:
            try:
                self.gw.set_leverage(self.symbol, self.leverage)
            except Exception:
                pass
            self.strategy = SwapMultiRegimeModel(ema_span=21)
            self.price_sl_pct = price_sl_pct if price_sl_pct is not None else 1.5
            self.price_tp_pct = price_tp_pct if price_tp_pct is not None else (2.0 if self.leverage >= 10 else 1.0)
            self.price_pullback_pct = price_pullback_pct if price_pullback_pct is not None else (0.5 if self.leverage >= 10 else 0.33)
            self.margin_sl_threshold = self.price_sl_pct * self.leverage
            self.margin_tp_threshold = self.price_tp_pct * self.leverage
            self.margin_pullback_threshold = self.price_pullback_pct * self.leverage
        else:
            self.strategy = SpotMomentumPullbackModel(ema_span=21)
            self.price_sl_pct = price_sl_pct if price_sl_pct is not None else 2.0
            self.price_tp_pct = price_tp_pct if price_tp_pct is not None else 1.5
            self.price_pullback_pct = price_pullback_pct if price_pullback_pct is not None else 0.4
            self.margin_sl_threshold = self.price_sl_pct
            self.margin_tp_threshold = self.price_tp_pct
            self.margin_pullback_threshold = self.price_pullback_pct

        # In-memory runtime state
        self.status = AutopilotState.STANDBY  # 預設待機，絕不自動交易
        self.cash = self.capital
        self.position: Dict[str, Any] = {
            "side": "NONE",
            "amount": 0.0,
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "highest_pnl_pct": 0.0,
            "entry_time": "",
            "entry_why": "",
            "ai_decision": "",
        }
        self.closed_trades: list[Dict[str, Any]] = []
        self.pending_order: Optional[Dict[str, Any]] = None
        self.load_state()

    def arm(self) -> str:
        """Manually arm the autopilot to activate automatic trading."""
        self.status = AutopilotState.ARMED
        self.save_state()
        return "自動操盤引擎已武裝 (ARMED)！開始監控行情與執行信號。"

    def disarm(self) -> str:
        """Manually disarm into standby mode (stops opening new positions)."""
        self.status = AutopilotState.STANDBY
        self.save_state()
        return "自動操盤引擎已切換為待機模式 (STANDBY)。停止自動交易。"

    def emergency_close_and_stop(self) -> str:
        """Immediately liquidate position and enter STANDBY."""
        self.status = AutopilotState.STANDBY
        if self.position["side"] != "NONE":
            t_btc = self.gw.fetch_ticker(self.symbol, market_type="SWAP" if "SWAP" in self.mode else "SPOT")
            cur_price = t_btc.get("price", 77000.0)
            if not self._close_position(cur_price, reason="交易員手動緊急全額平倉"):
                self.save_state()
                return "緊急平倉未確認；已保留持倉狀態並切換為待機，請檢查交易所訂單。"
        self.save_state()
        return "已全額平倉並切換為待機狀態。"

    def step(self) -> Dict[str, Any]:
        """Perform a single heartbeat evaluation tick.

        When STANDBY: Only refreshes tickers and computes portfolio value.
        When ARMED: Evaluates signals, AI multiple-choice veto, entry/exit.
        """
        m_type = "SWAP" if "SWAP" in self.mode else "SPOT"
        ticker = self.gw.fetch_ticker(self.symbol, market_type=m_type)
        cur_price = ticker.get("price", 77000.0)

        # 1. Calculate Portfolio Equity
        side = self.position.get("side", "NONE")
        qty = self.position.get("amount_btc", 0.0)
        entry_p = self.position.get("entry_price", cur_price)
        used_margin = self.position.get("margin_used", 0.0)

        if side == "LONG":
            unrealized_pnl = (cur_price - entry_p) * qty
        elif side == "SHORT":
            unrealized_pnl = (entry_p - cur_price) * qty
        else:
            unrealized_pnl = 0.0

        pnl_pct = (unrealized_pnl / used_margin * 100) if used_margin > 0 else 0.0
        total_equity = self.cash + used_margin + unrealized_pnl

        # If in position, update trailing peak and journal trajectory
        if side != "NONE":
            self.position["highest_pnl_pct"] = max(self.position.get("highest_pnl_pct", 0.0), pnl_pct)
            j_id = self.position.get("journal_id")
            if j_id:
                self.journal_mgr.on_trade_update(j_id, cur_price)

        step_result = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "status": self.status,
            "mode": self.mode,
            "price": cur_price,
            "position_side": side,
            "pnl_usdt": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "total_equity": total_equity,
            "action_taken": "NONE",
            "message": "待機中 (STANDBY) - 尚未手動武裝",
        }

        # Resolve acknowledged orders before another order can be submitted.
        if self.pending_order:
            resolved = self._resolve_pending_order()
            step_result["position_side"] = self.position.get("side", "NONE")
            step_result["total_equity"] = self.cash + self.position.get("margin_used", 0.0)
            step_result["action_taken"] = "ORDER_RESOLVED" if resolved else "ORDER_PENDING"
            step_result["message"] = "待確認中的交易所訂單已成交" if resolved else "交易所訂單結果尚未確認，暫停新下單"
            return step_result

        # Reconcile persisted swap positions even while disarmed. Restarting in
        # STANDBY must not prevent detection of an exchange-side stop execution.
        if side != "NONE" and not self.dry_run and "SWAP" in self.mode:
            try:
                reconciled = self.reconcile_with_exchange()
            except Exception:
                reconciled = None
            if reconciled is None:
                step_result["action_taken"] = "RECONCILIATION_REQUIRED"
                step_result["message"] = "無法確認交易所持倉，保留本機狀態並暫停交易"
                return step_result
            if reconciled:
                step_result["action_taken"] = "NATIVE_STOP_LOSS"
                step_result["message"] = "交易所原生條件單已平倉，已完成本機狀態對齊"
                return step_result

        # -------------------------------------------------------------
        # SAFETY RULE: If STANDBY, NEVER PLACE ANY ORDERS!
        # -------------------------------------------------------------
        if self.status != AutopilotState.ARMED:
            return step_result

        # ----------------- ARMED TRADING LOOP -----------------
        # A. Position Management (Stop Loss / Trailing Take Profit)
        if side != "NONE":
            # Reconcile with exchange to detect if native hard SL triggered on exchange during network drop
            peak_pct = self.position.get("highest_pnl_pct", 0.0)
            pullback = peak_pct - pnl_pct

            # 1. Hard Stop Loss
            if pnl_pct <= -self.margin_sl_threshold:
                closed = self._close_position(cur_price, reason=f"自適應保證金停損觸發 (虧損達 {pnl_pct:.2f}%, 截斷風險)")
                step_result["action_taken"] = "STOP_LOSS" if closed else "CLOSE_FAILED"
                step_result["message"] = (
                    f"已執行硬停損平倉 (虧損 {pnl_pct:.2f}%)"
                    if closed and not self.pending_order
                    else "部位已平倉；日誌或條件單清理待重試"
                    if closed
                    else "停損平倉未確認，保留持倉並等待對帳"
                )
                return step_result

            # 2. Trailing Take Profit
            if peak_pct >= self.margin_tp_threshold and pullback >= self.margin_pullback_threshold:
                closed = self._close_position(cur_price, reason=f"動態移動停利 (最高獲利 +{peak_pct:.2f}% 回撤 {pullback:.2f}%)")
                step_result["action_taken"] = "TAKE_PROFIT" if closed else "CLOSE_FAILED"
                step_result["message"] = (
                    f"已執行移動停利平倉 (鎖定利潤 +{pnl_pct:.2f}%)"
                    if closed and not self.pending_order
                    else "部位已平倉；日誌或條件單清理待重試"
                    if closed
                    else "停利平倉未確認，保留持倉並等待對帳"
                )
                return step_result

            step_result["message"] = f"持倉監控中 ({side} {qty:.5f} BTC | 浮盈 {pnl_pct:+.2f}%)"
            return step_result

        # B. Entry Evaluation (Only when flat and ARMED)
        signals = self._compute_market_signals(cur_price)
        rsi = signals["rsi"]
        ema21 = signals["ema21"]
        ema50 = signals.get("ema50", ema21)

        # Strategy Candidate Decision
        candidate_signal = None
        candidate_reason = ""

        if "SWAP" in self.mode:
            # Swap MultiRegime rules:
            # 1. Healthy dip entry
            if (cur_price >= ema21 and 45.0 <= rsi <= 58.0) or (rsi < 35.0):
                candidate_signal = "LONG"
                candidate_reason = f"均線上方多頭動量確認 (RSI={rsi:.1f}, 價穩EMA21)" if rsi >= 45 else f"短線跌深超賣反彈 (RSI={rsi:.1f}<35)"
            # 2. Strong trend continuation momentum entry
            elif cur_price >= ema21 and cur_price >= ema50 and 58.0 < rsi <= 72.0:
                candidate_signal = "LONG"
                candidate_reason = f"雙均線多頭排列強勢動能突破 (RSI={rsi:.1f}, 站上EMA21/EMA50)"
            # 3. Breakdown short entry
            elif cur_price < ema21 * 0.995 and 38.0 <= rsi <= 48.0:
                candidate_signal = "SHORT"
                candidate_reason = f"均線破位空方順勢 (RSI={rsi:.1f}, 跌破EMA21)"
        else:
            # Spot Momentum Pullback rules
            if (cur_price >= ema21 * 0.998 and rsi <= 55.0) or (rsi < 38.0):
                candidate_signal = "LONG"
                candidate_reason = f"均線支撐回踩確認 (RSI={rsi:.1f}, 貼近EMA21)" if rsi >= 40 else f"短線超賣低接 (RSI={rsi:.1f}<38)"

        if not candidate_signal:
            step_result["message"] = f"無開倉信號 (RSI={rsi:.1f}, 市價=${cur_price:,.2f})，等待標準型態"
            return step_result

        # C. Local Ollama AI Veto Sanity Check (Multiple Choice: EXECUTE vs VETO)
        ai_decision_text = "策略技術面信號觸發"
        if self.enable_ai_veto:
            signals["reason"] = candidate_reason
            ai_eval = self.ai_agent.evaluate_signal_choice(self.symbol, candidate_signal, signals)
            ai_decision_text = f"Ollama {ai_eval['choice']}: {ai_eval['reason']}"

            if ai_eval["choice"] == "VETO":
                step_result["action_taken"] = "AI_VETO"
                step_result["message"] = f"AI 風控守門員否決開倉：{ai_eval['reason']}"
                return step_result

        # D. Execute Order
        trade_margin = min(50.0, self.cash)
        if trade_margin < 10.0:
            step_result["message"] = f"可用資金不足 (${self.cash:.2f} < 10 U)，放棄開倉"
            return step_result

        notional = trade_margin * self.leverage
        qty_to_buy = notional / max(cur_price, 1e-4)

        # Calculate Native Hard Stop-Loss price to attach atomically upon entry
        if candidate_signal == "LONG":
            native_sl_price = cur_price * (1.0 - (self.price_sl_pct / 100.0))
        else:
            native_sl_price = cur_price * (1.0 + (self.price_sl_pct / 100.0))

        # Gateway order with Atomic Native SL attachment
        order_res = self.gw.create_order(
            symbol=self.symbol,
            side="BUY" if candidate_signal == "LONG" else "SELL",
            order_type="MARKET",
            size=qty_to_buy,
            market_type=m_type,
            position_side=candidate_signal if "SWAP" in self.mode else None,
            leverage=self.leverage,
            stop_loss_price=native_sl_price,
            simulation_price=cur_price,
        )

        filled, fill_qty, fill_price, resolution = self._confirm_market_fill(order_res, qty_to_buy, m_type)
        if filled:
            self._record_open_position(
                candidate_signal, fill_qty, fill_price, trade_margin, candidate_reason,
                ai_decision_text, native_sl_price, signals,
            )
            step_result["action_taken"] = "OPEN_POSITION"
            step_result["message"] = f"已成功開倉 {candidate_signal} ({fill_qty:.5f} BTC) | {ai_decision_text}"
        elif resolution == "PENDING":
            data = order_res.get("data", {}) if isinstance(order_res, dict) else {}
            self.pending_order = {
                "action": "OPEN",
                "order_id": str(data.get("orderId", "")),
                "candidate_signal": candidate_signal,
                "candidate_reason": candidate_reason,
                "ai_decision_text": ai_decision_text,
                "quantity": qty_to_buy,
                "margin": trade_margin,
                "price": cur_price,
                "native_sl_price": native_sl_price,
                "signals": signals,
                "order_response": order_res,
            }
            self.save_state()
            step_result["action_taken"] = "ORDER_PENDING"
            step_result["message"] = "交易所已受理訂單但成交狀態未確認；暫停重試以避免重複開倉"
        else:
            step_result["message"] = f"下單失敗: {order_res.get('msg', '未知錯誤')}"

        return step_result

    def _close_position(self, exit_price: float, reason: str, *, exchange_already_closed: bool = False) -> bool:
        """Close the exchange position first, then persist the confirmed result."""
        side = self.position["side"]
        qty = self.position["amount_btc"]
        entry_p = self.position["entry_price"]
        margin = self.position["margin_used"]

        if side == "NONE" or qty <= 0:
            return False

        if not exchange_already_closed:
            market_type = "SWAP" if "SWAP" in self.mode else "SPOT"
            close_side = "SELL" if side == "LONG" else "BUY"
            try:
                close_res = self.gw.create_order(
                    symbol=self.symbol,
                    side=close_side,
                    order_type="MARKET",
                    size=qty,
                    market_type=market_type,
                    position_side=side if market_type == "SWAP" else None,
                    leverage=self.leverage,
                    client_order_id=f"auto-close-{int(time.time() * 1000)}",
                    simulation_price=exit_price,
                )
                filled, filled_qty, actual_exit_price, resolution = self._confirm_market_fill(close_res, qty, market_type)
            except Exception:
                filled, filled_qty, actual_exit_price, resolution = False, 0.0, exit_price, "PENDING"
            if not filled:
                if resolution == "PENDING":
                    data = close_res.get("data", {}) if isinstance(close_res, dict) else {}
                    self.pending_order = {
                        "action": "CLOSE",
                        "order_id": str(data.get("orderId", "")),
                        "quantity": qty,
                        "price": exit_price,
                        "reason": reason,
                        "order_response": close_res if "close_res" in locals() else {},
                    }
                    self.save_state()
                return False
            if filled_qty + max(1e-12, qty * 1e-8) < qty:
                self.pending_order = {"action": "CLOSE", "order_id": "", "quantity": qty, "reason": reason}
                self.save_state()
                return False
            exit_price = actual_exit_price

        if side == "LONG":
            pnl_usdt = (exit_price - entry_p) * qty
        else:
            pnl_usdt = (entry_p - exit_price) * qty
        pnl_pct = (pnl_usdt / margin * 100) if margin > 0 else 0.0
        raw_record = {
            "symbol": self.symbol,
            "side": side,
            "entry_price": entry_p,
            "exit_price": exit_price,
            "pnl_usdt": round(pnl_usdt, 2),
            "pnl_pct": round(pnl_pct, 2),
            "entry_reason": self.position.get("entry_why", "技術型態觸發"),
            "ai_decision": self.position.get("ai_decision", "AI 風控核准"),
            "exit_reason": reason,
            "entry_time": self.position.get("entry_time", ""),
            "exit_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        journal_id = self.position.get("journal_id", "")
        # Persist exchange-confirmed closure before fallible journal work. A
        # restart resumes journal/conditional-order cleanup instead of closing twice.
        self.cash += margin + pnl_usdt
        self.position = {
            "side": "NONE",
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "highest_pnl_pct": 0.0,
            "entry_time": "",
            "entry_why": "",
            "ai_decision": "",
            "journal_id": "",
        }
        self.pending_order = {
            "action": "JOURNAL_CLOSE",
            "journal_id": journal_id,
            "raw_record": raw_record,
        }
        self.save_state()
        self._finish_confirmed_close()
        return True

    def _finish_confirmed_close(self) -> bool:
        """Finish disk journaling and conditional-order cleanup idempotently."""
        pending = self.pending_order or {}
        raw_record = pending.get("raw_record")
        if pending.get("action") != "JOURNAL_CLOSE" or not isinstance(raw_record, dict):
            return False
        try:
            ai_summary = self.ai_agent.summarize_trade_journal(raw_record)
        except Exception:
            ai_summary = {}
        pnl_usdt = float(raw_record["pnl_usdt"])
        journal_id = pending.get("journal_id") or ""
        clean_journal_card = {
            "id": f"TRD_{journal_id or raw_record['exit_time'].replace(':', '').replace('-', '').replace(' ', '_')}",
            "time": raw_record["exit_time"][:16],
            "side": raw_record["side"],
            "pnl_usdt": raw_record["pnl_usdt"],
            "pnl_pct": raw_record["pnl_pct"],
            "entry_price": raw_record["entry_price"],
            "exit_price": raw_record["exit_price"],
            "why_enter": ai_summary.get("why_enter", raw_record["entry_reason"]),
            "ai_decision": ai_summary.get("ai_decision", raw_record["ai_decision"]),
            "exit_result": ai_summary.get("exit_result", f"{raw_record['exit_reason']} (盈虧: ${pnl_usdt:+,.2f})"),
        }
        if journal_id:
            try:
                closed_entry = self.journal_mgr.get_entry(journal_id)
                if closed_entry is not None and closed_entry.status != "CLOSED":
                    closed_entry = self.journal_mgr.on_trade_close(
                        journal_id=journal_id,
                        exit_price=float(raw_record["exit_price"]),
                        exit_reason=raw_record["exit_reason"],
                    )
                if closed_entry:
                    if ai_summary.get("why_enter"):
                        closed_entry.review.thesis = ai_summary["why_enter"]
                    if ai_summary.get("ai_decision"):
                        closed_entry.review.strategy_evaluation = ai_summary["ai_decision"]
                    if ai_summary.get("exit_result"):
                        closed_entry.review.exit_reason = ai_summary["exit_result"]
                    self.journal_mgr._save_db()
                    self.journal_mgr._write_entry_markdown(closed_entry)
                    self.journal_mgr._render_index()
            except Exception:
                return False

        try:
            if not self.gw.cancel_all_orders(self.symbol, market_type="SWAP" if "SWAP" in self.mode else "SPOT"):
                return False
        except Exception:
            return False
        if not any(card.get("id") == clean_journal_card["id"] for card in self.closed_trades):
            self.closed_trades.insert(0, clean_journal_card)
        self.pending_order = None
        self.save_state()
        self.save_journal()
        return True

    def _confirm_market_fill(self, response: Dict[str, Any], requested_qty: float, market_type: str):
        """Return confirmed full fill details, or distinguish failure from uncertainty."""
        if not isinstance(response, dict):
            return False, 0.0, 0.0, "FAILED"
        if not response.get("result"):
            return (False, 0.0, 0.0, "PENDING") if response.get("code") == 0 else (False, 0.0, 0.0, "FAILED")
        data = response.get("data", {})
        if not isinstance(data, dict):
            return False, 0.0, 0.0, "PENDING"
        status = str(data.get("status", "")).upper()
        order_id = data.get("orderId")
        if status not in {"FILLED", "CLOSED"} and order_id:
            try:
                queried = self.gw.get_order(self.symbol, str(order_id), market_type=market_type)
                queried_data = queried.get("data", {}) if isinstance(queried, dict) else {}
                if isinstance(queried_data, dict):
                    data = queried_data
                    status = str(data.get("status", "")).upper()
            except Exception:
                pass
        if status not in {"FILLED", "CLOSED"}:
            if status in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}:
                return False, 0.0, 0.0, "FAILED"
            return False, 0.0, 0.0, "PENDING"
        try:
            filled_qty = float(data.get("executedQty", data.get("quantity", data.get("origQty", requested_qty))))
            fill_price = float(data.get("avgPrice", data.get("price", 0.0)))
        except (TypeError, ValueError):
            return False, 0.0, 0.0, "PENDING"
        if filled_qty + max(1e-12, requested_qty * 1e-8) < requested_qty or fill_price <= 0:
            return False, filled_qty, fill_price, "PENDING"
        return True, min(filled_qty, requested_qty), fill_price, "FILLED"

    def _record_open_position(self, side, quantity, price, margin, reason, decision, native_sl_price, signals):
        """Persist a confirmed opening fill and its authoritative journal entry."""
        actual_margin = quantity * price / (self.leverage if "SWAP" in self.mode else 1)
        j_entry = self.journal_mgr.on_trade_open(
            symbol=self.symbol,
            market_type="SWAP" if "SWAP" in self.mode else "SPOT",
            side=side,
            entry_price=price,
            amount_btc=quantity,
            margin_used=actual_margin,
            leverage=self.leverage,
            raw_reason=reason,
            snapshot_dict={
                "price": price,
                "rsi": signals.get("rsi", 50.0),
                "ema21": signals.get("ema21", price),
                "ema50": signals.get("ema50", price),
                "atr": price * 0.015,
            },
            stop_loss_pct=self.margin_sl_threshold,
            trailing_pullback_pct=self.margin_pullback_threshold,
        )
        if j_entry and hasattr(j_entry, "review"):
            j_entry.review.strategy_evaluation = decision
            self.journal_mgr._save_db()
            self.journal_mgr._write_entry_markdown(j_entry)
        self.cash -= actual_margin
        self.position = {
            "side": side,
            "amount": quantity,
            "amount_btc": quantity,
            "entry_price": price,
            "margin_used": actual_margin,
            "highest_pnl_pct": 0.0,
            "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "entry_why": reason,
            "ai_decision": decision,
            "journal_id": j_entry.journal_id if j_entry else "",
            "native_sl_price": native_sl_price,
        }
        self.save_state()

    def _resolve_pending_order(self) -> bool:
        """Resolve a previously accepted order without submitting a duplicate."""
        pending = self.pending_order or {}
        if pending.get("action") == "JOURNAL_CLOSE":
            return self._finish_confirmed_close()
        order_id = pending.get("order_id")
        if not order_id:
            return False
        market_type = "SWAP" if "SWAP" in self.mode else "SPOT"
        try:
            response = self.gw.get_order(self.symbol, str(order_id), market_type=market_type)
        except Exception:
            return False
        order_data = response.get("data", {}) if isinstance(response, dict) else {}
        order_status = str(order_data.get("status", "")).upper() if isinstance(order_data, dict) else ""
        if order_status in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}:
            self.pending_order = None
            self.save_state()
            return False
        if pending.get("action") == "CLOSE":
            # A confirmed exchange close is finalized using the returned fill.
            filled, _, price, _ = self._confirm_market_fill(response, float(pending["quantity"]), market_type)
            if not filled:
                return False
            self.pending_order = None
            return self._close_position(price, pending.get("reason", "待確認市價平倉"), exchange_already_closed=True)
        filled, qty, price, _ = self._confirm_market_fill(response, float(pending["quantity"]), market_type)
        if not filled:
            return False
        # Persist a confirmed fill as a position so the normal risk loop takes over.
        self.pending_order = None
        self._record_open_position(
            pending["candidate_signal"], qty, price, float(pending["margin"]),
            pending["candidate_reason"], pending["ai_decision_text"],
            float(pending.get("native_sl_price", 0.0)), pending.get("signals", {}),
        )
        return True

    def reconcile_with_exchange(self, active_exchange_positions: Optional[list] = None) -> Optional[bool]:
        """Reconcile local state with exchange positions (essential for reconnecting after network drops).

        If local engine records an OPEN position but exchange has 0 amount (e.g. native SL executed on exchange),
        immediately finalize trade journal and mark as CLOSED.
        """
        if self.position.get("side") == "NONE":
            return False

        cur_side = self.position["side"]

        if active_exchange_positions is None:
            if self.dry_run:
                return False
            try:
                m_type = "SWAP" if "SWAP" in self.mode else "SPOT"
                if m_type == "SWAP":
                    active_exchange_positions = self.gw.get_positions(self.symbol)
                else:
                    return False
            except Exception:
                return None

        has_active_position = False
        for p in active_exchange_positions:
            pos_amt = float(p.get("positionAmt", p.get("amount", 0.0)))
            pos_side = p.get("positionSide", p.get("side", "")).upper()
            if pos_side == cur_side and abs(pos_amt) > 0:
                has_active_position = True
                break

        if not has_active_position:
            # Position was liquidated / closed on exchange (e.g. by native SL) while client was offline!
            t = self.gw.fetch_ticker(self.symbol, market_type="SWAP" if "SWAP" in self.mode else "SPOT")
            cur_p = t.get("price", self.position.get("entry_price", 0.0))
            return self._close_position(cur_p, reason="交易所原生硬停損觸發平倉 (斷網保底生效)", exchange_already_closed=True)

        return False

    def _compute_market_signals(self, cur_price: float) -> Dict[str, float]:
        """Compute live 1h technical signals for decision making."""
        try:
            m_type = "SWAP" if "SWAP" in self.mode else "SPOT"
            klines = self.gw.fetch_klines(self.symbol, timeframe="1h", limit=50, market_type=m_type)
            if klines is not None and len(klines) >= 25:
                df = klines if isinstance(klines, pd.DataFrame) else pd.DataFrame(klines)
                close_s = df["close"]
                ema21 = float(close_s.ewm(span=21, adjust=False).mean().iloc[-1])
                ema50 = float(close_s.ewm(span=50, adjust=False).mean().iloc[-1]) if len(close_s) >= 30 else ema21
                diff = close_s.diff()
                gain = diff.clip(lower=0).rolling(14).mean()
                loss = (-diff.clip(upper=0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                rsi = float((100.0 - (100.0 / (1.0 + rs))).iloc[-1])
                return {"price": cur_price, "rsi": rsi, "ema21": ema21, "ema50": ema50}
        except Exception:
            pass
        return {"price": cur_price, "rsi": 50.0, "ema21": cur_price, "ema50": cur_price}

    def save_state(self):
        """Save persistent state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "status": self.status,
            "mode": self.mode,
            "capital": self.capital,
            "cash": round(self.cash, 2),
            "leverage": self.leverage,
            "position": self.position,
            "pending_order": self.pending_order,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_state(self):
        """Load state from disk if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # A process restart always requires explicit manual re-arming.
                    self.status = AutopilotState.STANDBY
                    self.cash = data.get("cash", self.capital)
                    self.position = data.get("position", self.position)
                    self.pending_order = data.get("pending_order")
            except Exception:
                pass

    def save_journal(self):
        """Save clean trade records to disk."""
        self.journal_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal_file, "w", encoding="utf-8") as f:
            json.dump(self.closed_trades[:50], f, indent=2, ensure_ascii=False)

    def load_journal(self) -> list[Dict[str, Any]]:
        """Load clean trade records from the authoritative TradeJournalManager."""
        entries = self.journal_mgr.get_entries()
        records = []
        for e in entries:
            records.append({
                "id": e.journal_id,
                "time": (e.exit_time or e.entry_time)[:16],
                "side": e.side,
                "status": e.status,
                "market": e.market_type,
                "pnl_usdt": round(e.pnl_usdt, 2),
                "pnl_pct": round(e.pnl_pct, 2),
                "entry_price": e.entry_price,
                "exit_price": e.exit_price,
                "why_enter": e.review.thesis.splitlines()[0] if e.review.thesis else "技術型態觸發",
                "ai_decision": e.review.strategy_evaluation.splitlines()[0] if e.review.strategy_evaluation else "AI 核准進場",
                "exit_result": e.review.exit_reason.splitlines()[0] if e.review.exit_reason else "持續守護中",
            })
        if not records and self.closed_trades:
            return self.closed_trades
        return records
