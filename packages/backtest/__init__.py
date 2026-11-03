"""Backtest Package: Simulator, Metrics, and Modular Rolling Evaluator."""

from packages.backtest.engine import BacktestEngine
from packages.backtest.metrics import calculate_performance_metrics
from packages.backtest.rolling_evaluator import RollingBacktestEvaluator, RollingEvaluationResult
from packages.backtest.convergence_analyzer import (
    StrategyConvergenceAnalyzer,
    StrategyEvaluationSummary,
)

__all__ = [
    "BacktestEngine",
    "calculate_performance_metrics",
    "RollingBacktestEvaluator",
    "RollingEvaluationResult",
    "StrategyConvergenceAnalyzer",
    "StrategyEvaluationSummary",
]
