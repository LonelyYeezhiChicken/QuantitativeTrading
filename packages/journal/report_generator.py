"""Quantitative Daily (08:00 AM / 18:00 PM) and Weekly (Monday) Report Generator.

Follows an Inverted-Pyramid structure:
- Part 1 (Front - Must Read): Executive Summary, Key Portfolio & Bot Metrics, Market Levels / Actionable Tuning Advice.
- Part 2 (Back - Optional Appendix): Detailed Trade-by-Trade Journal Log for reference when time permits.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from typing import Any, Callable, Dict, List, Optional

from packages.journal.manager import TradeJournalManager
from packages.journal.models import TradeJournalEntry

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TZ_TAIPEI = timezone(timedelta(hours=8))


class QuantReportGenerator:
    """Generates structured Daily (AM/PM) and Weekly Markdown reports from authoritative bot states and trade journals."""

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        journal_mgr: Optional[TradeJournalManager] = None,
        issue_publisher: Optional[Callable[[str, Path, List[str]], Optional[str]]] = None,
    ):
        self.root_dir = Path(root_dir) if root_dir else ROOT_DIR
        self.journal_mgr = journal_mgr or TradeJournalManager(
            db_path=str(self.root_dir / "data" / "trade_journal_db.json"),
            journals_dir=str(self.root_dir / "journals"),
        )
        self.issue_publisher = issue_publisher or self._default_gh_issue_publisher
        self.reports_dir = self.root_dir / "journals" / "reports"
        self.daily_dir = self.reports_dir / "daily"
        self.weekly_dir = self.reports_dir / "weekly"
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.weekly_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_gh_issue_publisher(title: str, body_file: Path, labels: List[str]) -> Optional[str]:
        """Publish a Markdown report file as a GitHub Issue via `gh issue create`."""
        cmd = ["gh", "issue", "create", "--title", title, "--body-file", str(body_file)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[-1].strip()
        return None

    @staticmethod
    def _parse_utc(ts_str: str) -> Optional[datetime]:
        if not ts_str:
            return None
        clean = ts_str.replace(" UTC", "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(clean[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(clean)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _filter_entries_in_window(
        self,
        entries: List[TradeJournalEntry],
        start_utc: datetime,
        end_utc: datetime,
    ) -> List[TradeJournalEntry]:
        matched: List[TradeJournalEntry] = []
        for e in entries:
            ref_ts = self._parse_utc(e.exit_time) if e.status == "CLOSED" and e.exit_time else self._parse_utc(e.entry_time)
            if ref_ts is None:
                continue
            if start_utc <= ref_ts <= end_utc:
                matched.append(e)
        matched.sort(key=lambda x: x.exit_time or x.entry_time, reverse=True)
        return matched

    def generate_daily_report(
        self,
        current_price: float,
        session: Optional[str] = None,
        now_local: Optional[datetime] = None,
        lookback_hours: int = 12,
        market_signals: Optional[Dict[str, Any]] = None,
        publish_issue: bool = False,
    ) -> Dict[str, Any]:
        """Generate the 08:00 AM or 18:00 PM Daily Report and persist it to journals/reports/daily/."""
        now_tp = (now_local or datetime.now(TZ_TAIPEI)).astimezone(TZ_TAIPEI)
        now_utc = now_tp.astimezone(timezone.utc)
        start_utc = now_utc - timedelta(hours=lookback_hours)

        if session is None:
            session_code = "AM" if now_tp.hour < 13 else "PM"
        else:
            session_code = session.upper()
        session_title = "早報 (08:00 晨間過夜盤點)" if session_code == "AM" else "晚報 (18:00 日盤收斂盤點)"

        from packages.core.state_repository import BotStateRepository

        bots = BotStateRepository.discover_active_bots(current_price, root_dir=self.root_dir)
        self.journal_mgr._load_db(merge=True)
        all_entries = self.journal_mgr.get_entries()
        window_entries = self._filter_entries_in_window(all_entries, start_utc, now_utc)
        closed_window = [e for e in window_entries if e.status == "CLOSED"]

        capital_base = sum(b["init_cap"] for b in bots) if bots else 400.0
        total_equity = sum(b["equity"] for b in bots) if bots else capital_base
        total_upnl = sum(b["upnl"] for b in bots)
        total_net_pnl = total_equity - capital_base
        total_net_pct = (total_net_pnl / capital_base * 100.0) if capital_base > 0 else 0.0
        open_bots = [b for b in bots if b.get("side") != "NONE"]

        window_pnl = sum(e.pnl_usdt for e in closed_window)
        window_wins = [e for e in closed_window if e.pnl_usdt > 0]
        window_wr = (len(window_wins) / len(closed_window) * 100.0) if closed_window else 0.0

        sig = market_signals or {}
        rsi = float(sig.get("rsi", 50.0))
        ema21 = float(sig.get("ema21", current_price))
        ema50 = float(sig.get("ema50", current_price))
        bias_pct = ((current_price - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0

        date_str = now_tp.strftime("%Y-%m-%d")
        report_filename = f"{date_str}_{session_code}.md"
        report_path = self.daily_dir / report_filename

        md_lines = [
            f"# 📊 量化操盤日報 — {date_str} {session_title}",
            f"> **產出時間**：{now_tp.strftime('%Y-%m-%d %H:%M:%S')} (台北時間 UTC+8) ｜ **BTC 現價**：`${current_price:,.2f}`",
            "",
            "---",
            "",
            "## 一、核心摘要與關鍵數字（必讀區）",
            "",
            "### 1. 一句話戰況結論",
            f"- **帳戶總體表現**：總本金 **`${capital_base:,.2f} U`** ➔ 當前總淨值 **`${total_equity:,.2f} U`**（累計總損益 **`{total_net_pnl:+,.2f} U` / `{total_net_pct:+.2f}%`**）。",
            f"- **近 {lookback_hours} 小時戰果**：共結算 **`{len(closed_window)}` 筆**交易，期間已實現損益 **`{window_pnl:+,.2f} U`**（勝率 `{window_wr:.1f}%`）；目前場上持倉 **`{len(open_bots)} / {len(bots)}` 台**（浮動損益 `{total_upnl:+,.2f} U`）。",
            f"- **當前盤勢位階**：BTC 1h RSI 為 `{rsi:.1f}`，EMA21 為 `${ema21:,.2f}`（乖離率 `{bias_pct:+.2f}%`），{'目前正乖離偏大（> +0.45%），防追高機制啟動中，等待回踩均線再切入' if bias_pct > 0.45 else ('處於多頭排列健康支撐區，隨時留意訊號切入' if ema21 >= ema50 else '均線偏弱整理中，嚴控逆勢風險')}。",
            "",
            "### 2. 四張單即時健康度與關鍵指標總表",
            "",
            "| 守護進程 | 模式 / 槓桿 | 初始本金 | **當前總淨值** | **累計報酬率** | 當前持倉狀態 | 浮動損益 (ROE) | 風控與強平保護 |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]

        for b in bots:
            net_ret = ((b["equity"] - b["init_cap"]) / b["init_cap"] * 100.0) if b["init_cap"] > 0 else 0.0
            clean_risk = str(b["risk_desc"]).replace(" | ", " ｜ ").replace("|", "｜")
            if b["side"] == "NONE":
                pos_str = "🟢 空倉待機"
                upnl_str = "—"
                risk_str = clean_risk
            else:
                pos_str = f"🔥 **{b['side']}** (`${b['cost']:,.1f}`)"
                upnl_str = f"`{b['upnl']:+,.2f} U` (`{b['upnl_pct']:+.2f}%`)"
                liq_txt = f"強平 `${b['liq_price']:,.0f}`" if b["liq_price"] > 0 else "現貨無強平"
                risk_str = f"{liq_txt} ｜ {clean_risk}"
            md_lines.append(
                f"| **{b['title']}** | `{b['market_type']} {b['leverage']}x` | `${b['init_cap']:,.0f} U` | "
                f"**`${b['equity']:,.2f} U`** | **`{net_ret:+.2f}%`** | {pos_str} | {upnl_str} | {risk_str} |"
            )

        md_lines.extend([
            "",
            "---",
            "",
            f"## 二、附錄：近 {lookback_hours} 小時交易日誌明細（備查區，有空再看）",
            "",
        ])

        if not window_entries:
            md_lines.append(f"*(近 {lookback_hours} 小時內無新增開倉或平倉交易紀錄，系統嚴格執行過濾紀律空手觀望中)*")
        else:
            md_lines.extend([
                "| 時間 (UTC) | 日誌編號 | 市場 | 方向 | 進場價 | 平倉/現價 | 損益 (USDT) | 報酬率 | 出場/狀態摘要 |",
                "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
            ])
            for e in window_entries:
                t_str = (e.exit_time or e.entry_time)[:16]
                mkt_str = f"{e.market_type} {e.leverage}x"
                exit_p_str = f"${e.exit_price:,.1f}" if e.status == "CLOSED" and e.exit_price > 0 else f"${current_price:,.1f} (持倉)"
                reason_first = (e.review.exit_reason or "").splitlines()[0].lstrip("- ").strip()[:48]
                md_lines.append(
                    f"| `{t_str}` | `{e.journal_id}` | `{mkt_str}` | **{e.side}** | `${e.entry_price:,.1f}` | "
                    f"`{exit_p_str}` | **`{e.pnl_usdt:+,.2f} U`** | `{e.pnl_pct:+.2f}%` | {reason_first} |"
                )

        content = "\n".join(md_lines) + "\n"
        report_path.write_text(content, encoding="utf-8")

        issue_title = f"[量化日報] {date_str} {session_title} | 總淨值 ${total_equity:,.2f}U ({total_net_pct:+.2f}%)"
        issue_url = self.issue_publisher(issue_title, report_path, ["daily-report"]) if publish_issue else None

        return {
            "report_type": "DAILY",
            "session": session_code,
            "date": date_str,
            "path": str(report_path),
            "issue_title": issue_title,
            "issue_url": issue_url,
            "capital_base": capital_base,
            "total_equity": total_equity,
            "total_net_pnl": total_net_pnl,
            "total_net_pct": total_net_pct,
            "window_trades_count": len(closed_window),
            "window_pnl_usdt": window_pnl,
            "window_win_rate_pct": window_wr,
            "bots": bots,
            "markdown": content,
        }

    def generate_weekly_report(
        self,
        current_price: float,
        now_local: Optional[datetime] = None,
        lookback_days: int = 7,
        publish_issue: bool = False,
    ) -> Dict[str, Any]:
        """Generate the Monday Weekly Report (independent from Daily Report) and persist to journals/reports/weekly/."""
        now_tp = (now_local or datetime.now(TZ_TAIPEI)).astimezone(TZ_TAIPEI)
        now_utc = now_tp.astimezone(timezone.utc)
        start_utc = now_utc - timedelta(days=lookback_days)

        iso_year, iso_week, _ = now_tp.isocalendar()
        week_tag = f"{iso_year}-W{iso_week:02d}"
        report_filename = f"{week_tag}.md"
        report_path = self.weekly_dir / report_filename

        from packages.core.state_repository import BotStateRepository

        bots = BotStateRepository.discover_active_bots(current_price, root_dir=self.root_dir)
        self.journal_mgr._load_db(merge=True)
        all_entries = self.journal_mgr.get_entries()
        week_entries = self._filter_entries_in_window(all_entries, start_utc, now_utc)
        closed_week = [e for e in week_entries if e.status == "CLOSED"]

        capital_base = sum(b["init_cap"] for b in bots) if bots else 400.0
        total_equity = sum(b["equity"] for b in bots) if bots else capital_base
        total_net_pnl = total_equity - capital_base
        total_net_pct = (total_net_pnl / capital_base * 100.0) if capital_base > 0 else 0.0

        wins = [e for e in closed_week if e.pnl_usdt > 0]
        losses = [e for e in closed_week if e.pnl_usdt < 0]
        week_pnl = sum(e.pnl_usdt for e in closed_week)
        week_wr = (len(wins) / len(closed_week) * 100.0) if closed_week else 0.0
        gross_win = sum(e.pnl_usdt for e in wins)
        gross_loss = abs(sum(e.pnl_usdt for e in losses))
        pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

        # Rank bots by cumulative return %
        ranked_bots = sorted(
            bots,
            key=lambda b: ((b["equity"] - b["init_cap"]) / b["init_cap"] * 100.0) if b["init_cap"] > 0 else 0.0,
            reverse=True,
        )
        best_bot = ranked_bots[0] if ranked_bots else None
        worst_bot = ranked_bots[-1] if ranked_bots else None

        # Exit attribution breakdown
        tp_cnt = sum(1 for e in closed_week if e.pnl_usdt > 0 and ("停利" in e.review.exit_reason or "超買" in e.review.exit_reason or "超賣" in e.review.exit_reason))
        sl_cnt = sum(1 for e in closed_week if e.pnl_usdt < 0)
        other_cnt = max(0, len(closed_week) - tp_cnt - sl_cnt)

        # Synthesize actionable weekly tuning advice
        advice_list: List[str] = []
        if best_bot:
            b_ret = (best_bot["equity"] - best_bot["init_cap"]) / best_bot["init_cap"] * 100.0
            advice_list.append(
                f"**本週冠軍配置**：`{best_bot['short_title']} ({best_bot['title']})` 目前淨值 `${best_bot['equity']:,.2f} U` (`{b_ret:+.2f}%`)，順勢結構與保本鎖利配合穩定，建議維持現有參數。"
            )
        if sl_cnt > tp_cnt and len(closed_week) >= 3:
            advice_list.append(
                f"**停損頻率偏高警示**：本週硬停損筆數（`{sl_cnt}` 筆）高於停利筆數（`{tp_cnt}` 筆），主要集中於高倍槓桿短線震盪洗盤；若下週盤勢維持橫盤，建議將 50x 調降為 20x 或拉寬 ATR 停損倍數。"
            )
        else:
            advice_list.append(
                f"**風控期望值健康**：本週獲利因子 (Profit Factor) 達 `{pf:.2f}`，防追高 (`Bias <= 0.45%`) 與平倉後 15 分鐘冷卻鎖有效減少連續停損。"
            )

        md_lines = [
            f"# 🏆 量化操盤週報 — {week_tag}（過去 {lookback_days} 日策略總體檢）",
            f"> **產出時間**：{now_tp.strftime('%Y-%m-%d %H:%M:%S')} (台北時間 UTC+8) ｜ **統計區間**：{start_utc.strftime('%Y-%m-%d')} ~ {now_tp.strftime('%Y-%m-%d')}",
            "",
            "---",
            "",
            "## 一、核心摘要與關鍵數字（必讀區）",
            "",
            "### 1. 本週關鍵績效總結",
            f"- **總資產淨值**：**`${total_equity:,.2f} USDT`**（總本金 `${capital_base:,.2f} U`，累計淨損益 **`{total_net_pnl:+,.2f} U` / `{total_net_pct:+.2f}%`**）",
            f"- **本週已實現戰績**：共完成 **`{len(closed_week)}` 筆**交易｜淨利 **`{week_pnl:+,.2f} U`**｜勝率 **`{week_wr:.1f}%`**（{len(wins)} 勝 {len(losses)} 敗）｜獲利因子 (PF) **`{pf:.2f}`**",
            f"- **出場結構歸因**：移動/目標停利 `{tp_cnt}` 筆 ｜ 硬停損截斷 `{sl_cnt}` 筆 ｜ 保本/手動結算 `{other_cnt}` 筆",
            "",
            "### 2. 四張單 7 日績效賽馬排行榜（由高至低）",
            "",
            "| 排名 | 守護進程 | 槓桿 | 初始本金 | **當前總淨值** | **累計淨報酬** | 目前狀態 |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        for idx, b in enumerate(ranked_bots, start=1):
            ret_p = ((b["equity"] - b["init_cap"]) / b["init_cap"] * 100.0) if b["init_cap"] > 0 else 0.0
            medal = "🥇 1" if idx == 1 else ("🥈 2" if idx == 2 else ("🥉 3" if idx == 3 else f"{idx}"))
            md_lines.append(
                f"| {medal} | **{b['title']}** | `{b['leverage']}x` | `${b['init_cap']:,.0f} U` | "
                f"**`${b['equity']:,.2f} U`** | **`{ret_p:+.2f}%`** | {b['side']} |"
            )

        md_lines.extend([
            "",
            "### 3. 下週具體優化與行動建議",
        ])
        for item in advice_list:
            md_lines.append(f"- {item}")

        md_lines.extend([
            "",
            "---",
            "",
            f"## 二、附錄：本週（近 {lookback_days} 日）完整交易日誌清單（備查區，有空再看）",
            "",
        ])

        if not week_entries:
            md_lines.append("*(本週區間內尚無交易紀錄)*")
        else:
            md_lines.extend([
                "| 時間 (UTC) | 日誌編號 | 市場 | 方向 | 進場價 | 平倉價 | 實現損益 | 報酬率 | MFE / MAE |",
                "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
            ])
            for e in week_entries:
                t_str = (e.exit_time or e.entry_time)[:16]
                mkt_str = f"{e.market_type} {e.leverage}x"
                mfe_mae = f"+{e.trajectory.mfe_pct:.1f}% / {e.trajectory.mae_pct:.1f}%"
                md_lines.append(
                    f"| `{t_str}` | `{e.journal_id}` | `{mkt_str}` | **{e.side}** | `${e.entry_price:,.1f}` | "
                    f"`${e.exit_price:,.1f}` | **`{e.pnl_usdt:+,.2f} U`** | `{e.pnl_pct:+.2f}%` | `{mfe_mae}` |"
                )

        content = "\n".join(md_lines) + "\n"
        report_path.write_text(content, encoding="utf-8")

        issue_title = f"[量化週報] {week_tag} 策略總體檢 | 總淨值 ${total_equity:,.2f}U ({total_net_pct:+.2f}%) | PF {pf:.2f}"
        issue_url = self.issue_publisher(issue_title, report_path, ["weekly-report"]) if publish_issue else None

        return {
            "report_type": "WEEKLY",
            "week_tag": week_tag,
            "path": str(report_path),
            "issue_title": issue_title,
            "issue_url": issue_url,
            "capital_base": capital_base,
            "total_equity": total_equity,
            "total_net_pnl": total_net_pnl,
            "total_net_pct": total_net_pct,
            "week_trades_count": len(closed_week),
            "week_pnl_usdt": week_pnl,
            "week_win_rate_pct": week_wr,
            "profit_factor": pf,
            "ranked_bots": ranked_bots,
            "markdown": content,
        }
