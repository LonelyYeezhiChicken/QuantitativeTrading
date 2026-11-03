"""Trade Journal Data Models and Structured Representations."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from datetime import datetime, timezone


@dataclass
class MarketSnapshot:
    """Market technical context captured at the moment of entry."""
    price: float = 0.0
    rsi: float = 50.0
    ema21: float = 0.0
    atr: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    bias_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketSnapshot":
        if not data:
            return cls()
        return cls(
            price=float(data.get("price", 0.0)),
            rsi=float(data.get("rsi", 50.0)),
            ema21=float(data.get("ema21", 0.0)),
            atr=float(data.get("atr", 0.0)),
            bid=float(data.get("bid", 0.0)),
            ask=float(data.get("ask", 0.0)),
            bias_pct=float(data.get("bias_pct", 0.0)),
        )


@dataclass
class RiskPlan:
    """Pre-trade risk management and invalidation rules."""
    stop_loss_price: float = 0.0
    stop_loss_pct: float = 2.5
    take_profit_type: str = "TRAILING"
    trailing_pullback_pct: float = 1.2
    planned_rr_ratio: float = 2.0
    max_loss_usdt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskPlan":
        if not data:
            return cls()
        return cls(
            stop_loss_price=float(data.get("stop_loss_price", 0.0)),
            stop_loss_pct=float(data.get("stop_loss_pct", 2.5)),
            take_profit_type=str(data.get("take_profit_type", "TRAILING")),
            trailing_pullback_pct=float(data.get("trailing_pullback_pct", 1.2)),
            planned_rr_ratio=float(data.get("planned_rr_ratio", 2.0)),
            max_loss_usdt=float(data.get("max_loss_usdt", 0.0)),
        )


@dataclass
class TradeTrajectory:
    """In-trade dynamics, tracking MFE (peak favorable) and MAE (max adverse)."""
    highest_price: float = 0.0
    lowest_price: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    duration_seconds: int = 0
    updates_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeTrajectory":
        if not data:
            return cls()
        return cls(
            highest_price=float(data.get("highest_price", 0.0)),
            lowest_price=float(data.get("lowest_price", 0.0)),
            mfe_pct=float(data.get("mfe_pct", 0.0)),
            mae_pct=float(data.get("mae_pct", 0.0)),
            duration_seconds=int(data.get("duration_seconds", 0)),
            updates_count=int(data.get("updates_count", 0)),
        )


@dataclass
class ReviewNote:
    """Educational review, post-trade analysis, and manual trader takeaways."""
    thesis: str = ""
    exit_reason: str = ""
    strategy_evaluation: str = ""
    pedagogical_takeaway: str = ""
    quality_score: int = 3  # 1 to 5 scale

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewNote":
        if not data:
            return cls()
        return cls(
            thesis=str(data.get("thesis", "")),
            exit_reason=str(data.get("exit_reason", "")),
            strategy_evaluation=str(data.get("strategy_evaluation", "")),
            pedagogical_takeaway=str(data.get("pedagogical_takeaway", "")),
            quality_score=int(data.get("quality_score", 3)),
        )


@dataclass
class TradeJournalEntry:
    """Comprehensive Trade Journal Entry for an individual trade."""
    journal_id: str
    symbol: str = "BTC/USDT"
    market_type: str = "SPOT"       # "SPOT" or "SWAP"
    side: str = "LONG"              # "LONG" or "SHORT"
    status: str = "OPEN"            # "OPEN" or "CLOSED"
    entry_time: str = ""
    exit_time: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    amount_btc: float = 0.0
    margin_used: float = 0.0
    leverage: int = 1
    notional_value: float = 0.0
    pnl_usdt: float = 0.0
    pnl_pct: float = 0.0
    realized_r_multiple: float = 0.0
    liquidation_price: float = 0.0
    snapshot: MarketSnapshot = field(default_factory=MarketSnapshot)
    risk_plan: RiskPlan = field(default_factory=RiskPlan)
    trajectory: TradeTrajectory = field(default_factory=TradeTrajectory)
    review: ReviewNote = field(default_factory=ReviewNote)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "journal_id": self.journal_id,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "side": self.side,
            "status": self.status,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "amount_btc": self.amount_btc,
            "margin_used": self.margin_used,
            "leverage": self.leverage,
            "notional_value": self.notional_value,
            "pnl_usdt": self.pnl_usdt,
            "pnl_pct": self.pnl_pct,
            "realized_r_multiple": self.realized_r_multiple,
            "liquidation_price": self.liquidation_price,
            "snapshot": self.snapshot.to_dict(),
            "risk_plan": self.risk_plan.to_dict(),
            "trajectory": self.trajectory.to_dict(),
            "review": self.review.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradeJournalEntry":
        return cls(
            journal_id=str(data.get("journal_id", "")),
            symbol=str(data.get("symbol", "BTC/USDT")),
            market_type=str(data.get("market_type", "SPOT")),
            side=str(data.get("side", "LONG")),
            status=str(data.get("status", "OPEN")),
            entry_time=str(data.get("entry_time", "")),
            exit_time=str(data.get("exit_time", "")),
            entry_price=float(data.get("entry_price", 0.0)),
            exit_price=float(data.get("exit_price", 0.0)),
            amount_btc=float(data.get("amount_btc", 0.0)),
            margin_used=float(data.get("margin_used", 0.0)),
            leverage=int(data.get("leverage", 1)),
            notional_value=float(data.get("notional_value", 0.0)),
            pnl_usdt=float(data.get("pnl_usdt", 0.0)),
            pnl_pct=float(data.get("pnl_pct", 0.0)),
            realized_r_multiple=float(data.get("realized_r_multiple", 0.0)),
            liquidation_price=float(data.get("liquidation_price", 0.0)),
            snapshot=MarketSnapshot.from_dict(data.get("snapshot", {})),
            risk_plan=RiskPlan.from_dict(data.get("risk_plan", {})),
            trajectory=TradeTrajectory.from_dict(data.get("trajectory", {})),
            review=ReviewNote.from_dict(data.get("review", {})),
        )

    def to_markdown(self) -> str:
        """Render a clean, publication-ready educational Trade Journal markdown card."""
        duration_min = self.trajectory.duration_seconds // 60 if self.trajectory.duration_seconds else 0
        pnl_sign = "+" if self.pnl_usdt >= 0 else ""
        pnl_pct_sign = "+" if self.pnl_pct >= 0 else ""

        md = []
        md.append(f"# 交易學習日誌：{self.journal_id}")
        md.append("")
        md.append(f"> 標的：`{self.symbol}` | 市場：`{self.market_type}` | 方向：`{self.side}` | 狀態：`{self.status}`")
        md.append("")
        md.append("## 一、基本交易參數")
        md.append("")
        md.append("| 項目 | 數值 | 項目 | 數值 |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| 開倉時間 | `{self.entry_time}` | 平倉時間 | `{self.exit_time if self.exit_time else '持倉中'}` |")
        md.append(f"| 開倉均價 | `${self.entry_price:,.2f}` | 平倉均價 | `${self.exit_price:,.2f}` |" if self.status == "CLOSED" else f"| 開倉均價 | `${self.entry_price:,.2f}` | 平倉均價 | 持倉中 |")
        md.append(f"| 部位數量 | `{self.amount_btc:.6f} BTC` | 槓桿倍數 | `{self.leverage}x` |")
        md.append(f"| 投入保證金 | `${self.margin_used:,.2f} USDT` | 名義價值 | `${self.notional_value:,.2f} USDT` |")
        if self.market_type == "SWAP":
            md.append(f"| 強平參考價 | `${self.liquidation_price:,.2f}` | 持倉時長 | `{duration_min} 分鐘` |")
        else:
            md.append(f"| 持倉時長 | `{duration_min} 分鐘` | 交易市場 | 現貨無爆倉風險 |")
        md.append(f"| 實現盈虧 (PnL) | `{pnl_sign}${self.pnl_usdt:,.2f} USDT` | 收益率 (ROI) | `{pnl_pct_sign}{self.pnl_pct:.2f}%` |")
        md.append(f"| 實現 R 倍數 | `{self.realized_r_multiple:+.2f}R` | 執行品質評分 | `{'★' * self.review.quality_score}{'☆' * (5 - self.review.quality_score)}` ({self.review.quality_score}/5) |")
        md.append("")
        md.append("## 二、進場環境與技術面快照")
        md.append("")
        md.append("| 指標項目 | 進場數值 | 技術解讀與情境 |")
        md.append("| :--- | :--- | :--- |")
        md.append(f"| 進場市價 | `${self.snapshot.price:,.2f}` | 基準執行價格 |")
        md.append(f"| RSI (14) | `{self.snapshot.rsi:.1f}` | {'超買區鈍化/多頭加速' if self.snapshot.rsi >= 65 else '超賣區底背離/均值回歸' if self.snapshot.rsi <= 35 else '中性突破/動能確認'} |")
        md.append(f"| EMA 21 | `${self.snapshot.ema21:,.2f}` | 價格偏離度 (Bias): `{self.snapshot.bias_pct:+.2f}%` |")
        md.append(f"| ATR (14) 波動度 | `${self.snapshot.atr:,.2f}` | 代表 1 小時平均震幅 |")
        md.append(f"| 買賣掛單點差 | `${abs(self.snapshot.ask - self.snapshot.bid):.2f}` | 市場流動性正常 |")
        md.append("")
        md.append("## 三、前置風控計畫 (Pre-Trade Risk Management)")
        md.append("")
        md.append(f"- **停損規劃 (Stop Loss)**：設定於 `${self.risk_plan.stop_loss_price:,.2f}`（距離成本 `- {self.risk_plan.stop_loss_pct:.1f}%`），最大承受風險 `${self.risk_plan.max_loss_usdt:,.2f} USDT`。")
        md.append(f"- **停利規劃 (Take Profit)**：採用 `{self.risk_plan.take_profit_type}` 動態機制，高點回撤 `{self.risk_plan.trailing_pullback_pct:.1f}%` 即刻鎖定利潤。")
        md.append(f"- **預期風報比 (Planned R:R)**：`1 : {self.risk_plan.planned_rr_ratio:.1f}`。")
        md.append("")
        md.append("## 四、盤中軌跡動態 (In-Trade Trajectory)")
        md.append("")
        md.append(f"- **區間最高價**：`${self.trajectory.highest_price:,.2f}` (最高有利幅度 MFE: `+{self.trajectory.mfe_pct:.2f}%`)")
        md.append(f"- **區間最低價**：`${self.trajectory.lowest_price:,.2f}` (最大不利幅度 MAE: `{self.trajectory.mae_pct:.2f}%`)")
        md.append(f"- **心跳輪詢次數**：`{self.trajectory.updates_count}` 次")
        md.append("")
        md.append("## 五、學習覆盤與策略反思 (Pedagogical Reflection)")
        md.append("")
        md.append(f"### 1. 進場立論假說 (Trade Thesis)\n{self.review.thesis}\n")
        md.append(f"### 2. 出場歸因 (Exit Catalyst)\n{self.review.exit_reason}\n")
        md.append(f"### 3. 策略執行評價 (Strategy Evaluation)\n{self.review.strategy_evaluation}\n")
        md.append(f"### 4. 給操盤手的學習心得與啟發 (Pedagogical Takeaway)\n{self.review.pedagogical_takeaway}\n")
        md.append("---")
        md.append(f"*日誌由量化自主操盤守護進程自動生成 | 時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*")
        return "\n".join(md)
