"""CLI Tool: 5-Year (2021-2025) BTC Multi-Strategy Backtest Matrix & Convergence Report.

Usage:
    python apps/cli/run_5year_backtest_matrix.py
    python apps/cli/run_5year_backtest_matrix.py --symbol BTC/USDT --capital 10000
"""

import argparse
import json
import sys
import time
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.backtest.convergence_analyzer import StrategyConvergenceAnalyzer, StrategyEvaluationSummary


def generate_markdown_report(summaries: list[StrategyEvaluationSummary], df_summary: pd.DataFrame, output_path: Path):
    """Generate professional, comprehensive quantitative convergence report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    keep_list = [s for s in summaries if s.convergence_verdict == "KEEP"]
    opt_list = [s for s in summaries if s.convergence_verdict == "OPTIMIZE"]
    discard_list = [s for s in summaries if s.convergence_verdict == "DISCARD"]

    md = []
    md.append("# 比特幣 (BTC/USDT) 五年 (2021~2025) 策略回測矩陣與收斂淘汰權威報告\n")
    md.append("> **回測基準區間**：2021-01-01 至 2025-12-31 (共計 5 年，43,786 根 1h K 線)")
    md.append("> **交易成本設定**：手續費 0.05% (Taker) + 滑價 0.02% | 初始本金: $10,000.00 USDT\n")
    md.append("--- \n")

    md.append("## 1. 五年全週期績效排行榜 (5-Year Performance Ranking Matrix)\n")
    md.append("| 排名 | 策略名稱 | 類別 | 五年總報酬 (%) | 年化 CAGR (%) | 最大回撤 MDD (%) | 夏普比率 | 獲利因子 | 2022熊市 (%) | 評定結論 |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for idx, row in df_summary.iterrows():
        rank = idx + 1
        verdict = row["收斂評定"]
        tag = f"**[{verdict}]**"
        md.append(
            f"| {rank} | `{row['策略名稱']}` | {row['策略類別']} | **{row['五年總報酬 (%)']:+,.1f}%** | "
            f"{row['年化 CAGR (%)']:+.1f}% | -{row['最大回撤 MDD (%)']:.1f}% | {row['夏普比率']:.2f} | "
            f"{row['獲利因子']:.2f} | {row['2022熊市表現 (%)']:+.1f}% | {tag} |"
        )
    md.append("\n---\n")

    md.append("## 2. 逐年市場行情適應性矩陣 (Year-by-Year Multi-Regime Breakdown)\n")
    md.append("| 策略名稱 | 2021 (狂暴牛市) | 2022 (極限大熊) | 2023 (震盪復甦) | 2024 (ETF牛市) | 2025 (後減半震盪) | 盈利年數 |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for s in summaries:
        y21 = f"{s.yearly_returns.get(2021, 0.0):+,.1f}%"
        y22 = f"{s.yearly_returns.get(2022, 0.0):+,.1f}%"
        y23 = f"{s.yearly_returns.get(2023, 0.0):+,.1f}%"
        y24 = f"{s.yearly_returns.get(2024, 0.0):+,.1f}%"
        y25 = f"{s.yearly_returns.get(2025, 0.0):+,.1f}%"
        md.append(f"| `{s.name}` | {y21} | {y22} | {y23} | {y24} | {y25} | **{s.profitable_years_count} / 5** |")
    md.append("\n---\n")

    md.append("## 3. 策略收斂淘汰決策剖析 (Convergence & Pruning Breakdown)\n")

    md.append("### 3.1 保留並納入主力實盤 (KEEP - Core Production)\n")
    if keep_list:
        for s in keep_list:
            md.append(f"#### 策略：`{s.name}` ({s.category})")
            md.append(f"- **診斷依據**：{s.diagnosis_reason}")
            md.append(f"- **執行建議**：{s.optimization_recommendation}")
            md.append(f"- **核心數據**：5年報酬 `{s.total_return_pct:+,.1f}%` | MDD `-{s.max_drawdown_pct:.1f}%` | 夏普 `{s.sharpe_ratio:.2f}` | 2022熊市 `{s.bear_2022_return_pct:+.1f}%`\n")
    else:
        md.append("（無完全符合 KEEP 嚴苛標準之策略，需進行參數優化）\n")

    md.append("### 3.2 具備優勢但需優化調校 (OPTIMIZE - High Potential Refinement)\n")
    if opt_list:
        for s in opt_list:
            md.append(f"#### 策略：`{s.name}` ({s.category})")
            md.append(f"- **診斷依據**：{s.diagnosis_reason}")
            md.append(f"- **優化方案**：{s.optimization_recommendation}")
            md.append(f"- **核心數據**：5年報酬 `{s.total_return_pct:+,.1f}%` | MDD `-{s.max_drawdown_pct:.1f}%` | 夏普 `{s.sharpe_ratio:.2f}` | 2022熊市 `{s.bear_2022_return_pct:+.1f}%`\n")
    else:
        md.append("（無）\n")

    md.append("### 3.3 淘汰捨棄或除役 (DISCARD - Inadequate Risk/Reward)\n")
    if discard_list:
        for s in discard_list:
            md.append(f"#### 策略：`{s.name}` ({s.category})")
            md.append(f"- **淘汰原因**：{s.diagnosis_reason}")
            md.append(f"- **除役說明**：{s.optimization_recommendation}")
            md.append(f"- **核心數據**：5年報酬 `{s.total_return_pct:+,.1f}%` | MDD `-{s.max_drawdown_pct:.1f}%` | 夏普 `{s.sharpe_ratio:.2f}` | 2022熊市 `{s.bear_2022_return_pct:+.1f}%`\n")
    else:
        md.append("（無淘汰策略）\n")

    report_text = "\n".join(md)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n[報告已存檔] Markdown 報告已生成至：{output_path}")


def main():
    parser = argparse.ArgumentParser(description="5-Year BTC Multi-Strategy Backtest Matrix & Convergence Runner")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading Symbol (default: BTC/USDT)")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial Capital (default: 10000 USDT)")
    parser.add_argument("--report", type=str, default="reports/btc_5year_convergence_report.md", help="Markdown Report Output Path")
    args = parser.parse_args()

    print("=" * 80)
    print("  比特幣 (BTC/USDT) 五年 (2021~2025) 策略回測矩陣與收斂分析引擎")
    print(f"  回測標的: {args.symbol} | 初始本金: ${args.capital:,.2f} USDT")
    print("=" * 80)

    t0 = time.time()
    analyzer = StrategyConvergenceAnalyzer(
        symbol=args.symbol,
        initial_capital=args.capital,
    )

    print("\n[1/3] 正在並行推演所有候選策略 (2021 ~ 2025 各年度與五年連續複利)...")
    summaries = analyzer.run_all()

    print(f"[2/3] 完成回測！耗時: {time.time() - t0:.2f} 秒。正在建構收斂矩陣總表...")
    df_summary = analyzer.build_summary_dataframe(summaries)

    print("\n" + "=" * 80)
    print("  五年策略回測排行榜與收斂結論 (5-Year Matrix Ranking)")
    print("=" * 80)
    cols_to_print = ["策略名稱", "策略類別", "五年總報酬 (%)", "最大回撤 MDD (%)", "夏普比率", "獲利因子", "2022熊市表現 (%)", "收斂評定"]
    print(df_summary[cols_to_print].to_string(index=False))
    print("=" * 80)

    # Save JSON summary for Dashboard instant consumption
    json_path = ROOT_DIR / "data" / "btc_5year_strategy_convergence.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_payload = []
    for s in summaries:
        # Downsample equity curve to daily timestamps for fast web rendering
        eq_curve = s.equity_curve.copy()
        eq_curve["date"] = pd.to_datetime(eq_curve["timestamp"]).dt.strftime("%Y-%m-%d")
        daily_eq = eq_curve.groupby("date").last().reset_index()

        json_payload.append({
            "name": s.name,
            "category": s.category,
            "total_return_pct": s.total_return_pct,
            "cagr_pct": s.cagr_pct,
            "max_drawdown_pct": s.max_drawdown_pct,
            "sharpe_ratio": s.sharpe_ratio,
            "profit_factor": s.profit_factor,
            "win_rate_pct": s.win_rate_pct,
            "alpha_vs_hodl_pct": s.alpha_vs_hodl_pct,
            "bear_2022_return_pct": s.bear_2022_return_pct,
            "profitable_years_count": s.profitable_years_count,
            "yearly_returns": {str(k): v for k, v in s.yearly_returns.items()},
            "yearly_drawdowns": {str(k): v for k, v in s.yearly_drawdowns.items()},
            "convergence_verdict": s.convergence_verdict,
            "diagnosis_reason": s.diagnosis_reason,
            "optimization_recommendation": s.optimization_recommendation,
            "equity_dates": daily_eq["date"].tolist(),
            "equity_values": daily_eq["equity"].tolist(),
        })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)
    print(f"[數據已快取] 控制台 JSON 數據已存檔至：{json_path}")

    # Generate Markdown Report
    report_file = ROOT_DIR / args.report
    generate_markdown_report(summaries, df_summary, report_file)


if __name__ == "__main__":
    main()
