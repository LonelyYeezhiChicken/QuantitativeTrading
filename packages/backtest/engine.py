"""Backtesting Engine: Vectorized & Event-Aware Simulator with Fees & Slippage."""

from typing import Dict, Tuple
import numpy as np
import pandas as pd
from packages.backtest.metrics import calculate_performance_metrics

class BacktestEngine:
    """Simulates trading strategy performance accounting for realistic friction costs."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.0005,
        slippage: float = 0.0002,
        confidence_threshold: float = 0.003,
        allow_short: bool = False,
        atr_stop_multiplier: float = 2.0,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.confidence_threshold = confidence_threshold
        self.allow_short = allow_short
        self.atr_stop_multiplier = atr_stop_multiplier

    def run(
        self,
        df: pd.DataFrame,
        predicted_returns: np.ndarray,
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """Run backtest simulation."""
        data = df.copy().reset_index(drop=True)
        data["pred_ret"] = predicted_returns
        
        n = len(data)
        close_prices = data["close"].values
        pred_rets = data["pred_ret"].values
        natr = data["natr_14"].values if "natr_14" in data.columns else np.full(n, 0.015)

        raw_signals = np.zeros(n)
        for i in range(n):
            if pred_rets[i] > self.confidence_threshold:
                raw_signals[i] = 1.0
            elif self.allow_short and pred_rets[i] < -self.confidence_threshold:
                raw_signals[i] = -1.0
            else:
                raw_signals[i] = 0.0

        positions = np.zeros(n)
        equity = np.zeros(n)
        strategy_returns = np.zeros(n)

        current_pos = 0.0
        current_equity = self.initial_capital
        entry_price = 0.0
        stop_price = 0.0
        stopped_out_dir = 0.0

        # Timeline per bar t (bar t ends at close[t]):
        #   1. At close[t-1] the position for interval (t-1, t] is set from signal[t-1].
        #      Entry price / initial stop use close[t-1] and natr[t-1] only.
        #   2. That position earns the asset return close[t-1] -> close[t].
        #   3. At close[t] the stop is checked and the position is exited at close[t].
        # The old loop checked the stop BEFORE booking step 2, so every stop-out erased the
        # very loss that triggered it (the exit decision used close[t] to avoid close[t]'s move).
        for t in range(n):
            if t > 0:
                raw_target = raw_signals[t - 1]

                # If stopped out in this direction, require signal to reset to 0 or reverse before re-entering
                if stopped_out_dir != 0.0:
                    if raw_target == 0.0 or (np.sign(raw_target) != np.sign(stopped_out_dir)):
                        stopped_out_dir = 0.0

                target_pos = 0.0 if stopped_out_dir != 0.0 else raw_target

                turnover = abs(target_pos - current_pos)
                if turnover > 0:
                    cost = current_equity * turnover * (self.fee_rate + self.slippage)
                    current_equity -= cost
                    prev_pos = current_pos
                    current_pos = target_pos
                    if current_pos != 0.0 and np.sign(current_pos) != np.sign(prev_pos):
                        entry_price = close_prices[t - 1]
                        if current_pos > 0:
                            stop_price = entry_price * (1.0 - (natr[t - 1] * self.atr_stop_multiplier))
                        else:
                            stop_price = entry_price * (1.0 + (natr[t - 1] * self.atr_stop_multiplier))

            # 2. Book the return of the position held through bar t
            held_pos = current_pos
            asset_ret = (close_prices[t] / close_prices[t - 1]) - 1.0 if t > 0 else 0.0
            period_ret = held_pos * asset_ret
            current_equity *= (1.0 + period_ret)

            # 3. Stop check at close[t] (after the bar's P&L is booked)
            current_price = close_prices[t]
            if current_pos > 0 and current_price < stop_price:
                current_equity -= current_equity * (self.fee_rate + self.slippage)
                stopped_out_dir = 1.0
                current_pos = 0.0
                entry_price = 0.0
            elif current_pos < 0 and current_price > stop_price:
                current_equity -= current_equity * (self.fee_rate + self.slippage)
                stopped_out_dir = -1.0
                current_pos = 0.0
                entry_price = 0.0

            # Dynamic Trailing Stop profit lock (uses information up to close[t] for bar t+1)
            if current_pos > 0 and current_price > entry_price:
                new_stop = current_price * (1.0 - (natr[t] * self.atr_stop_multiplier))
                if new_stop > stop_price:
                    stop_price = new_stop
            elif current_pos < 0 and current_price < entry_price:
                new_stop = current_price * (1.0 + (natr[t] * self.atr_stop_multiplier))
                if new_stop < stop_price:
                    stop_price = new_stop

            positions[t] = held_pos
            equity[t] = current_equity
            strategy_returns[t] = period_ret

        data["signal"] = raw_signals
        data["position"] = positions
        data["equity"] = equity
        data["strategy_return"] = strategy_returns
        data["benchmark_equity"] = self.initial_capital * (data["close"] / data["close"].iloc[0])

        metrics = calculate_performance_metrics(
            equity_curve=data["equity"],
            strategy_returns=data["strategy_return"],
        )

        return data, metrics
