"""Plotly Financial Charts for the Quantitative Dashboard."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def create_candlestick_chart(df: pd.DataFrame, symbol: str = "BTC/USDT", max_bars: int = 150) -> go.Figure:
    """Create interactive Candlestick chart with Volume bars."""
    plot_df = df.tail(max_bars).copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
        subplot_titles=[f"{symbol} Price Action", "Volume"]
    )

    fig.add_trace(
        go.Candlestick(
            x=plot_df["timestamp"],
            open=plot_df["open"],
            high=plot_df["high"],
            low=plot_df["low"],
            close=plot_df["close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1, col=1
    )

    colors = ["#26a69a" if c >= o else "#ef5350" for c, o in zip(plot_df["close"], plot_df["open"])]
    fig.add_trace(
        go.Bar(
            x=plot_df["timestamp"],
            y=plot_df["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.6,
        ),
        row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=40, b=20),
        height=480,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig

def create_equity_curve_chart(results_df: pd.DataFrame, initial_capital: float = 10000.0) -> go.Figure:
    """Create Equity Curve comparison between Strategy and Buy & Hold."""
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=results_df["timestamp"],
            y=results_df["equity"],
            mode="lines",
            name="AI Strategy Equity",
            line=dict(color="#00e676", width=2.5),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=results_df["timestamp"],
            y=results_df["benchmark_equity"],
            mode="lines",
            name="Benchmark (Buy & Hold)",
            line=dict(color="#78909c", width=1.5, dash="dash"),
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title="Strategy Equity Growth vs Benchmark ($ USDT)",
        xaxis_title="Time",
        yaxis_title="Account Equity (USDT)",
        margin=dict(l=20, r=20, t=50, b=20),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig

def create_feature_importance_chart(df_imp: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Create horizontal bar chart of top predictive features."""
    top_df = df_imp.head(top_n).sort_values("importance", ascending=True)

    fig = go.Figure(
        go.Bar(
            x=top_df["importance"],
            y=top_df["feature"],
            orientation="h",
            marker=dict(
                color=top_df["importance"],
                colorscale="Viridis",
            ),
        )
    )

    fig.update_layout(
        template="plotly_dark",
        title=f"Top {top_n} Predictive Feature Importances (Gain)",
        xaxis_title="Importance Gain",
        yaxis_title="Feature",
        margin=dict(l=20, r=20, t=50, b=20),
        height=380,
    )
    return fig
