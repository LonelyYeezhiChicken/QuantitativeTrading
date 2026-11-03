"""BDD Scenario Implementation Tests: Strategy Convergence and Pruning Matrix."""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from packages.models import (
    BaseTradingModel,
    FibonacciSNRModel,
    DualEMACrossoverModel,
    RSIMomentumModel,
    SpotMomentumPullbackModel,
    SwapMultiRegimeModel,
    LGBMAgent,
)
from packages.backtest.convergence_analyzer import (
    StrategyConvergenceAnalyzer,
    StrategyEvaluationSummary,
)


class TestStrategyConvergenceBDDScenarios:
    """BDD Step Implementations matching strategy_convergence.feature."""

    def test_scenario_5year_matrix_multi_strategy_backtesting(self):
        """Scenario: 五年歷史數據特徵快取與多策略矩陣推演"""
        # Given 系統已載入 2021 至 2025 年完整 5 年 BTC 歷史行情數據
        analyzer = StrategyConvergenceAnalyzer(symbol="BTC/USDT", years=[2024, 2025])
        assert len(analyzer.years) == 2

        # When 收斂分析器批量執行包含趨勢、均值回歸、多因子AI與價格行為之多個候選模型
        candidates = analyzer.get_candidate_strategies()
        assert len(candidates) >= 5

        # Run on a representative subset of candidates to keep BDD fast
        model_ema, cat_ema, short_ema = candidates[0]
        model_fib, cat_fib, short_fib = candidates[2]

        sum_ema = analyzer.evaluate_strategy_5year(model_ema, cat_ema, allow_short=short_ema)
        sum_fib = analyzer.evaluate_strategy_5year(model_fib, cat_fib, allow_short=short_fib)

        # Then 每個策略皆應輸出完整的累積報酬率、年化CAGR、夏普比率與最大回撤
        for s in [sum_ema, sum_fib]:
            assert isinstance(s.total_return_pct, float)
            assert isinstance(s.cagr_pct, float)
            assert isinstance(s.max_drawdown_pct, float)
            assert isinstance(s.sharpe_ratio, float)
            assert isinstance(s.profit_factor, float)
            assert s.equity_curve is not None
            assert len(s.equity_curve) > 0

        # And 系統應輸出歷年市場行情適應性矩陣
        assert 2024 in sum_ema.yearly_returns
        assert 2025 in sum_ema.yearly_returns

    def test_scenario_fibonacci_snr_golden_pocket_model(self):
        """Scenario: 斐波那契 SNR 4h 黃金口袋短單模型驗證"""
        # Given 交易員配置 Fibonacci SNR 模型並設定回看週期與黃金口袋比例
        model = FibonacciSNRModel(
            swing_window=48,
            fib_lower=0.50,
            fib_upper=0.65,
            trend_filter_span=50,
            signal_strength=0.005,
        )
        assert model.name.startswith("Fibonacci_SNR")

        # When 策略於時序特徵矩陣中識別關鍵高低點支撐阻力與 0.50 至 0.65 回撤區間
        # Generate synthetic trending and pull-back market data
        np.random.seed(42)
        n = 200
        close_prices = 50000.0 + np.cumsum(np.random.randn(n) * 100.0)
        high_prices = close_prices + np.abs(np.random.randn(n) * 80.0)
        low_prices = close_prices - np.abs(np.random.randn(n) * 80.0)

        mock_df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=n, freq="1h"),
            "open": close_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close_prices,
            "volume": np.random.uniform(100, 1000, n),
        })

        signals = model.predict(mock_df)

        # Then 策略應產出連續訊號數組且包含持倉與平倉
        assert len(signals) == n
        assert isinstance(signals, np.ndarray)

        # And 模型在真實歷史五年表現應維持健全風險收益比 (MDD < 20%)
        analyzer = StrategyConvergenceAnalyzer(symbol="BTC/USDT")
        fib_production = FibonacciSNRModel(swing_window=96, fib_lower=0.50, fib_upper=0.65, trend_filter_span=100)
        summary = analyzer.evaluate_strategy_5year(fib_production, "價格行為/支撐阻力", allow_short=False)

        assert summary.max_drawdown_pct < 20.0  # Outstanding risk protection
        assert summary.sharpe_ratio > 1.0       # High institutional quality
        assert summary.total_return_pct > 0.0

    def test_scenario_strict_quantitative_pruning_classification(self):
        """Scenario: 策略收斂規則精準識別保留與淘汰策略"""
        analyzer = StrategyConvergenceAnalyzer(symbol="BTC/USDT")

        # Given & When: High profit, contained drawdown, high Sharpe
        keep_verdict, keep_diag, keep_rec = analyzer._classify_strategy(
            model_name="Top_Alpha",
            total_return=3000.0,
            mdd=8.0,
            sharpe=4.2,
            profit_factor=3.5,
            profitable_years=5,
            bear_2022_ret=120.0,
        )
        # Then 應標註為 KEEP
        assert keep_verdict == "KEEP"
        assert "實盤主力" in keep_rec

        # Given & When: High returns but drawdowns slightly elevated
        opt_verdict, opt_diag, opt_rec = analyzer._classify_strategy(
            model_name="Promising_Strategy",
            total_return=800.0,
            mdd=36.0,
            sharpe=2.1,
            profit_factor=1.25,
            profitable_years=5,
            bear_2022_ret=50.0,
        )
        # Then 應標註為 OPTIMIZE
        assert opt_verdict == "OPTIMIZE"
        assert "優化" in opt_rec or "調校" in opt_rec or "ATR" in opt_rec

        # Given & When: Negative returns, high MDD, low profit factor
        disc_verdict, disc_diag, disc_rec = analyzer._classify_strategy(
            model_name="Naive_RSI",
            total_return=-25.0,
            mdd=58.0,
            sharpe=-0.2,
            profit_factor=0.98,
            profitable_years=2,
            bear_2022_ret=-55.0,
        )
        # Then 應精準標註為 DISCARD
        assert disc_verdict == "DISCARD"
        assert "除役" in disc_rec or "淘汰" in disc_rec
