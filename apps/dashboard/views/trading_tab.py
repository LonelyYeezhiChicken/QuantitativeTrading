"""Trading Tab View: Live & Simulated Manual Order Placement with Position Monitor."""

import streamlit as st
import pandas as pd
from packages.execution import BingXGateway, PaperBroker


def render_trading_tab(gw: BingXGateway, broker: PaperBroker, dm, btc_p: float):
    """Render the manual trading and paper execution tab."""
    st.subheader("實盤與模擬下單操作")
    col_act1, col_act2 = st.columns(2)

    with col_act1:
        st.write("#### 手動下單面板")
        exec_channel = st.radio(
            "執行通道",
            ["本地模擬經紀商 (Paper Broker)", "BingX OpenAPI (即時網關)"],
            index=0,
            horizontal=True,
            key="exec_channel",
        )

        col_ts1, col_ts2 = st.columns(2)
        with col_ts1:
            trade_sym = st.selectbox("標的選擇", ["BTC/USDT", "ETH/USDT", "SOL/USDT"], index=0, key="paper_sym")
        with col_ts2:
            trade_mkt = st.selectbox("市場類別", ["SPOT", "SWAP"], index=0, key="order_mkt_type")

        trade_size = st.number_input("下單金額 (USDT)", min_value=10.0, max_value=5000.0, value=50.0, step=10.0)
        cur_p = gw.fetch_ticker(trade_sym, market_type=trade_mkt).get("price", btc_p)
        st.markdown(f"當前市價: **${cur_p:,.2f}** | 計算數量: **{(trade_size / max(cur_p, 1e-4)):.6f}**")

        btn_b, btn_s = st.columns(2)
        with btn_b:
            if st.button("市價買入 / 開多 (BUY)", use_container_width=True, key="btn_manual_buy"):
                qty = trade_size / max(cur_p, 1e-4)
                if "BingX" in exec_channel:
                    # BingX OpenAPI order
                    res = gw.create_order(
                        symbol=trade_sym,
                        side="BUY",
                        order_type="MARKET",
                        size=qty,
                        market_type=trade_mkt,
                        position_side="LONG" if trade_mkt == "SWAP" else None,
                    )
                    if res.get("result"):
                        st.success(f"BingX OpenAPI 買單已撮合成交！訂單編號: {res.get('data', {}).get('orderId', 'OK')}")
                        st.rerun()
                    else:
                        st.error(f"下單失敗: {res.get('msg', '未知錯誤')}")
                else:
                    # Local Paper Broker order
                    res = broker.buy(trade_sym, cur_p, usdt_amount=trade_size)
                    if res is not None:
                        st.success(f"模擬買單已成交！數量: {res['quantity']:.6f} {trade_sym} | 均價: ${res['price']:,.2f}")
                        st.rerun()
                    else:
                        st.error(f"下單失敗：可用現金不足 (${broker.cash:,.2f} USDT < ${trade_size:,.2f} USDT)")

        with btn_s:
            if st.button("市價平倉 / 賣出 (SELL)", use_container_width=True, key="btn_manual_sell"):
                if "BingX" in exec_channel:
                    # BingX OpenAPI sell / close
                    pos_list = gw.get_positions(trade_sym) if trade_mkt == "SWAP" else []
                    pos_qty = float(pos_list[0].get("positionAmt", 0.0)) if pos_list else (trade_size / max(cur_p, 1e-4))
                    res = gw.create_order(
                        symbol=trade_sym,
                        side="SELL",
                        order_type="MARKET",
                        size=abs(pos_qty),
                        market_type=trade_mkt,
                        position_side="LONG" if trade_mkt == "SWAP" else None,
                    )
                    if res.get("result"):
                        st.success(f"BingX OpenAPI 賣單/平倉已成交！")
                        st.rerun()
                    else:
                        st.error(f"平倉失敗: {res.get('msg', '未知錯誤')}")
                else:
                    # Local Paper Broker sell
                    res = broker.sell(trade_sym, cur_p, pct_position=1.0)
                    if res is not None:
                        st.success(f"已平倉賣出！數量: {res['quantity']:.6f} {trade_sym} | 均價: ${res['price']:,.2f} | 實現盈虧: ${res['realized_pnl']:+,.2f}")
                        st.rerun()
                    else:
                        st.warning("無持倉部位可平。")

    with col_act2:
        st.write("#### 24-Bar 模擬步進推演")
        if st.button("執行 24 根 K 棒 AI 模擬推演", use_container_width=True, key="btn_step_sim"):
            cached_data = dm.load_raw_data(trade_sym, "1h")
            if cached_data is not None and len(cached_data) > 50:
                with st.spinner("模擬撮合中..."):
                    from packages.features import FeaturePipeline
                    from packages.models import LGBMAgent
                    pipeline = FeaturePipeline(target_horizon=3)
                    feat_df, cols = pipeline.build_features(cached_data)
                    agent = LGBMAgent(num_boost_round=50)
                    agent.fit(feat_df, cols)

                    test_bars = feat_df.tail(24)
                    for i in range(len(test_bars)):
                        b = test_bars.iloc[i : i + 1]
                        price = b["close"].iloc[0]
                        pred = agent.predict(b)[0]
                        has_pos = trade_sym in broker.positions and broker.positions[trade_sym]["amount"] > 0
                        if pred > 0.002 and not has_pos:
                            broker.buy(trade_sym, price, usdt_amount=trade_size)
                        elif pred < -0.002 and has_pos:
                            broker.sell(trade_sym, price, pct_position=1.0)
                    st.success("24 根 K 棒模擬推演完成！")
                    st.rerun()
            else:
                st.warning("請先至「研究與回測」下載此幣種的 K 線數據！")

    st.write("#### 目前持倉明細")
    if "BingX" in exec_channel:
        st.caption("顯示 BingX OpenAPI 網關部位")
        positions = gw.get_positions()
        if positions:
            st.dataframe(pd.DataFrame(positions), use_container_width=True)
        else:
            st.info("目前無持倉部位")
    else:
        st.caption(f"顯示模擬經紀商部位 (可用現金: ${broker.cash:,.2f} USDT)")
        if broker.positions:
            pos_data = []
            for sym, pos in broker.positions.items():
                amt = pos["amount"]
                avg_p = pos["avg_price"]
                p = gw.fetch_ticker(sym).get("price", avg_p)
                mkt_val = amt * p
                pnl = (p - avg_p) * amt
                pnl_pct = (((p / avg_p) - 1.0) * 100) if avg_p > 0 else 0.0
                pos_data.append({
                    "標的": sym,
                    "持倉數量": round(amt, 6),
                    "持倉均價 ($)": round(avg_p, 2),
                    "市價 ($)": round(p, 2),
                    "市值 ($)": round(mkt_val, 2),
                    "浮動盈虧 ($)": round(pnl, 2),
                    "報酬率 (%)": f"{pnl_pct:+.2f}%",
                })
            st.dataframe(pd.DataFrame(pos_data), use_container_width=True)
        else:
            st.info("目前為空倉（100% 現金儲備）")
