"""Performance Metrics for Strategy Evaluation."""

from typing import Dict
import numpy as np
import pandas as pd

def calculate_performance_metrics(
    equity_curve: pd.Series,
    strategy_returns: pd.Series,
    periods_per_year: int = 24 * 365,
    risk_free_rate: float = 0.0,
) -> Dict[str, float]:
    """Calculate key quantitative performance metrics."""
    if len(equity_curve) < 2:
        return {}

    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1.0
    n_periods = len(equity_curve)
    years = n_periods / periods_per_year
    annualized_return = ((1.0 + total_return) ** (1.0 / max(years, 1e-4))) - 1.0

    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = float(drawdown.min())

    mean_return = strategy_returns.mean()
    std_return = strategy_returns.std()
    annualized_vol = std_return * np.sqrt(periods_per_year)
    
    excess_mean = mean_return - (risk_free_rate / periods_per_year)
    sharpe_ratio = (excess_mean / (std_return + 1e-12)) * np.sqrt(periods_per_year)

    downside_returns = strategy_returns[strategy_returns < 0]
    downside_std = downside_returns.std() if len(downside_returns) > 0 else 1e-12
    sortino_ratio = (excess_mean / (downside_std + 1e-12)) * np.sqrt(periods_per_year)

    positive_trades = strategy_returns[strategy_returns > 0]
    negative_trades = strategy_returns[strategy_returns < 0]
    win_rate = len(positive_trades) / max(len(strategy_returns[strategy_returns != 0]), 1)
    profit_factor = positive_trades.sum() / max(abs(negative_trades.sum()), 1e-12)

    return {
        "Total Return (%)": round(total_return * 100, 2),
        "Annualized Return (%)": round(annualized_return * 100, 2),
        "Annualized Volatility (%)": round(annualized_vol * 100, 2),
        "Sharpe Ratio": round(float(sharpe_ratio), 2),
        "Sortino Ratio": round(float(sortino_ratio), 2),
        "Max Drawdown (%)": round(abs(max_drawdown) * 100, 2),
        "Win Rate (%)": round(win_rate * 100, 2),
        "Profit Factor": round(float(profit_factor), 2),
        "Total Trades Count": int(len(strategy_returns[strategy_returns != 0])),
    }
