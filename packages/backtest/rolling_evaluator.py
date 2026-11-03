"""Modular Rolling Backtest Evaluator: Evaluates any BaseTradingModel across any market and period."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
import numpy as np
import pandas as pd
import ccxt

from packages.data import DataManager
from packages.features import FeaturePipeline
from packages.models.base import BaseTradingModel
from packages.backtest.engine import BacktestEngine

@dataclass
class RollingEvaluationResult:
    """Standardized result object returned by RollingBacktestEvaluator."""
    model_name: str
    symbol: str
    period_description: str
    initial_capital: float
    final_equity: float
    net_profit: float
    total_return_pct: float
    benchmark_return_pct: float
    benchmark_final_equity: float
    alpha_pct: float
    metrics: Dict[str, float]
    monthly_breakdown: pd.DataFrame
    results_df: pd.DataFrame

    def print_summary(self):
        """Print clean quantitative performance report."""
        print("\n" + "=" * 70)
        print(f"  策略滾倉複利回測報告: {self.model_name}")
        print("=" * 70)
        print(f"  標的 / 區間                : {self.symbol} ({self.period_description})")
        print(f"  起始本金 (Initial Capital) : ${self.initial_capital:,.2f} USDT")
        print(f"  期末淨值 (Final Equity)    : ${self.final_equity:,.2f} USDT")
        print(f"  年度淨獲利 (Net Profit)    : ${self.net_profit:+,.2f} USDT ({self.total_return_pct:+.2f}%)")
        print(f"  -------------------------------------------------------------")
        print(f"  現貨單純死抱 (Buy & Hold)  : ${self.benchmark_final_equity:,.2f} USDT ({self.benchmark_return_pct:+.2f}%)")
        print(f"  超額收益 (Alpha vs HODL)   : {self.alpha_pct:+.2f}%")
        print("-" * 70)
        print(f"  夏普比率 (Sharpe Ratio)    : {self.metrics.get('Sharpe Ratio', 0.0):.2f}")
        print(f"  最大回撤 (Max Drawdown)    : -{self.metrics.get('Max Drawdown (%)', 0.0):.2f}%")
        print(f"  交易勝率 (Win Rate)        : {self.metrics.get('Win Rate (%)', 0.0):.2f}%")
        print(f"  盈虧比 (Profit Factor)     : {self.metrics.get('Profit Factor', 0.0):.2f}")
        print(f"  總交易次數 (Total Trades)  : {self.metrics.get('Total Trades Count', 0):,}")
        print("-" * 70)
        print("  每月資金滾動進度:")
        print(self.monthly_breakdown.to_string(index=False))
        print("=" * 70)

class RollingBacktestEvaluator:
    """Pluggable framework for running full-year compounding backtests with ANY model."""

    def __init__(
        self,
        initial_capital: float = 100.0,
        fee_rate: float = 0.0005,       # 0.05% Taker fee
        slippage: float = 0.0002,       # 0.02% Slippage
        atr_stop_multiplier: float = 2.0,
        allow_short: bool = False,
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.atr_stop_multiplier = atr_stop_multiplier
        self.allow_short = allow_short

    def fetch_or_load_year_data(self, symbol: str, year: int, timeframe: str = "1h") -> pd.DataFrame:
        """Fetch and cache clean 1h OHLCV data for an entire calendar year."""
        dm = DataManager()
        clean_symbol = symbol.replace("/", "_")
        cache_file = dm.raw_dir / f"{clean_symbol}_{year}_{timeframe}.parquet"

        if cache_file.exists():
            df = pd.read_parquet(cache_file)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df.sort_values("timestamp").reset_index(drop=True)

        exchange = ccxt.binance({"enableRateLimit": True})
        start_dt = datetime(year, 1, 1, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime(year, 12, 31, 23, 59, tzinfo=timezone.utc)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        current_ms = start_ms
        all_candles = []

        while current_ms < end_ms:
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_ms, limit=1000)
            except Exception as e:
                print(f"[Warning] Error fetching {symbol} at {current_ms}: {e}")
                break

            if not candles:
                break

            for c in candles:
                if c[0] <= end_ms:
                    all_candles.append(c)

            last_ts = candles[-1][0]
            if last_ts <= current_ms or len(candles) < 1000 or last_ts >= end_ms:
                break
            current_ms = last_ts + 1

        df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        df.to_parquet(cache_file, engine="pyarrow", index=False)
        return df

    def evaluate(
        self,
        model: BaseTradingModel,
        df: pd.DataFrame,
        symbol: str = "BTC/USDT",
        period_description: str = "Custom Period",
        threshold: float = 0.002,
        train_model: bool = True,
    ) -> RollingEvaluationResult:
        """Evaluate any model implementing BaseTradingModel on OHLCV data."""
        # 1. Feature Engineering
        pipeline = FeaturePipeline(target_horizon=3, label_threshold=0.005)
        features_df, feature_cols = pipeline.build_features(df)

        # 2. Train / Fit Model if required
        if train_model:
            model.fit(features_df, feature_cols=feature_cols, target_col="target_forward_return")

        # 3. Model Inference (Predictions / Signals)
        predicted_signals = model.predict(features_df)

        # 4. Compounding Backtest Simulation
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            slippage=self.slippage,
            confidence_threshold=threshold,
            allow_short=self.allow_short,
            atr_stop_multiplier=self.atr_stop_multiplier,
        )
        results_df, perf = engine.run(features_df, predicted_signals)

        # 5. Metrics & Monthly Breakdown
        final_equity = results_df["equity"].iloc[-1]
        net_profit = final_equity - self.initial_capital
        total_ret_pct = perf.get("Total Return (%)", 0.0)

        start_price = df["close"].iloc[0]
        end_price = df["close"].iloc[-1]
        bench_ret_pct = ((end_price / start_price) - 1.0) * 100.0
        bench_final_equity = self.initial_capital * (1.0 + (bench_ret_pct / 100.0))
        alpha_pct = total_ret_pct - bench_ret_pct

        results_df["month"] = results_df["timestamp"].dt.tz_localize(None).dt.to_period("M")
        monthly_data = []
        prev_eq = self.initial_capital
        for m, group in results_df.groupby("month"):
            m_end_eq = group["equity"].iloc[-1]
            m_ret = ((m_end_eq / prev_eq) - 1.0) * 100.0
            m_pnl = m_end_eq - prev_eq
            monthly_data.append({
                "月份 (Month)": str(m),
                "月末淨值 ($)": round(m_end_eq, 2),
                "當月盈虧 ($)": round(m_pnl, 2),
                "當月報酬 (%)": f"{m_ret:+.2f}%",
            })
            prev_eq = m_end_eq

        monthly_df = pd.DataFrame(monthly_data)

        return RollingEvaluationResult(
            model_name=model.name,
            symbol=symbol,
            period_description=period_description,
            initial_capital=self.initial_capital,
            final_equity=round(final_equity, 2),
            net_profit=round(net_profit, 2),
            total_return_pct=round(total_ret_pct, 2),
            benchmark_return_pct=round(bench_ret_pct, 2),
            benchmark_final_equity=round(bench_final_equity, 2),
            alpha_pct=round(alpha_pct, 2),
            metrics=perf,
            monthly_breakdown=monthly_df,
            results_df=results_df,
        )

    def evaluate_year(
        self,
        model: BaseTradingModel,
        symbol: str = "BTC/USDT",
        year: int = 2025,
        timeframe: str = "1h",
        threshold: float = 0.002,
        train_model: bool = True,
    ) -> RollingEvaluationResult:
        """Convenience method to evaluate a full calendar year."""
        df = self.fetch_or_load_year_data(symbol=symbol, year=year, timeframe=timeframe)
        return self.evaluate(
            model=model,
            df=df,
            symbol=symbol,
            period_description=f"{year} 全年 ({timeframe})",
            threshold=threshold,
            train_model=train_model,
        )
