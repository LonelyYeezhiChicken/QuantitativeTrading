"""Streamlit Web Dashboard for Crypto AI Quantitative Trading Platform."""

import sys
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

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
)
from packages.execution import PaperBroker
from apps.dashboard.ui.components import (
    create_candlestick_chart,
    create_equity_curve_chart,
    create_feature_importance_chart,
)

def main():
    # ----------------- Page Configuration -----------------
    st.set_page_config(
        page_title="AI 量化交易控制台 (Monorepo)",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("🤖 加密貨幣 AI 多因子量化控制台")
    st.caption("企業級模組化量化架構 | 支援任意模型插拔回測與 100U 滾倉複利分析")

    # ----------------- Shared State / Instances -----------------
    dm = DataManager()
    broker = PaperBroker()

    # ----------------- Sidebar Configuration -----------------
    st.sidebar.header("⚙️ 交易對與週期設定")
    symbol = st.sidebar.selectbox(
        "交易對 (Symbol)",
        ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
        index=0,
    )
    timeframe = st.sidebar.selectbox(
        "K 線週期 (Timeframe)",
        ["15m", "1h", "4h", "1d"],
        index=1,
    )

    st.sidebar.divider()
    st.sidebar.subheader("📌 快速狀態")
    cached_data = dm.load_raw_data(symbol, timeframe)
    if cached_data is not None and not cached_data.empty:
        st.sidebar.success(f"已緩存 {len(cached_data):,} 筆 K 線")
        st.sidebar.write(f"最新價格: **${cached_data['close'].iloc[-1]:,.2f}**")
        st.sidebar.write(f"數據時間: {cached_data['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M')}")
    else:
        st.sidebar.warning("尚未下載此幣種數據")

    # ----------------- Main Tabs -----------------
    tab_data, tab_model, tab_rolling, tab_paper = st.tabs([
        "📊 數據中心 (Data Hub)",
        "🤖 策略與模型回測 (Models & Backtest)",
        "💰 年度 100U 滾倉分析 (Rolling Compounding)",
        "💼 模擬盤即時監控 (Paper Trading)",
    ])

    # ================= TAB 1: DATA HUB =================
    with tab_data:
        st.subheader("行情數據獲取與視覺化")
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            days_to_fetch = st.slider("抓取歷史天數 (Days)", min_value=15, max_value=360, value=180, step=15)
        with col2:
            st.write("")
            st.write("")
            download_btn = st.button("🚀 一鍵下載 / 更新行情", use_container_width=True)

        if download_btn:
            with st.spinner(f"正在透過 CCXT 連線幣安下載 {symbol} ({timeframe}) 數據..."):
                fetcher = CCXTFetcher()
                try:
                    df = fetcher.fetch_ohlcv(
                        symbol=symbol,
                        timeframe=timeframe,
                        max_total_candles=days_to_fetch * 24,
                    )
                    if df.empty or len(df) < 50:
                        df = fetcher.generate_mock_ohlcv(symbol=symbol, timeframe=timeframe, days=days_to_fetch)
                        st.info("由於交易所網路限制，已為您生成高逼真度真實幾何布朗運動市場數據。")
                    dm.save_raw_data(df, symbol, timeframe)
                    st.success(f"成功下載並儲存 {len(df):,} 筆 K 線！")
                    cached_data = df
                except Exception as e:
                    st.error(f"下載失敗: {e}")

        if cached_data is not None and not cached_data.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("總 K 線數", f"{len(cached_data):,}")
            c2.metric("最新收盤價", f"${cached_data['close'].iloc[-1]:,.2f}")
            c3.metric("最高價", f"${cached_data['high'].max():,.2f}")
            c4.metric("最低價", f"${cached_data['low'].min():,.2f}")

            st.plotly_chart(create_candlestick_chart(cached_data, symbol=symbol), use_container_width=True)
            
            with st.expander("檢視最新 10 筆歷史數據明細"):
                st.dataframe(cached_data.tail(10), use_container_width=True)
        else:
            st.info("請點擊上方「一鍵下載 / 更新行情」按鈕以開始。")

    # ================= TAB 2: MODELS & BACKTEST =================
    with tab_model:
        st.subheader("多模型可插拔回測與比對")
        
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            model_choice = st.selectbox(
                "🧠 選擇交易模型 (Trading Model)",
                [
                    "LightGBM 多因子 AI 模型 (機器學習預測)",
                    "雙均線趨勢追蹤 (Dual EMA 21/50 傳統指標)",
                    "RSI 均值回歸 (RSI Momentum 35/65)",
                ],
                index=0,
            )

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            threshold = st.slider("交易信心門檻 (Confidence Threshold)", 0.001, 0.010, 0.002, 0.0005, format="%.4f")
        with col_p2:
            init_capital = st.number_input("初始回測本金 (USDT)", min_value=10.0, max_value=1000000.0, value=10000.0, step=100.0)
        with col_p3:
            fee_rate = st.selectbox("手續費率 (Taker Fee)", [0.0002, 0.0005, 0.001], index=1, format_func=lambda x: f"{x*100:.2f}%")

        train_btn = st.button("⚡ 開始模型回測", type="primary", use_container_width=True)

        if train_btn:
            if cached_data is None or len(cached_data) < 100:
                st.warning("請先在「數據中心」下載足夠的行情數據（至少 100 根 K 棒）。")
            else:
                with st.spinner(f"正在執行 {model_choice} 回測分析..."):
                    # Instantiate selected model
                    if "LightGBM" in model_choice:
                        model = LGBMAgent(num_boost_round=150)
                        train_req = True
                    elif "雙均線" in model_choice:
                        model = DualEMACrossoverModel(21, 50)
                        train_req = False
                    else:
                        model = RSIMomentumModel(35.0, 65.0)
                        train_req = False

                    evaluator = RollingBacktestEvaluator(
                        initial_capital=init_capital,
                        fee_rate=fee_rate,
                        slippage=0.0002,
                    )
                    eval_res = evaluator.evaluate(
                        model=model,
                        df=cached_data,
                        symbol=symbol,
                        threshold=threshold,
                        train_model=train_req,
                    )

                    st.session_state["eval_res"] = eval_res
                    st.success(f"{eval_res.model_name} 回測完成！")

        if "eval_res" in st.session_state:
            res = st.session_state["eval_res"]

            st.divider()
            st.write(f"### 🏆 {res.model_name} 績效報告 (已扣除真實手續費與滑價)")
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("策略總回報", f"{res.total_return_pct:+.2f}%")
            m2.metric("夏普比率 (Sharpe)", f"{res.metrics.get('Sharpe Ratio', 0.0):.2f}")
            m3.metric("最大回撤 (MDD)", f"-{res.metrics.get('Max Drawdown (%)', 0.0):.2f}%")
            m4.metric("交易勝率 (Win Rate)", f"{res.metrics.get('Win Rate (%)', 0.0):.1f}%")
            m5.metric("超額收益 (Alpha)", f"{res.alpha_pct:+.2f}%")

            st.plotly_chart(create_equity_curve_chart(res.results_df, initial_capital=init_capital), use_container_width=True)

    # ================= TAB 3: ROLLING COMPOUNDING =================
    with tab_rolling:
        st.subheader("💰 年度 100U 滾倉複利分析 (Compounding Evaluator)")
        st.write("以 100 USDT 起始本金，模擬全年全複利滾動，驗證在牛熊不同市況下的實質獲利。")

        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            rolling_year = st.selectbox("選擇回測完整年度", [2025, 2024], index=0)
        with rc2:
            rolling_capital = st.number_input("起始本金 (USDT)", min_value=10.0, max_value=50000.0, value=100.0, step=10.0)
        with rc3:
            rolling_model = st.selectbox("評估模型", ["LightGBM 多因子 AI", "雙均線趨勢追蹤 (Dual EMA)"], index=0)

        if st.button("🚀 執行年度滾倉回測", use_container_width=True):
            with st.spinner(f"正在載入 {rolling_year} 全年 K 線並推演滾倉利潤..."):
                selected_model = LGBMAgent(num_boost_round=150) if "LightGBM" in rolling_model else DualEMACrossoverModel(21, 50)
                evaluator = RollingBacktestEvaluator(initial_capital=rolling_capital)
                r_res = evaluator.evaluate_year(
                    model=selected_model,
                    symbol="BTC/USDT",
                    year=rolling_year,
                    timeframe="1h",
                    threshold=0.002,
                )
                st.session_state["rolling_res"] = r_res
                st.success("年度滾倉推演完成！")

        if "rolling_res" in st.session_state:
            r = st.session_state["rolling_res"]
            st.divider()
            
            c_a, c_b, c_c, c_d = st.columns(4)
            c_a.metric("起始本金", f"${r.initial_capital:,.2f}")
            c_b.metric("期末淨值", f"${r.final_equity:,.2f}")
            c_c.metric("淨獲利", f"${r.net_profit:+,.2f}", delta=f"{r.total_return_pct:+.2f}%")
            c_d.metric("BTC死抱 (HODL)", f"${r.benchmark_final_equity:,.2f}", delta=f"{r.benchmark_return_pct:+.2f}%")

            st.write("#### 📅 每月滾動資金成長明細表")
            st.dataframe(r.monthly_breakdown, use_container_width=True)
            st.plotly_chart(create_equity_curve_chart(r.results_df, initial_capital=r.initial_capital), use_container_width=True)

    # ================= TAB 4: PAPER TRADING =================
    with tab_paper:
        st.subheader("虛擬模擬盤帳戶即時監控 (Paper Trading)")
        
        current_price = cached_data["close"].iloc[-1] if cached_data is not None and not cached_data.empty else 30000.0
        summary = broker.summary(current_prices={symbol: current_price})

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("可用現金 (USDT)", f"${summary['cash_usdt']:,.2f}")
        b2.metric("總資產淨值 (Portfolio)", f"${summary['portfolio_value_usdt']:,.2f}")
        b3.metric("累計盈虧 (Total PnL)", f"${summary['total_pnl_usdt']:+,.2f}", delta=summary['total_pnl_pct'])
        b4.metric("已完成訂單數", f"{summary['total_trades']}")

        st.divider()
        col_act1, col_act2 = st.columns([1, 1])

        with col_act1:
            st.write("#### 🕹️ 模擬盤控制動作")
            trade_size = st.number_input("單筆委託金額 (USDT)", min_value=10.0, max_value=50000.0, value=2500.0, step=500.0)
            
            c_buy, c_sell = st.columns(2)
            with c_buy:
                if st.button("🟢 手動市價買入 (Buy)", use_container_width=True):
                    order = broker.buy(symbol, current_price, usdt_amount=trade_size)
                    if order:
                        st.success(f"買入成功！價格: ${order['price']:,.2f}")
                        st.rerun()
                    else:
                        st.error("現金不足，無法買入！")
            with c_sell:
                if st.button("🔴 手動市價全平 (Close All)", use_container_width=True):
                    order = broker.sell(symbol, current_price, pct_position=1.0)
                    if order:
                        st.success(f"平倉成功！實現盈虧: ${order['realized_pnl']:+,.2f}")
                        st.rerun()
                    else:
                        st.warning("無持倉可平！")

        with col_act2:
            st.write("#### 🔄 模擬步進推演")
            st.write("依據 AI 模型信號，自動執行未來 24 根 K 棒的模擬交易撮合。")
            if st.button("⏩ 執行 24 根 K 棒 AI 模擬推演", use_container_width=True):
                if cached_data is not None and len(cached_data) > 50:
                    with st.spinner("AI 正在模擬撮合中..."):
                        pipeline = FeaturePipeline(target_horizon=3)
                        feat_df, cols = pipeline.build_features(cached_data)
                        agent = LGBMAgent(num_boost_round=50)
                        agent.train_cv(feat_df, cols)
                        
                        test_bars = feat_df.tail(24)
                        for i in range(len(test_bars)):
                            b = test_bars.iloc[i : i + 1]
                            price = b["close"].iloc[0]
                            pred = agent.predict(b)[0]
                            has_pos = symbol in broker.positions and broker.positions[symbol]["amount"] > 0
                            if pred > 0.002 and not has_pos:
                                broker.buy(symbol, price, usdt_amount=trade_size)
                            elif pred < -0.002 and has_pos:
                                broker.sell(symbol, price, pct_position=1.0)
                        st.success("24 根 K 棒模擬推演完成！")
                        st.rerun()

        st.write("#### 📦 目前持倉明細")
        if broker.positions:
            pos_data = []
            for sym, pos in broker.positions.items():
                amt = pos["amount"]
                avg_p = pos["avg_price"]
                mkt_val = amt * current_price
                pnl = (current_price - avg_p) * amt
                pnl_pct = ((current_price / avg_p) - 1.0) * 100
                pos_data.append({
                    "幣種": sym,
                    "持倉數量": round(amt, 6),
                    "持倉均價 ($)": round(avg_p, 2),
                    "最新市價 ($)": round(current_price, 2),
                    "目前市值 ($)": round(mkt_val, 2),
                    "浮動盈虧 ($)": round(pnl, 2),
                    "浮動報酬率 (%)": f"{pnl_pct:+.2f}%",
                })
            st.dataframe(pd.DataFrame(pos_data), use_container_width=True)
        else:
            st.info("目前為空倉（100% 現金儲備）")

        st.write("#### 📜 歷史成交流水記錄")
        if broker.trade_history:
            history_df = pd.DataFrame(broker.trade_history)
            st.dataframe(history_df.tail(15), use_container_width=True)
        else:
            st.caption("尚無歷史成交記錄。")

if __name__ == "__main__":
    main()
