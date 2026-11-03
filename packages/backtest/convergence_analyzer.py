"""Strategy Convergence Analyzer: 5-Year (2021-2025) BTC Multi-Strategy Evaluation & Pruning Matrix.

Evaluates strategies across 5 years of historical data covering all market regimes,
computes risk/return profiles, and categorizes models into:
- [KEEP] (Core production candidates)
- [OPTIMIZE] (High potential, requires refinement)
- [DISCARD] (Inferior expectancy, severe drawdown, to be retired)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from packages.data import DataManager
from packages.features import FeaturePipeline
from packages.models.base import BaseTradingModel
from packages.models.rule_based import DualEMACrossoverModel, RSIMomentumModel
from packages.models.lgbm_agent import LGBMAgent
from packages.models.advanced_strategies import (
    FibonacciSNRModel,
    SpotMomentumPullbackModel,
    SwapMultiRegimeModel,
    RSIBottomHunterModel,
    BollingerBreakoutModel,
)
from packages.backtest.engine import BacktestEngine
from packages.backtest.rolling_evaluator import RollingBacktestEvaluator


@dataclass
class StrategyEvaluationSummary:
    """Consolidated 5-year multi-regime evaluation result for a single strategy."""
    name: str
    category: str
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    win_rate_pct: float
    alpha_vs_hodl_pct: float
    bear_2022_return_pct: float
    profitable_years_count: int
    yearly_returns: Dict[int, float]
    yearly_drawdowns: Dict[int, float]
    convergence_verdict: str  # 'KEEP', 'OPTIMIZE', 'DISCARD'
    diagnosis_reason: str
    optimization_recommendation: str
    equity_curve: pd.DataFrame


class StrategyConvergenceAnalyzer:
    """Orchestrates comprehensive 5-year backtesting and pruning classification."""

    def __init__(
        self,
        symbol: str = "BTC/USDT",
        years: Optional[List[int]] = None,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.0005,
        slippage: float = 0.0002,
    ):
        self.symbol = symbol
        self.years = years or [2021, 2022, 2023, 2024, 2025]
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.evaluator = RollingBacktestEvaluator(
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            slippage=slippage,
        )

    def load_full_5year_dataset(self) -> pd.DataFrame:
        """Load and concatenate clean 5-year OHLCV data."""
        dfs = []
        for yr in self.years:
            df_yr = self.evaluator.fetch_or_load_year_data(self.symbol, yr)
            dfs.append(df_yr)
        full_df = pd.concat(dfs, ignore_index=True)
        full_df = full_df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        return full_df

    def get_candidate_strategies(self) -> List[Tuple[BaseTradingModel, str, bool]]:
        """Return standardized candidate strategy instances with (model, category, allow_short)."""
        return [
            # 1. Benchmark
            (DualEMACrossoverModel(fast_span=21, slow_span=50), "趨勢動量", False),
            # 2. RSI Classic
            (RSIMomentumModel(lower_thresh=35.0, upper_thresh=65.0), "均值回歸", False),
            # 3. Fibonacci + SNR Golden Pocket (User Requested)
            (FibonacciSNRModel(swing_window=96, fib_lower=0.50, fib_upper=0.65, trend_filter_span=100), "價格行為/支撐阻力", False),
            # 4. Spot Daemon Pullback
            (SpotMomentumPullbackModel(ema_span=21), "現貨守護複合", False),
            # 5. Swap Daemon Dual-Direction
            (SwapMultiRegimeModel(ema_span=21), "合約多空雙向", True),
            # 6. RSI Confirmed Bottom Hunter
            (RSIBottomHunterModel(oversold_threshold=30.0, exit_rsi=55.0), "深度抄底反轉", False),
            # 7. Bollinger Breakout
            (BollingerBreakoutModel(bb_period=20, bb_std=2.0), "波動通道突破", False),
            # 8. LightGBM AI
            (LGBMAgent(num_boost_round=60), "機器學習多因子", False),
        ]

    def evaluate_strategy_5year(
        self,
        model: BaseTradingModel,
        category: str,
        allow_short: bool = False,
    ) -> StrategyEvaluationSummary:
        """Run yearly and 5-year continuous backtests for a specific model."""
        yearly_ret = {}
        yearly_dd = {}

        # 1. Yearly Breakdown
        for yr in self.years:
            df_yr = self.evaluator.fetch_or_load_year_data(self.symbol, yr)
            res = self.evaluator.evaluate(
                model=model,
                df=df_yr,
                symbol=self.symbol,
                period_description=str(yr),
                train_model=(model.name == "LightGBM_MultiFactor"),
            )
            yearly_ret[yr] = res.total_return_pct
            yearly_dd[yr] = res.metrics.get("Max Drawdown (%)", 0.0)

        # 2. Full 5-Year Cumulative Compounding Backtest
        full_df = self.load_full_5year_dataset()
        res_full = self.evaluator.evaluate(
            model=model,
            df=full_df,
            symbol=self.symbol,
            period_description="5Year_Full",
            train_model=(model.name == "LightGBM_MultiFactor"),
        )

        metrics = res_full.metrics
        tot_ret = res_full.total_return_pct
        mdd = metrics.get("Max Drawdown (%)", 0.0)
        sharpe = metrics.get("Sharpe Ratio", 0.0)
        pf = metrics.get("Profit Factor", 0.0)
        win_rate = metrics.get("Win Rate (%)", 0.0)
        alpha = res_full.alpha_pct

        # 5-Year CAGR calculation
        cagr = (((1.0 + (tot_ret / 100.0)) ** (1.0 / len(self.years))) - 1.0) * 100.0 if tot_ret > -100 else -100.0

        bear_2022_ret = yearly_ret.get(2022, 0.0)
        profitable_years = sum(1 for r in yearly_ret.values() if r > 0)

        # 3. Determine Convergence Verdict based on Quantitative Rubric
        verdict, diagnosis, recommendation = self._classify_strategy(
            model_name=model.name,
            total_return=tot_ret,
            mdd=mdd,
            sharpe=sharpe,
            profit_factor=pf,
            profitable_years=profitable_years,
            bear_2022_ret=bear_2022_ret,
        )

        return StrategyEvaluationSummary(
            name=model.name,
            category=category,
            total_return_pct=round(tot_ret, 2),
            cagr_pct=round(cagr, 2),
            max_drawdown_pct=round(mdd, 2),
            sharpe_ratio=round(sharpe, 2),
            profit_factor=round(pf, 2),
            win_rate_pct=round(win_rate, 2),
            alpha_vs_hodl_pct=round(alpha, 2),
            bear_2022_return_pct=round(bear_2022_ret, 2),
            profitable_years_count=profitable_years,
            yearly_returns=yearly_ret,
            yearly_drawdowns=yearly_dd,
            convergence_verdict=verdict,
            diagnosis_reason=diagnosis,
            optimization_recommendation=recommendation,
            equity_curve=res_full.results_df[["timestamp", "close", "equity"]],
        )

    def _classify_strategy(
        self,
        model_name: str,
        total_return: float,
        mdd: float,
        sharpe: float,
        profit_factor: float,
        profitable_years: int,
        bear_2022_ret: float,
    ) -> Tuple[str, str, str]:
        """Apply strict multi-dimensional quantitative rules to classify strategy."""
        # Condition A: Discard (Severe Drawdown or Negative Expectancy)
        if mdd > 55.0 or total_return < 0.0 or profit_factor < 1.05 or profitable_years <= 2:
            verdict = "DISCARD"
            diagnosis = f"五年整體獲利期望值薄弱 (PF={profit_factor:.2f}) 或回撤過深 (MDD={mdd:.1f}%)，無法穿越 2022 熊市風險。"
            recommendation = "建議自主力交易清單除役，避免資金長期遭受磨耗與手續費摩擦。"
            return verdict, diagnosis, recommendation

        # Condition B: Keep (Solid Alpha, Contained Drawdown, Multi-Regime Survival)
        if total_return > 150.0 and mdd <= 35.0 and sharpe >= 0.85 and profitable_years >= 4 and bear_2022_ret > -20.0:
            verdict = "KEEP"
            diagnosis = f"五年複利收益優異 (+{total_return:.1f}%)，風控防禦卓越 (MDD={mdd:.1f}%)，歷經牛熊皆穩定獲利。"
            recommendation = "推薦列入實盤主力核心策略，配置高比例資產運作。"
            return verdict, diagnosis, recommendation

        # Condition C: Optimize (Clear Edge, but Needs Refinement)
        verdict = "OPTIMIZE"
        if bear_2022_ret <= -25.0:
            diagnosis = f"牛市具備強勁爆發力，但在 2022 熊市回檔較深 ({bear_2022_ret:.1f}%)，單邊下行時止損不夠敏銳。"
            recommendation = "引入動態 ATR 追蹤止損或長期 200 EMA 趨勢硬濾網，熊市時強制空倉或降低曝險。"
        elif profit_factor < 1.3:
            diagnosis = f"勝率穩定但盈虧比偏低 (PF={profit_factor:.2f})，震盪市來回雙巴損耗手續費。"
            recommendation = "放寬停利空間並增設波動度閥值（NATR 濾網），濾除低動量微幅震盪區間。"
        else:
            diagnosis = f"具備長期正向期望值 (5年收益 +{total_return:.1f}%, 勝率 {profitable_years}/5 年)，但風險報酬比尚有優化空間。"
            recommendation = "建議微調時間週期（如結合 4h 結構）與動態停利比例，提升夏普比率。"

        return verdict, diagnosis, recommendation

    def run_all(self) -> List[StrategyEvaluationSummary]:
        """Execute matrix backtest across all candidate strategies."""
        candidates = self.get_candidate_strategies()
        summaries = []
        for model, cat, allow_short in candidates:
            summary = self.evaluate_strategy_5year(model, cat, allow_short=allow_short)
            summaries.append(summary)
        return summaries

    def build_summary_dataframe(self, summaries: List[StrategyEvaluationSummary]) -> pd.DataFrame:
        """Convert list of summaries into a clean comparative table."""
        rows = []
        for s in summaries:
            row = {
                "策略名稱": s.name,
                "策略類別": s.category,
                "五年總報酬 (%)": s.total_return_pct,
                "年化 CAGR (%)": s.cagr_pct,
                "最大回撤 MDD (%)": s.max_drawdown_pct,
                "夏普比率": s.sharpe_ratio,
                "獲利因子": s.profit_factor,
                "勝率 (%)": s.win_rate_pct,
                "2022熊市表現 (%)": s.bear_2022_return_pct,
                "盈利年份數": f"{s.profitable_years_count} / 5",
                "收斂評定": s.convergence_verdict,
            }
            # Append individual year returns
            for yr, r in s.yearly_returns.items():
                row[f"{yr} 年 (%)"] = r
            rows.append(row)

        df = pd.DataFrame(rows)
        return df.sort_values(by="五年總報酬 (%)", ascending=False).reset_index(drop=True)
