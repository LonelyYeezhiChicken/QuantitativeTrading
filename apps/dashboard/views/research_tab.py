"""Research Tab View: Multi-factor Research, Backtesting, Rolling Compound & Convergence Matrix."""

import json
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from packages.data import CCXTFetcher, DataManager
from packages.features import FeaturePipeline
from packages.models import (
    BaseTradingModel,
    LGBMAgent,
    DualEMACrossoverModel,
    RSIMomentumModel,
)
from packages.backtest import (
    BacktestEngine,
    RollingBacktestEvaluator,
    StrategyConvergenceAnalyzer,
)
from apps.dashboard.ui.components import (
    create_candlestick_chart,
    create_equity_curve_chart,
    create_feature_importance_chart,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def render_research_tab(dm: DataManager):
    """Render the research and backtest hub tab."""
    st.subheader("量化多因子研究與回測")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        r_sym = st.selectbox("標的選擇", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XAUT/USDT"], index=0, key="r_sym")
    with col_r2:
        r_tf = st.selectbox("K 線週期", ["15m", "1h", "4h", "1d"], index=1, key="r_tf")

    sub_tab_data, sub_tab_backtest, sub_tab_rolling, sub_tab_matrix = st.tabs([
        "行情數據下載",
        "模型回測比較",
        "年度 100U 滾倉複利",
        "五年全期策略收斂矩陣",
    ])

    with sub_tab_data:
        col_d1, col_d2 = st.columns([3, 1])
        with col_d1:
            days_to_fetch = st.slider("歷史天數", 15, 360, 90, 15, key="r_days")
        with col_d2:
            st.write("")
            st.write("")
            download_btn = st.button("下載 / 更新行情", use_container_width=True, key="btn_download_kline")

        cached_data = dm.load_raw_data(r_sym, r_tf)
        if download_btn:
            with st.spinner(f"下載 {r_sym} ({r_tf}) 數據中..."):
                fetcher = CCXTFetcher()
                try:
                    df = fetcher.fetch_ohlcv(symbol=r_sym, timeframe=r_tf, max_total_candles=days_to_fetch * 24)
                    if df.empty or len(df) < 50:
                        df = fetcher.generate_mock_ohlcv(symbol=r_sym, timeframe=r_tf, days=days_to_fetch)
                    dm.save_raw_data(df, r_sym, r_tf)
                    st.success(f"已儲存 {len(df):,} 筆 K 線數據！")
                    cached_data = df
                except Exception as e:
                    st.error(f"下載失敗: {e}")

        if cached_data is not None and not cached_data.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("K 線總數", f"{len(cached_data):,}")
            c2.metric("最新收盤價", f"${cached_data['close'].iloc[-1]:,.2f}")
            c3.metric("區間最高價", f"${cached_data['high'].max():,.2f}")
            c4.metric("區間最低價", f"${cached_data['low'].min():,.2f}")
            st.plotly_chart(create_candlestick_chart(cached_data, symbol=r_sym), use_container_width=True)

    with sub_tab_backtest:
        if cached_data is None or len(cached_data) < 50:
            st.info(f"請先在「行情數據下載」獲取 {r_sym} 數據。")
        else:
            m_choice = st.selectbox(
                "選擇交易策略模型",
                ["LightGBM 多因子 AI 模型", "雙均線趨勢追蹤 (Dual EMA 21/50)", "RSI 均值回歸 (RSI 35/65)"],
                index=0,
                key="sel_model",
            )
            if st.button("執行模型回測", use_container_width=True, key="btn_run_bt"):
                with st.spinner("計算因子特徵與回測推演中..."):
                    pipeline = FeaturePipeline(target_horizon=3)
                    feat_df, cols = pipeline.build_features(cached_data)

                    if "LightGBM" in m_choice:
                        model: BaseTradingModel = LGBMAgent(num_boost_round=60)
                    elif "雙均線" in m_choice:
                        model = DualEMACrossoverModel(fast_span=21, slow_span=50)
                    else:
                        model = RSIMomentumModel(lower_thresh=35.0, upper_thresh=65.0)

                    # Fit model on historical data
                    model.fit(feat_df, cols)
                    preds = model.predict(feat_df)

                    # Run backtest with proper fee_rate parameter
                    engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.0006, confidence_threshold=0.002)
                    results_df, perf = engine.run(feat_df, preds)

                    final_equity = results_df["equity"].iloc[-1]
                    total_ret = perf.get("Total Return (%)", 0.0)
                    sharpe = perf.get("Sharpe Ratio", 0.0)
                    max_dd = perf.get("Max Drawdown (%)", 0.0)

                    bc1, bc2, bc3, bc4 = st.columns(4)
                    bc1.metric("最終淨值", f"${final_equity:,.2f}")
                    bc2.metric("累計報酬率", f"{total_ret:+.2f}%")
                    bc3.metric("夏普比率", f"{sharpe:.2f}")
                    bc4.metric("最大回撤", f"{max_dd:.2f}%")

                    st.plotly_chart(create_equity_curve_chart(results_df), use_container_width=True)
                    if "LightGBM" in m_choice and hasattr(model, "get_feature_importance"):
                        imp_df = model.get_feature_importance(cols)
                        if not imp_df.empty:
                            st.plotly_chart(create_feature_importance_chart(imp_df), use_container_width=True)

    with sub_tab_rolling:
        st.write("#### 100 USDT 滾倉年度複利實測")
        if cached_data is not None and len(cached_data) > 100:
            roll_year = st.selectbox("評估年份", [2024, 2025, 2026], index=1, key="sel_roll_yr")
            if st.button(f"執行 {roll_year} 年度 100U 滾倉推演", use_container_width=True, key="btn_run_roll"):
                with st.spinner("年度時序滾動推進中..."):
                    evaluator = RollingBacktestEvaluator(initial_capital=100.0)
                    model = LGBMAgent(num_boost_round=40)
                    res = evaluator.evaluate_year(model, symbol=r_sym, year=roll_year)

                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric("起始本金", "$100.00 USDT")
                    rc2.metric("結算淨值", f"${res.final_equity:,.2f} USDT")
                    rc3.metric("年度總收益率", f"{res.total_return_pct:+.2f}%")

                    st.write("##### 每月資金滾動進度")
                    st.dataframe(res.monthly_breakdown, use_container_width=True)
        else:
            st.info("請先下載足夠歷史數據以進行年度滾倉複利推演。")

    with sub_tab_matrix:
        st.markdown("#### 比特幣 (BTC/USDT) 五年 (2021~2025) 策略回測矩陣與收斂報告")
        conv_json_file = ROOT_DIR / "data" / "btc_5year_strategy_convergence.json"

        col_mx1, col_mx2 = st.columns([3, 1])
        with col_mx1:
            st.caption("回測基準: 2021-01-01 至 2025-12-31 | 週期: 1h (43,786 根 K 棒) | 成本: 0.05% Taker + 0.02% 滑價")
        with col_mx2:
            recalc_matrix = st.button("重新計算五年矩陣", use_container_width=True, key="btn_recalc_matrix")

        if recalc_matrix or not conv_json_file.exists():
            with st.spinner("正在推演所有策略五年 (2021~2025) 逐年與連續複利回測..."):
                analyzer = StrategyConvergenceAnalyzer()
                summaries = analyzer.run_all()
                json_payload = []
                for s in summaries:
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
                conv_json_file.parent.mkdir(parents=True, exist_ok=True)
                with open(conv_json_file, "w", encoding="utf-8") as f:
                    json.dump(json_payload, f, indent=2, ensure_ascii=False)
                st.success("五年策略收斂矩陣推演完成並已快取！")

        if conv_json_file.exists():
            with open(conv_json_file, "r", encoding="utf-8") as f:
                matrix_data = json.load(f)

            # Top Metrics Summary
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("回測總週期", "5 個完整年度 (2021~2025)")
            m_c2.metric("主力保留策略 (KEEP)", f"{sum(1 for s in matrix_data if s['convergence_verdict'] == 'KEEP')} 組")
            m_c3.metric("建議優化策略 (OPTIMIZE)", f"{sum(1 for s in matrix_data if s['convergence_verdict'] == 'OPTIMIZE')} 組")
            m_c4.metric("淘汰除役策略 (DISCARD)", f"{sum(1 for s in matrix_data if s['convergence_verdict'] == 'DISCARD')} 組")

            # Multi-Strategy 5-Year Equity Curves Overlay Chart
            st.write("##### 五年策略累積權益曲線對比 (Log Scale)")
            fig_comp = go.Figure()
            color_palette = [
                "#58a6ff", "#3fb950", "#d29922", "#f85149", "#bc8cff", "#39c5bb", "#ff7b72", "#79c0ff"
            ]
            for idx, s in enumerate(matrix_data):
                color = color_palette[idx % len(color_palette)]
                fig_comp.add_trace(go.Scatter(
                    x=s["equity_dates"],
                    y=s["equity_values"],
                    mode="lines",
                    name=f"{s['name']} ({s['total_return_pct']:+,.0f}%)",
                    line=dict(width=2, color=color),
                ))
            fig_comp.update_layout(
                template="plotly_dark",
                height=500,
                margin=dict(l=20, r=20, t=30, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                yaxis=dict(type="log", title="權益淨值 (USDT, 對數坐標)"),
            )
            st.plotly_chart(fig_comp, use_container_width=True)

            # Strategy Detailed Evaluation Cards
            st.write("##### 策略評級與收斂裁決清單")
            for s in matrix_data:
                verdict = s["convergence_verdict"]
                if verdict == "KEEP":
                    badge_style = "background: rgba(63, 185, 80, 0.2); color: #3fb950; border: 1px solid #3fb950;"
                elif verdict == "OPTIMIZE":
                    badge_style = "background: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid #d29922;"
                else:
                    badge_style = "background: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid #f85149;"

                with st.expander(f"【{verdict}】{s['name']} — 5 年總回報: {s['total_return_pct']:+,.1f}% | MDD: {s['max_drawdown_pct']:.1f}%", expanded=(verdict == "KEEP")):
                    e_c1, e_c2, e_c3, e_c4 = st.columns(4)
                    e_c1.metric("年化複合增長 (CAGR)", f"{s['cagr_pct']:+.1f}%")
                    e_c2.metric("夏普比率 (Sharpe)", f"{s['sharpe_ratio']:.2f}")
                    e_c3.metric("獲利因子 (Profit Factor)", f"{s['profit_factor']:.2f}")
                    e_c4.metric("交易勝率 (Win Rate)", f"{s['win_rate_pct']:.1f}%")

                    st.markdown(f"""
                    <div style="background: rgba(22, 27, 34, 0.7); padding: 10px 14px; border-radius: 6px; margin: 8px 0;">
                        <b>裁決診斷</b>：{s['diagnosis_reason']}<br>
                        <b>優化建議</b>：{s['optimization_recommendation']}
                    </div>
                    """, unsafe_allow_html=True)
