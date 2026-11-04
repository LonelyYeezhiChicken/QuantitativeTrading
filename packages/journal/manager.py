"""Trade Journal Manager for Life-Cycle Tracking, Storage, and Markdown Generation."""

import os
import json
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from packages.journal.models import (
    TradeJournalEntry,
    MarketSnapshot,
    RiskPlan,
    TradeTrajectory,
    ReviewNote,
)
from packages.journal.analyzer import JournalAnalyzer


class TradeJournalManager:
    """Central manager handling persistence, multi-process concurrency, lifecycle updates, and markdown rendering."""

    def __init__(
        self,
        db_path: str = "data/trade_journal_db.json",
        journals_dir: str = "journals",
    ):
        self.db_path = Path(db_path)
        self.journals_dir = Path(journals_dir)
        self.entries_dir = self.journals_dir / "entries"
        self.index_file = self.journals_dir / "INDEX.md"

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.entries_dir.mkdir(parents=True, exist_ok=True)

        self._entries: Dict[str, TradeJournalEntry] = {}
        self._load_db(merge=False)

    def _load_db(self, merge: bool = True):
        """Load trade journal database from disk and optionally merge with in-memory entries."""
        if not self.db_path.exists():
            if not merge:
                self._entries = {}
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            disk_entries = {
                item["journal_id"]: TradeJournalEntry.from_dict(item)
                for item in data.get("entries", [])
                if "journal_id" in item
            }
            if not merge or not self._entries:
                self._entries = disk_entries
            else:
                for jid, d_entry in disk_entries.items():
                    if jid not in self._entries:
                        self._entries[jid] = d_entry
                    else:
                        mem_entry = self._entries[jid]
                        # If disk has a CLOSED entry with exit details, always adopt the complete closed record
                        if d_entry.status == "CLOSED" and (mem_entry.status != "CLOSED" or (d_entry.exit_price > 0 and mem_entry.exit_price == 0)):
                            self._entries[jid] = d_entry
                        elif (
                            d_entry.status == mem_entry.status
                            and d_entry.trajectory.updates_count > mem_entry.trajectory.updates_count
                        ):
                            mem_entry.trajectory = d_entry.trajectory
                            if d_entry.risk_plan:
                                mem_entry.risk_plan = d_entry.risk_plan
        except Exception:
            if not merge:
                self._entries = {}

    def _save_db(self, updated_entry: Optional[TradeJournalEntry] = None):
        """Synchronize with disk entries and atomically save trade journal database."""
        self._load_db(merge=True)
        if updated_entry is not None:
            self._entries[updated_entry.journal_id] = updated_entry

        data = {
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_entries": len(self._entries),
            "entries": [e.to_dict() for e in self._entries.values()],
        }
        # Unique per process AND thread: concurrent writers must never share a temp file.
        tmp_path = self.db_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            replaced = False
            for _ in range(5):
                try:
                    os.replace(tmp_path, self.db_path)
                    replaced = True
                    break
                except PermissionError:
                    time.sleep(0.02)
            if not replaced:
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def on_trade_open(
        self,
        symbol: str,
        market_type: str,
        side: str,
        entry_price: float,
        amount_btc: float,
        margin_used: float,
        leverage: int = 1,
        raw_reason: str = "",
        snapshot_dict: Optional[Dict[str, Any]] = None,
        stop_loss_pct: float = 2.5,
        trailing_pullback_pct: float = 1.2,
        entry_time_str: Optional[str] = None,
        custom_id: Optional[str] = None,
    ) -> TradeJournalEntry:
        """Record the initiation of a trade with market snapshot, risk rules, and thesis."""
        self._load_db(merge=True)
        now_utc = datetime.now(timezone.utc)
        entry_time = entry_time_str or now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

        time_tag = now_utc.strftime("%Y%m%d_%H%M%S")
        if entry_time_str:
            try:
                parsed_dt = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S UTC")
                time_tag = parsed_dt.strftime("%Y%m%d_%H%M%S")
            except Exception:
                pass

        if custom_id:
            journal_id = custom_id
        else:
            base_id = f"{market_type.upper()}_{time_tag}_{side.upper()}"
            journal_id = base_id
            if journal_id in self._entries:
                lev_id = f"{market_type.upper()}_{leverage}X_{time_tag}_{side.upper()}"
                if lev_id not in self._entries:
                    journal_id = lev_id
                else:
                    seq = 2
                    while f"{lev_id}_{seq}" in self._entries:
                        seq += 1
                    journal_id = f"{lev_id}_{seq}"

        snapshot_dict = snapshot_dict or {}
        price = snapshot_dict.get("price", entry_price)
        ema21 = snapshot_dict.get("ema21", price)
        bias = ((price - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0

        snapshot = MarketSnapshot(
            price=price,
            rsi=snapshot_dict.get("rsi", 50.0),
            ema21=ema21,
            atr=snapshot_dict.get("atr", price * 0.015),
            bid=snapshot_dict.get("bid", price),
            ask=snapshot_dict.get("ask", price),
            bias_pct=bias,
        )

        # Risk Plan
        notional = margin_used * leverage
        if side.upper() == "LONG":
            sl_price = entry_price * (1.0 - (stop_loss_pct / 100.0 / leverage))
        else:
            sl_price = entry_price * (1.0 + (stop_loss_pct / 100.0 / leverage))
        max_loss = margin_used * (stop_loss_pct / 100.0)

        risk_plan = RiskPlan(
            stop_loss_price=sl_price,
            stop_loss_pct=stop_loss_pct,
            take_profit_type="TRAILING",
            trailing_pullback_pct=trailing_pullback_pct,
            planned_rr_ratio=2.0,
            max_loss_usdt=max_loss,
        )

        # Trajectory
        trajectory = TradeTrajectory(
            highest_price=entry_price,
            lowest_price=entry_price,
            mfe_pct=0.0,
            mae_pct=0.0,
            duration_seconds=0,
            updates_count=1,
        )

        # Pre-trade Thesis
        thesis = JournalAnalyzer.generate_entry_thesis(snapshot, side.upper(), market_type.upper(), raw_reason)
        review = ReviewNote(
            thesis=thesis,
            exit_reason="持倉中，持續依據風控計畫動態監控中",
            strategy_evaluation="部位建倉符合量化規則，等待市場驗證假說",
            pedagogical_takeaway="耐心持有，嚴格遵守預設止損與追蹤停利邏輯，不受短線雜訊干擾情緒",
            quality_score=3,
        )

        # Liquidation price estimation
        liq_price = 0.0
        if market_type.upper() == "SWAP":
            if side.upper() == "LONG":
                liq_price = entry_price * (1.0 - (0.9 / leverage))
            else:
                liq_price = entry_price * (1.0 + (0.9 / leverage))

        entry = TradeJournalEntry(
            journal_id=journal_id,
            symbol=symbol,
            market_type=market_type.upper(),
            side=side.upper(),
            status="OPEN",
            entry_time=entry_time,
            exit_time="",
            entry_price=entry_price,
            exit_price=0.0,
            amount_btc=amount_btc,
            margin_used=margin_used,
            leverage=leverage,
            notional_value=notional,
            pnl_usdt=0.0,
            pnl_pct=0.0,
            realized_r_multiple=0.0,
            liquidation_price=liq_price,
            snapshot=snapshot,
            risk_plan=risk_plan,
            trajectory=trajectory,
            review=review,
        )

        self._entries[journal_id] = entry
        self._save_db(updated_entry=entry)
        self._write_entry_markdown(entry)
        self._render_index()
        return entry

    def update_stop_loss_price(
        self,
        journal_id: str,
        new_stop_price: float,
        new_stop_loss_pct: float = 0.0,
        new_max_loss_usdt: float = 0.0,
    ) -> Optional[TradeJournalEntry]:
        """Update the stop-loss price in an open trade journal entry (e.g., upon Break-Even Order Sync)."""
        self._load_db(merge=True)
        entry = self._entries.get(journal_id)
        if not entry or entry.status != "OPEN":
            return None
        from packages.execution.precision import round_price
        entry.risk_plan.stop_loss_price = round_price(new_stop_price)
        entry.risk_plan.stop_loss_pct = round(new_stop_loss_pct, 2)
        entry.risk_plan.max_loss_usdt = round(new_max_loss_usdt, 2)
        self._save_db(updated_entry=entry)
        self._write_entry_markdown(entry)
        return entry

    def on_trade_update(
        self,
        journal_id: str,
        current_price: float,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
    ) -> Optional[TradeJournalEntry]:
        """Update live trajectory (MFE, MAE, duration) for an open trade.

        high_price / low_price carry intra-interval extremes when callers throttle updates.
        """
        self._load_db(merge=True)
        entry = self._entries.get(journal_id)
        if not entry or entry.status != "OPEN":
            return entry

        traj = entry.trajectory
        side = entry.side
        entry_p = entry.entry_price
        lev = entry.leverage

        hi = max(current_price, high_price) if high_price is not None else current_price
        lo = min(current_price, low_price) if low_price is not None else current_price
        traj.highest_price = max(traj.highest_price, hi)
        traj.lowest_price = min(traj.lowest_price, lo) if traj.lowest_price > 0 else lo
        traj.updates_count += 1

        # Calculate MFE & MAE relative to margin
        if side == "LONG":
            mfe_p = (traj.highest_price - entry_p) / entry_p * 100.0 * lev
            mae_p = (traj.lowest_price - entry_p) / entry_p * 100.0 * lev
        else:
            mfe_p = (entry_p - traj.lowest_price) / entry_p * 100.0 * lev
            mae_p = (entry_p - traj.highest_price) / entry_p * 100.0 * lev

        traj.mfe_pct = max(0.0, mfe_p)
        traj.mae_pct = min(0.0, mae_p)

        # Duration
        try:
            t0 = datetime.strptime(entry.entry_time, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
            t1 = datetime.now(timezone.utc)
            traj.duration_seconds = max(0, int((t1 - t0).total_seconds()))
        except Exception:
            pass

        self._save_db(updated_entry=entry)
        self._write_entry_markdown(entry)
        return entry

    def on_trade_close(
        self,
        journal_id: str,
        exit_price: float,
        exit_reason: str,
        exit_time_str: Optional[str] = None,
    ) -> Optional[TradeJournalEntry]:
        """Finalize trade, synthesize pedagogical review, generate complete markdown card."""
        self._load_db(merge=True)
        entry = self._entries.get(journal_id)
        if not entry:
            return None

        now_utc = datetime.now(timezone.utc)
        entry.exit_time = exit_time_str or now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        entry.exit_price = exit_price
        entry.status = "CLOSED"

        # Update final duration
        try:
            t0 = datetime.strptime(entry.entry_time, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
            t1 = datetime.strptime(entry.exit_time, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
            entry.trajectory.duration_seconds = max(0, int((t1 - t0).total_seconds()))
        except Exception:
            pass

        # Calculate final PnL
        qty = entry.amount_btc
        if entry.side == "LONG":
            entry.pnl_usdt = (exit_price - entry.entry_price) * qty
        else:
            entry.pnl_usdt = (entry.entry_price - exit_price) * qty
        entry.pnl_pct = (entry.pnl_usdt / entry.margin_used) * 100.0 if entry.margin_used > 0 else 0.0

        # Generate detailed review
        review, r_mult = JournalAnalyzer.analyze_exit_and_review(entry, exit_price, exit_reason)
        entry.review = review
        entry.realized_r_multiple = r_mult

        self._save_db(updated_entry=entry)
        self._write_entry_markdown(entry)
        self._render_index()
        return entry

    def _write_entry_markdown(self, entry: TradeJournalEntry):
        """Render and save individual trade journal markdown file."""
        file_path = self.entries_dir / f"{entry.journal_id}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(entry.to_markdown())

    def _render_index(self):
        """Generate and write the comprehensive INDEX.md overview table."""
        stats = self.get_summary_stats()
        lines = []
        lines.append("# 量化交易自主學習日誌總覽 (Trade Journal Index)")
        lines.append("")
        lines.append("本總表由量化自主操盤系統即時維護，記錄所有現貨與永續合約實戰交易記錄與覆盤反思。")
        lines.append("")
        lines.append("## 一、總體績效指標 (Overall Statistics)")
        lines.append("")
        lines.append("| 總交易筆數 | 已平倉筆數 | 持倉中筆數 | 勝率 (Win Rate) | 累計實現盈虧 | 獲利因子 (PF) | 平均持倉時長 |")
        lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        lines.append(
            f"| {stats['total_trades']} | {stats['closed_trades']} | {stats['open_trades']} | "
            f"{stats['win_rate']:.1f}% | ${stats['total_pnl']:+,.2f} USDT | {stats['profit_factor']:.2f} | "
            f"{stats['avg_hold_time_min']:.0f} 分鐘 |"
        )
        lines.append("")
        lines.append("## 二、歷史交易日誌清單 (Trade Entries)")
        lines.append("")
        lines.append("| 日誌編號 (ID) | 開倉時間 | 市場 | 方向 | 開倉均價 | 平倉均價 | 實現盈虧 | 報酬率 | 評分 | 覆盤卡片 |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

        sorted_entries = sorted(self._entries.values(), key=lambda e: e.entry_time, reverse=True)
        for e in sorted_entries:
            pnl_str = f"${e.pnl_usdt:+,.2f}" if e.status == "CLOSED" else "持倉中"
            pnl_pct_str = f"{e.pnl_pct:+.2f}%" if e.status == "CLOSED" else "--"
            exit_p_str = f"${e.exit_price:,.2f}" if e.status == "CLOSED" else "持倉中"
            rating = f"{e.review.quality_score}★" if e.status == "CLOSED" else "評估中"
            link = f"[閱讀學習覆盤](entries/{e.journal_id}.md)"
            lines.append(
                f"| `{e.journal_id}` | {e.entry_time[:16]} | {e.market_type} | {e.side} | "
                f"${e.entry_price:,.2f} | {exit_p_str} | {pnl_str} | {pnl_pct_str} | {rating} | {link} |"
            )

        lines.append("")
        lines.append("---")
        lines.append(f"*最後更新時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*")

        with open(self.index_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculate statistical summaries across all trades."""
        self._load_db(merge=True)
        closed = [e for e in self._entries.values() if e.status == "CLOSED"]
        total_closed = len(closed)
        wins = [e for e in closed if e.pnl_usdt > 0]
        losses = [e for e in closed if e.pnl_usdt < 0]

        win_rate = (len(wins) / total_closed * 100.0) if total_closed > 0 else 0.0
        total_pnl = sum(e.pnl_usdt for e in closed)

        gross_profit = sum(e.pnl_usdt for e in wins)
        gross_loss = abs(sum(e.pnl_usdt for e in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 1.0)

        total_duration = sum(e.trajectory.duration_seconds for e in closed)
        avg_hold_min = (total_duration / total_closed / 60.0) if total_closed > 0 else 0.0

        return {
            "total_trades": len(self._entries),
            "closed_trades": total_closed,
            "open_trades": len(self._entries) - total_closed,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "profit_factor": profit_factor,
            "avg_hold_time_min": avg_hold_min,
        }

    def get_entries(
        self,
        market_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[TradeJournalEntry]:
        """Query entries with optional filters."""
        self._load_db(merge=True)
        res = list(self._entries.values())
        if market_type:
            res = [e for e in res if e.market_type == market_type.upper()]
        if status:
            res = [e for e in res if e.status == status.upper()]
        res = sorted(res, key=lambda e: e.entry_time, reverse=True)
        if limit:
            res = res[:limit]
        return res

    def get_entry(self, journal_id: str) -> Optional[TradeJournalEntry]:
        """Fetch single entry by ID."""
        self._load_db(merge=True)
        return self._entries.get(journal_id)
