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
from packages.execution.base import BaseBrokerGateway
from packages.models.base import BaseTradingModel
from packages.models.advanced_strategies import SwapMultiRegimeModel, SpotMomentumPullbackModel
from packages.models.ollama_agent import OllamaDecisionAgent
from packages.journal import TradeJournalManager


class AutopilotState:
    STANDBY = "STANDBY"    # 待機中：僅更新即時行情與資產，絕不主動下單
    ARMED = "ARMED"        # 守護中：已手動武裝，自動執行信號、AI風控審查與停損停利
    PAUSED = "PAUSED"      # 暫停中：維持當前部位，暫不開立新倉


def compute_structural_indicators_from_ohlc(
    closes: list[float],
    highs: Optional[list[float]],
    lows: Optional[list[float]],
    cur_price: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute EMA21, EMA50, Wilder RSI(14), ATR(14), and 48h Fibonacci Golden Pocket structure."""
    if not closes:
        closes = [cur_price]
    highs = highs if highs and len(highs) == len(closes) else list(closes)
    lows = lows if lows and len(lows) == len(closes) else list(closes)

    s_close = pd.Series(closes, dtype=float)
    ema21 = float(s_close.ewm(span=21, adjust=False).mean().iloc[-1])
    ema50 = float(s_close.ewm(span=50, adjust=False).mean().iloc[-1]) if len(closes) >= 25 else ema21
    prev_close = float(closes[-2]) if len(closes) >= 2 else cur_price

    rsi = 50.0
    if len(closes) >= 15:
        diff = s_close.diff()
        gain = diff.clip(lower=0).ewm(alpha=1.0 / 14.0, adjust=False).mean()
        loss = (-diff.clip(upper=0)).ewm(alpha=1.0 / 14.0, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi = float((100.0 - (100.0 / (1.0 + rs))).iloc[-1])

    atr = cur_price * 0.015
    if len(closes) >= 15:
        tr_list = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        if tr_list:
            atr = float(pd.Series(tr_list, dtype=float).ewm(alpha=1.0 / 14.0, adjust=False).mean().iloc[-1])

    window = min(48, len(closes))
    swing_high_48 = float(max(highs[-window:])) if window > 0 else cur_price
    swing_low_48 = float(min(lows[-window:])) if window > 0 else cur_price
    swing_range = swing_high_48 - swing_low_48

    in_bull_gp = False
    in_bear_gp = False
    if swing_range > (cur_price * 0.012):
        bull_top = swing_high_48 - 0.50 * swing_range
        bull_bot = swing_high_48 - 0.65 * swing_range
        bear_bot = swing_low_48 + 0.50 * swing_range
        bear_top = swing_low_48 + 0.65 * swing_range
        in_bull_gp = bool(bull_bot <= cur_price <= bull_top)
        in_bear_gp = bool(bear_bot <= cur_price <= bear_top)

    bias_pct = ((cur_price - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0
    return {
        "price": cur_price,
        "bid": bid if bid is not None else cur_price,
        "ask": ask if ask is not None else cur_price,
        "rsi": rsi,
        "ema21": ema21,
        "ema50": ema50,
        "atr": atr,
        "bias_pct": round(bias_pct, 4),
        "prev_close": prev_close,
        "swing_high_48": swing_high_48,
        "swing_low_48": swing_low_48,
        "in_bull_golden_pocket": in_bull_gp,
        "in_bear_golden_pocket": in_bear_gp,
    }


def _parse_utc_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse UTC timestamp strings like '2026-11-04 05:49:00 UTC' or ISO-8601 into aware datetime."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip()
    if cleaned.endswith(" UTC"):
        cleaned_no_tz = cleaned[:-4].strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(cleaned_no_tz, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    try:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def evaluate_structural_entry(
    mode: str,
    cur_price: float,
    signals: Dict[str, Any],
    max_ema21_bias_pct: float = 0.45,
    history: Optional[list[Dict[str, Any]]] = None,
    now_utc: Optional[datetime] = None,
    cooldown_minutes: int = 15,
) -> Tuple[Optional[str], str]:
    """Evaluate entry signal using macro trend alignment (EMA21 vs EMA50),
    48h Fibonacci Golden Pocket (0.50~0.65), anti-falling-knife confirmation,
    Max EMA21 Bias anti-chasing filter (<= +0.45%), and Post-Exit Cooldown (15 min).
    """
    # 0. Post-Exit Cooldown Guard (prevent immediate emotional/spike rechasing right after closing a trade)
    if history and cooldown_minutes > 0:
        ref_now = now_utc if now_utc is not None else datetime.now(timezone.utc)
        latest_closed_dt: Optional[datetime] = None
        for item in (history[-1], history[0]):
            if isinstance(item, dict):
                ts_str = str(item.get("closed_at") or item.get("exit_time") or item.get("time") or "")
                parsed = _parse_utc_timestamp(ts_str)
                if parsed is not None and (latest_closed_dt is None or parsed > latest_closed_dt):
                    latest_closed_dt = parsed
        if latest_closed_dt is not None:
            elapsed_sec = (ref_now - latest_closed_dt).total_seconds()
            if 0.0 <= elapsed_sec < (cooldown_minutes * 60.0):
                elapsed_min = elapsed_sec / 60.0
                return (
                    None,
                    f"平倉後冷卻保護中 (距上次出場 {elapsed_min:.1f} 分鐘 < {cooldown_minutes} 分鐘，禁止原地追單)",
                )

    rsi = float(signals.get("rsi", 50.0))
    ema21 = float(signals.get("ema21", cur_price))
    ema50 = float(signals.get("ema50", ema21))
    prev_close = float(signals.get("prev_close", cur_price - 1.0))
    in_bull_gp = bool(signals.get("in_bull_golden_pocket", False))
    in_bear_gp = bool(signals.get("in_bear_golden_pocket", False))

    ema21_bias_pct = ((cur_price - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0
    is_bull_macro = ema21 >= (ema50 * 0.999)
    is_bear_macro = ema21 < (ema50 * 0.9995)
    is_candle_rebound = cur_price > prev_close

    if "SWAP" in mode.upper():
        # 1. Bullish Fibonacci Golden Pocket (0.50 ~ 0.65) Structural Support
        if in_bull_gp and is_bull_macro and is_candle_rebound and 35.0 <= rsi <= 58.0:
            if ema21_bias_pct > max_ema21_bias_pct:
                return None, f"均線正乖離過大禁止追高 (Bias=+{ema21_bias_pct:.2f}% > +{max_ema21_bias_pct:.2f}%，等待回踩貼近EMA21)"
            return "LONG", f"斐波那契黃金口袋支撐回踩確認 (RSI={rsi:.1f}, 48h 0.5~0.65 結構區止跌)"
        # 2. Bullish Trend Pullback (requires EMA21 >= EMA50 macro trend alignment & low bias <= +0.45%)
        if cur_price >= ema21 and is_bull_macro and 45.0 <= rsi <= 58.0:
            if ema21_bias_pct > max_ema21_bias_pct:
                return None, f"均線正乖離過大禁止追高 (Bias=+{ema21_bias_pct:.2f}% > +{max_ema21_bias_pct:.2f}%，等待回踩貼近EMA21)"
            return "LONG", f"雙均線順勢回踩多頭動量確認 (RSI={rsi:.1f}, Bias={ema21_bias_pct:+.2f}%, 價穩EMA21>=EMA50)"
        # 3. Strong Dual-EMA Momentum Continuation (strictly capped by max_ema21_bias_pct to avoid buying top wicks)
        if cur_price >= ema21 and cur_price >= ema50 and is_bull_macro and 58.0 < rsi <= 70.0:
            if ema21_bias_pct > max_ema21_bias_pct:
                return None, f"均線正乖離過大禁止追高 (Bias=+{ema21_bias_pct:.2f}% > +{max_ema21_bias_pct:.2f}%，等待回踩貼近EMA21)"
            return "LONG", f"雙均線多頭排列強勢動能突破 (RSI={rsi:.1f}, Bias={ema21_bias_pct:+.2f}%, 站上EMA21/EMA50)"
        # 4. Confirmed Oversold Reversal (requires cur_price > prev_close to avoid catching a falling knife)
        if rsi < 35.0 and is_candle_rebound:
            return "LONG", f"短線超賣止跌勾頭反彈確認 (RSI={rsi:.1f}<35, 現價高於前收)"
        # 5. Bearish Fibonacci Golden Pocket Rejection
        if in_bear_gp and is_bear_macro and (cur_price < prev_close) and 42.0 <= rsi <= 62.0:
            return "SHORT", f"斐波那契空方黃金口袋壓力受阻 (RSI={rsi:.1f}, 48h 0.5~0.65 反彈受壓)"
        # 6. Bearish Breakdown Short (strictly requires EMA21 < EMA50 macro bearish structure & not over-extended crash)
        if cur_price < ema21 * 0.995 and is_bear_macro and 38.0 <= rsi <= 48.0:
            if ema21_bias_pct < -1.20:
                return None, f"均線負乖離過大禁止追空 (Bias={ema21_bias_pct:.2f}% < -1.20%，等待反彈靠近EMA21)"
            return "SHORT", f"雙均線空頭排列破位順勢開空 (RSI={rsi:.1f}, 跌破EMA21<EMA50)"
    else:
        # Spot Structural Entry Rules (Long-Only)
        if in_bull_gp and is_bull_macro and is_candle_rebound and rsi <= 58.0:
            if ema21_bias_pct > max_ema21_bias_pct:
                return None, f"均線正乖離過大禁止追高 (Bias=+{ema21_bias_pct:.2f}% > +{max_ema21_bias_pct:.2f}%，等待回踩貼近EMA21)"
            return "LONG", f"現貨斐波那契黃金口袋支撐低接 (RSI={rsi:.1f}, 48h 0.5~0.65 結構支撐)"
        if cur_price >= ema21 * 0.998 and is_bull_macro and rsi <= 55.0:
            if ema21_bias_pct > max_ema21_bias_pct:
                return None, f"均線正乖離過大禁止追高 (Bias=+{ema21_bias_pct:.2f}% > +{max_ema21_bias_pct:.2f}%，等待回踩貼近EMA21)"
            return "LONG", f"現貨順勢均線支撐回踩確認 (RSI={rsi:.1f}, Bias={ema21_bias_pct:+.2f}%, 貼近EMA21>=EMA50)"
        if rsi < 38.0 and is_candle_rebound:
            return "LONG", f"現貨短線超賣止跌勾頭低接 (RSI={rsi:.1f}<38, 現價高於前收)"

    return None, ""


def evaluate_three_stage_exit(
    pnl_pct: float,
    peak_pct: float,
    sl_threshold: float,
    tp_threshold: float,
    pullback_threshold: float,
    breakeven_trigger_pct: Optional[float] = None,
    breakeven_floor_pct: Optional[float] = None,
    rsi: Optional[float] = None,
    side: str = "LONG",
) -> Tuple[Optional[str], str]:
    """Evaluate 3-Stage Exit Shield:
    - Stage 1: Hard Stop-Loss (-sl_threshold)
    - Stage 2: Break-Even Ratchet (once peak_pct >= breakeven_trigger_pct, protect +breakeven_floor_pct)
    - Stage 3: Trailing Take-Profit (once peak_pct >= tp_threshold and pullback >= pullback_threshold)
    """
    pullback = peak_pct - pnl_pct
    be_trigger = breakeven_trigger_pct if breakeven_trigger_pct is not None else (tp_threshold * 0.5)
    if breakeven_floor_pct is None:
        if tp_threshold >= 10.0:
            be_floor = 1.5
        elif tp_threshold >= 3.0:
            be_floor = 0.5
        else:
            be_floor = 0.25
    else:
        be_floor = breakeven_floor_pct

    # Stage 1: Hard Stop Loss
    if pnl_pct <= -sl_threshold:
        return "STOP_LOSS", f"自適應保證金停損觸發 (虧損達 {pnl_pct:.2f}%, 截斷風險)"

    # Extreme RSI Exhaustion Take Profit
    if rsi is not None:
        if side == "LONG" and rsi >= 75.0 and pnl_pct >= be_trigger:
            return "TAKE_PROFIT", f"1h RSI 極端超買停利 (RSI={rsi:.1f} >= 75, 獲利 +{pnl_pct:.2f}%)"
        if side == "SHORT" and rsi <= 25.0 and pnl_pct >= be_trigger:
            return "TAKE_PROFIT", f"1h RSI 極端超賣停利 (RSI={rsi:.1f} <= 25, 獲利 +{pnl_pct:.2f}%)"

    # Stage 3: Full Trailing Take Profit
    if peak_pct >= tp_threshold and pullback >= pullback_threshold:
        return "TAKE_PROFIT", f"動態移動停利 (最高獲利 +{peak_pct:.2f}% 回撤 {pullback:.2f}%, 鎖定 +{pnl_pct:.2f}%)"

    # Stage 2: Break-Even Ratchet Shield (Halfway target reached, then pulled back to breakeven floor)
    if peak_pct >= be_trigger and pnl_pct <= be_floor:
        return (
            "BREAKEVEN_STOP",
            f"保本推移鎖利觸發 (最高浮盈曾達 +{peak_pct:.2f}% 突破半程門檻，回落守住 +{pnl_pct:.2f}% 保本底線)",
        )

    return None, ""


def sync_breakeven_stop_loss(
    pos: Dict[str, Any],
    cur_price: float,
    peak_pct: float,
    tp_threshold: float,
    leverage: int,
    symbol: str,
    market_type: str,
    gw: Any,
    journal_mgr: Any,
) -> Optional[float]:
    """Synchronize exchange-side STOP_MARKET order and journal stop_loss_price up to Break-Even
    once peak_pct reaches the halfway take-profit threshold (tp_threshold * 0.5).
    """
    if pos.get("breakeven_synced", False):
        return None

    be_trigger = tp_threshold * 0.5
    if peak_pct < be_trigger:
        return None

    entry_price = float(pos.get("entry_price", 0.0))
    qty = float(pos.get("amount_btc", pos.get("amount", 0.0)))
    side = str(pos.get("side", "NONE")).upper()
    if entry_price <= 0 or qty <= 0 or side not in ("LONG", "SHORT"):
        return None

    if tp_threshold >= 10.0:
        be_floor_margin_pct = 1.5
    elif tp_threshold >= 3.0:
        be_floor_margin_pct = 0.5
    else:
        be_floor_margin_pct = 0.25

    be_price_offset_pct = max(0.10, be_floor_margin_pct / max(leverage, 1))
    if side == "LONG":
        be_stop_price = round(entry_price * (1.0 + be_price_offset_pct / 100.0), 2)
        if cur_price <= be_stop_price:
            return None
    else:
        be_stop_price = round(entry_price * (1.0 - be_price_offset_pct / 100.0), 2)
        if cur_price >= be_stop_price:
            return None

    if gw is not None and hasattr(gw, "update_stop_loss_order"):
        res = gw.update_stop_loss_order(
            symbol=symbol,
            position_side=side,
            stop_price=be_stop_price,
            quantity=qty,
            old_sl_order_id=pos.get("sl_order_id"),
            market_type=market_type,
        )
        if isinstance(res, dict):
            data = res.get("data", {})
            order_dict = data.get("order", data) if isinstance(data, dict) else {}
            new_sl_id = order_dict.get("orderId") if isinstance(order_dict, dict) else None
            if new_sl_id:
                pos["sl_order_id"] = str(new_sl_id)

    pos["native_sl_price"] = be_stop_price
    pos["breakeven_synced"] = True

    journal_id = pos.get("journal_id")
    if journal_id and journal_mgr is not None and hasattr(journal_mgr, "update_stop_loss_price"):
        journal_mgr.update_stop_loss_price(
            journal_id=journal_id,
            new_stop_price=be_stop_price,
            new_stop_loss_pct=0.0,
            new_max_loss_usdt=0.0,
        )

    return be_stop_price


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
        gateway: Optional[BaseBrokerGateway] = None,
        strategy: Optional[BaseTradingModel] = None,
        ai_agent: Optional[Any] = None,
        event_bus: Optional[Any] = None,
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
        prod_data_dir = (root_dir / "data").resolve()
        if state_file:
            self.state_file = Path(state_file)
        else:
            clean_sym = self.symbol.replace("/", "_").replace("-", "_")
            if self.mode == "SWAP_3X" and self.symbol == "BTC/USDT" and capital == 100.0:
                self.state_file = root_dir / "data" / "autopilot_state.json"
            else:
                self.state_file = root_dir / "data" / f"autopilot_{clean_sym}_{self.mode.lower()}_{int(capital)}u.json"

        state_parent = self.state_file.resolve().parent
        if state_parent != prod_data_dir:
            self.journal_file = state_parent / "autopilot_journal.json"
            default_db_path = state_parent / "trade_journal_db.json"
            default_journals_dir = state_parent / "journals"
        else:
            self.journal_file = root_dir / "data" / "autopilot_journal.json"
            default_db_path = root_dir / "data" / "trade_journal_db.json"
            default_journals_dir = root_dir / "journals"

        self.journal_mgr = journal_mgr or TradeJournalManager(
            db_path=str(default_db_path),
            journals_dir=str(default_journals_dir),
        )

        # Hardware & Gateways (Supports Dependency Injection)
        self.gw = gateway or BingXGateway(
            dry_run=self.dry_run,
            use_vst=self.use_vst,
            enable_ws=True,
            default_market_type=MarketType.SWAP.value if "SWAP" in self.mode else MarketType.SPOT.value,
        )
        self.ai_agent = ai_agent or OllamaDecisionAgent(model=ollama_model)

        # Strategy Models (Supports Dependency Injection) & Adaptive Volatility Risk Math
        if "SWAP" in self.mode:
            try:
                self.gw.set_leverage(self.symbol, self.leverage)
            except Exception:
                pass
            self.strategy = strategy or SwapMultiRegimeModel(ema_span=21)
            self.price_sl_pct = price_sl_pct if price_sl_pct is not None else 1.5
            self.price_tp_pct = price_tp_pct if price_tp_pct is not None else (2.0 if self.leverage >= 10 else 1.0)
            self.price_pullback_pct = price_pullback_pct if price_pullback_pct is not None else (0.5 if self.leverage >= 10 else 0.33)
            self.margin_sl_threshold = self.price_sl_pct * self.leverage
            self.margin_tp_threshold = self.price_tp_pct * self.leverage
            self.margin_pullback_threshold = self.price_pullback_pct * self.leverage
        else:
            self.strategy = strategy or SpotMomentumPullbackModel(ema_span=21)
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
        self.event_bus: Optional[Any] = None
        self.load_state()
        if event_bus is not None:
            self.attach_event_bus(event_bus)

    def attach_event_bus(self, event_bus: Any) -> None:
        """Subscribe this engine to a MarketEventBus for real-time event-driven execution."""
        from packages.core.event_bus import TickerUpdateEvent

        self.event_bus = event_bus
        if hasattr(event_bus, "subscribe"):
            event_bus.subscribe(TickerUpdateEvent, self.on_ticker_event)

    def on_ticker_event(self, event: Any) -> Optional[Dict[str, Any]]:
        """Event-driven entry point triggered immediately by WebSocket push or Polling adapter."""
        ev_sym = getattr(event, "symbol", "").replace("-", "/").replace("_", "/").upper()
        my_sym = self.symbol.replace("-", "/").replace("_", "/").upper()
        if ev_sym != my_sym:
            return None
        ev_price = float(getattr(event, "price", 0.0) or 0.0)
        if ev_price <= 0:
            return None
        return self.step(override_price=ev_price)

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

    def step(self, override_price: Optional[float] = None) -> Dict[str, Any]:
        """Perform a single heartbeat or real-time event-driven evaluation tick.

        When STANDBY: Only refreshes tickers and computes portfolio value.
        When ARMED: Evaluates signals, AI multiple-choice veto, entry/exit.
        """
        m_type = "SWAP" if "SWAP" in self.mode else "SPOT"
        if override_price is not None and override_price > 0:
            cur_price = float(override_price)
        else:
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
        # A. Position Management (3-Stage Exit Shield: Hard SL / Break-Even Ratchet / Trailing TP)
        if side != "NONE":
            peak_pct = self.position.get("highest_pnl_pct", 0.0)
            exit_action, exit_reason = evaluate_three_stage_exit(
                pnl_pct=pnl_pct,
                peak_pct=peak_pct,
                sl_threshold=self.margin_sl_threshold,
                tp_threshold=self.margin_tp_threshold,
                pullback_threshold=self.margin_pullback_threshold,
                side=side,
            )
            if exit_action == "STOP_LOSS":
                closed = self._close_position(cur_price, reason=exit_reason)
                step_result["action_taken"] = "STOP_LOSS" if closed else "CLOSE_FAILED"
                step_result["message"] = (
                    f"已執行硬停損平倉 (虧損 {pnl_pct:.2f}%)"
                    if closed and not self.pending_order
                    else "部位已平倉；日誌或條件單清理待重試"
                    if closed
                    else "停損平倉未確認，保留持倉並等待對帳"
                )
                return step_result

            if exit_action == "BREAKEVEN_STOP":
                closed = self._close_position(cur_price, reason=exit_reason)
                step_result["action_taken"] = "BREAKEVEN_STOP" if closed else "CLOSE_FAILED"
                step_result["message"] = (
                    f"已執行保本推移鎖利平倉 (鎖定正報酬 +{pnl_pct:.2f}%)"
                    if closed and not self.pending_order
                    else "部位已平倉；日誌或條件單清理待重試"
                    if closed
                    else "保本平倉未確認，保留持倉並等待對帳"
                )
                return step_result

            if exit_action == "TAKE_PROFIT":
                closed = self._close_position(cur_price, reason=exit_reason)
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
            be_synced_price = sync_breakeven_stop_loss(
                pos=self.position,
                cur_price=cur_price,
                peak_pct=peak_pct,
                tp_threshold=self.margin_tp_threshold,
                leverage=self.leverage,
                symbol=self.symbol,
                market_type=m_type,
                gw=self.gw,
                journal_mgr=self.journal_mgr,
            )
            if be_synced_price is not None:
                self.save_state()
                step_result["message"] = f"已啟動雲端保本推移套保 (新停損價 ${be_synced_price:,.2f} | 浮盈 {pnl_pct:+.2f}%)"
            return step_result

        # B. Entry Evaluation (Only when flat and ARMED)
        signals = self._compute_market_signals(cur_price)
        rsi = signals["rsi"]

        # Strategy Candidate Decision (Structural Entry Filter + Fibonacci Golden Pocket + Anti-Knife + Anti-Chase + Cooldown)
        candidate_signal, candidate_reason = evaluate_structural_entry(
            self.mode, cur_price, signals, history=self.closed_trades
        )

        if not candidate_signal:
            step_result["message"] = (
                candidate_reason
                if candidate_reason
                else f"無開倉信號 (RSI={rsi:.1f}, 市價=${cur_price:,.2f})，等待標準型態"
            )
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
            "closed_at": raw_record["exit_time"],
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

    def _compute_market_signals(self, cur_price: float) -> Dict[str, Any]:
        """Compute live 1h technical and structural signals (EMA21, EMA50, Wilder RSI, ATR, 48h Fib Pocket)."""
        try:
            m_type = "SWAP" if "SWAP" in self.mode else "SPOT"
            klines = self.gw.fetch_klines(self.symbol, timeframe="1h", limit=100, market_type=m_type)
            if klines is not None and len(klines) >= 20:
                df = klines if isinstance(klines, pd.DataFrame) else pd.DataFrame(klines)
                closes = [float(x) for x in df["close"].tolist()]
                highs = [float(x) for x in df["high"].tolist()] if "high" in df.columns else closes
                lows = [float(x) for x in df["low"].tolist()] if "low" in df.columns else closes
                return compute_structural_indicators_from_ohlc(closes, highs, lows, cur_price)
        except Exception:
            pass
        return compute_structural_indicators_from_ohlc([cur_price], [cur_price], [cur_price], cur_price)

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
