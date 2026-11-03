"""CLI Interactive Viewer for Automated Trade Journal & Educational Reviews."""

import sys
import argparse
from pathlib import Path

# Force UTF-8 stdout encoding for Windows compatibility
sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.journal.manager import TradeJournalManager
from packages.journal.models import TradeJournalEntry


def print_entry_detail(entry: TradeJournalEntry):
    """Print full pedagogical trade review to terminal."""
    pnl_sign = "+" if entry.pnl_usdt >= 0 else ""
    pnl_pct_sign = "+" if entry.pnl_pct >= 0 else ""
    duration_min = entry.trajectory.duration_seconds // 60

    print("=" * 80)
    print(f"  交易自主學習覆盤日誌：{entry.journal_id}")
    print("=" * 80)
    print(f"  標的：{entry.symbol}  |  市場：{entry.market_type}  |  方向：{entry.side}  |  狀態：{entry.status}")
    print(f"  開倉時間：{entry.entry_time}  |  平倉時間：{entry.exit_time or '持倉中'}")
    print(f"  開倉均價：${entry.entry_price:,.2f}  |  平倉均價：${entry.exit_price:,.2f}" if entry.status == "CLOSED" else f"  開倉均價：${entry.entry_price:,.2f}  |  平倉均價：持倉中")
    print(f"  部位規模：{entry.amount_btc:.6f} BTC  |  槓桿倍數：{entry.leverage}x  |  保證金：${entry.margin_used:.2f} U")
    if entry.market_type == "SWAP":
        print(f"  強平參考價：${entry.liquidation_price:,.2f}  |  持倉時長：{duration_min} 分鐘")
    else:
        print(f"  持倉時長：{duration_min} 分鐘  |  市場性質：現貨資產交易")
    print(f"  實現盈虧：{pnl_sign}${entry.pnl_usdt:,.2f} USDT ({pnl_pct_sign}{entry.pnl_pct:.2f}%)  |  R倍數：{entry.realized_r_multiple:+.2f}R")
    print(f"  執行品質評分：{entry.review.quality_score} / 5 星")

    print("\n" + "-" * 80)
    print("  【進場技術面快照 (Technical Snapshot)】")
    print(f"  - 進場市價：${entry.snapshot.price:,.2f}  |  EMA21 均線：${entry.snapshot.ema21:,.2f} (乖離率: {entry.snapshot.bias_pct:+.2f}%)")
    print(f"  - RSI (14)：{entry.snapshot.rsi:.1f}  |  ATR 波動度：${entry.snapshot.atr:,.2f}")

    print("\n" + "-" * 80)
    print("  【前置風控與軌跡 (Risk & Trajectory)】")
    print(f"  - 預設止損：${entry.risk_plan.stop_loss_price:,.2f} (-{entry.risk_plan.stop_loss_pct:.1f}%)  |  預計最大風險：${entry.risk_plan.max_loss_usdt:.2f} U")
    print(f"  - 停利機制：{entry.risk_plan.take_profit_type} (回撤 {entry.risk_plan.trailing_pullback_pct:.1f}%)")
    print(f"  - 盤中最高價：${entry.trajectory.highest_price:,.2f} (MFE 最高浮盈: +{entry.trajectory.mfe_pct:.2f}%)")
    print(f"  - 盤中最低價：${entry.trajectory.lowest_price:,.2f} (MAE 最大回撤: {entry.trajectory.mae_pct:.2f}%)")

    print("\n" + "-" * 80)
    print("  【進場立論假說 (Trade Thesis)】")
    for line in entry.review.thesis.splitlines():
        print(f"    {line}")

    print("\n" + "-" * 80)
    print("  【出場歸因與策略評估 (Exit & Strategy Evaluation)】")
    for line in entry.review.exit_reason.splitlines():
        print(f"    {line}")
    for line in entry.review.strategy_evaluation.splitlines():
        print(f"    {line}")

    print("\n" + "-" * 80)
    print("  【給操盤手的學習心得與啟發 (Pedagogical Takeaway)】")
    for line in entry.review.pedagogical_takeaway.splitlines():
        print(f"    {line}")
    print("=" * 80 + "\n")


def print_list_view(mgr: TradeJournalManager, market_type: str = None):
    """Print clean terminal summary table of all entries."""
    stats = mgr.get_summary_stats()
    entries = mgr.get_entries(market_type=market_type)

    print("\n" + "=" * 90)
    print("  量化交易自主學習日誌總覽清單")
    print("=" * 90)
    print(f"  總筆數: {stats['total_trades']}  |  已結算: {stats['closed_trades']}  |  持倉中: {stats['open_trades']}")
    print(f"  勝率: {stats['win_rate']:.1f}% ({stats['wins']} 勝 / {stats['losses']} 負)  |  累計盈虧: ${stats['total_pnl']:+,.2f} U  |  獲利因子: {stats['profit_factor']:.2f}")
    print("-" * 90)
    print(f"{'日誌編號 (ID)':<24} {'時間':<17} {'市場':<6} {'方向':<6} {'開倉價':<10} {'平倉價':<10} {'盈虧 (U)':<10} {'狀態'}")
    print("-" * 90)

    if not entries:
        print("  目前尚無交易日誌記錄。")
    else:
        for e in entries:
            pnl_s = f"${e.pnl_usdt:+,.2f}" if e.status == "CLOSED" else "--"
            exit_s = f"${e.exit_price:,.1f}" if e.status == "CLOSED" else "持倉中"
            t_s = e.entry_time[:16] if e.entry_time else "--"
            print(f"{e.journal_id:<24} {t_s:<17} {e.market_type:<6} {e.side:<6} ${e.entry_price:<9,.1f} {exit_s:<10} {pnl_s:<10} {e.status}")

    print("=" * 90)
    print("  提示：輸入 `just journal <ID>` 或 `python apps/cli/trade_journal_viewer.py --latest` 查看完整學習覆盤。\n")


def main():
    parser = argparse.ArgumentParser(description="Trade Journal & Review Viewer")
    parser.add_argument("--list", action="store_true", help="List all trade journal entries")
    parser.add_argument("--latest", action="store_true", help="Show the latest trade entry details")
    parser.add_argument("--id", type=str, default="", help="Specific Journal ID to display")
    parser.add_argument("--market", type=str, default=None, help="Filter by market (SPOT/SWAP)")
    args = parser.parse_args()

    mgr = TradeJournalManager()

    if args.id:
        entry = mgr.get_entry(args.id)
        if entry:
            print_entry_detail(entry)
        else:
            print(f"找不到編號為 '{args.id}' 的日誌記錄。")
    elif args.latest:
        entries = mgr.get_entries(market_type=args.market)
        if entries:
            print_entry_detail(entries[0])
        else:
            print("目前尚無任何交易日誌記錄。")
    elif args.list:
        print_list_view(mgr, market_type=args.market)
    else:
        # Default behavior: if entries exist, show latest; if not, show list view
        entries = mgr.get_entries(market_type=args.market)
        if entries:
            print_entry_detail(entries[0])
        else:
            print_list_view(mgr, market_type=args.market)


if __name__ == "__main__":
    main()
