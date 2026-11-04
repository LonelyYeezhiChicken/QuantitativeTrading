"""Journal Tab View: Noise-Free 3-Question Cards & Interactive Deep Technical Inspection."""

import streamlit as st
import pandas as pd
from packages.journal import TradeJournalManager


def render_journal_tab(jm: TradeJournalManager, entries: list[dict]):
    """Render the trade journal tab."""
    st.subheader("交易覆盤日誌 (Trade Journal)")

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        stat_filter = st.selectbox("狀態篩選", ["全部記錄 (ALL)", "持倉中 (OPEN)", "已平倉結算 (CLOSED)"], index=0, key="j_stat_filter")
    with col_f2:
        st.write("")
        st.write("")
        if st.button("刷新日誌", key="btn_refresh_journal", use_container_width=True):
            st.rerun()

    filter_status = None if "全部" in stat_filter else ("OPEN" if "OPEN" in stat_filter else "CLOSED")

    filtered_entries = entries
    if filter_status:
        filtered_entries = [j for j in entries if j.get("status") == filter_status]

    if filtered_entries:
        for j in filtered_entries:
            pnl_val = j.get("pnl_usdt", 0.0)
            pnl_pct = j.get("pnl_pct", 0.0)
            pnl_color = "#3fb950" if pnl_val >= 0 else "#f85149"
            sign = "+" if pnl_val >= 0 else ""
            is_open = j.get("status") == "OPEN"
            status_badge = '<span style="background: rgba(63, 185, 80, 0.2); color: #3fb950; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">[持倉中 OPEN]</span>' if is_open else '<span style="background: rgba(88, 166, 255, 0.2); color: #58a6ff; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">[已平倉結算 CLOSED]</span>'
            pnl_tag_title = "當前浮動盈虧" if is_open else "已平倉實現盈虧"

            st.markdown(f"""
            <div class="stat-card" style="border-left: 4px solid {pnl_color}; margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin-bottom: 10px;">
                    <div>
                        <span style="font-weight: bold; font-size: 15px; color: #e6edf3;">#{j.get('id', '--')}</span>
                        <span style="background: rgba(88, 166, 255, 0.2); color: #58a6ff; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-left: 8px;">{j.get('market', 'BTC/USDT')}</span>
                        <span style="background: {'rgba(63, 185, 80, 0.2)' if j.get('side')=='LONG' else 'rgba(248, 81, 73, 0.2)'}; color: {'#3fb950' if j.get('side')=='LONG' else '#f85149'}; padding: 2px 6px; border-radius: 4px; font-size: 12px; margin-left: 4px; font-weight: bold;">{j.get('side', '--')}</span>
                        &nbsp; {status_badge}
                        <span style="color: #8b949e; font-size: 12px; margin-left: 10px;">時間: {j.get('time', '--')}</span>
                    </div>
                    <div style="font-size: 15px; font-weight: bold; color: {pnl_color};">
                        {pnl_tag_title}: {sign}${pnl_val:,.2f} USDT ({sign}{pnl_pct:.2f}%)
                    </div>
                </div>
                <div style="font-size: 14px; line-height: 1.8; color: #c9d1d9;">
                    <div style="margin-bottom: 6px;">
                        <span style="color: #58a6ff; font-weight: bold;">【為什麼要進場】：</span>
                        <span>{j.get('why_enter', '--')}</span>
                    </div>
                    <div style="margin-bottom: 6px;">
                        <span style="color: #bc8cff; font-weight: bold;">【AI 的決策是什麼】：</span>
                        <span>{j.get('ai_decision', '--')}</span>
                    </div>
                    <div>
                        <span style="color: #3fb950; font-weight: bold;">【出場原因與結果】：</span>
                        <span>{j.get('exit_result', '--')}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("目前無符合條件的覆盤日誌。")

    # Section B: Interactive Single Trade Deep Inspection
    st.markdown("---")
    st.markdown("#### 單筆交易深度檢驗與技術快照")
    if entries:
        entry_opts = [
            f"#{e['id']} | {e['market']} | {e['side']} | {e['status']} | 盈虧: ${e['pnl_usdt']:+,.2f} U"
            for e in entries
        ]
        selected_idx = st.selectbox(
            "選擇欲深入檢驗的交易日誌 (查看開倉快照、風控計畫與動態軌跡)",
            range(len(entry_opts)),
            format_func=lambda i: entry_opts[i],
            key="sel_journal_detail",
        )
        sel_entry = entries[selected_idx]["raw_entry"]

        insp_c1, insp_c2 = st.columns(2)
        with insp_c1:
            st.markdown("##### 1. 開倉當下技術面快照 (Technical Snapshot)")
            snap = sel_entry.snapshot
            snap_rows = [
                {"指標名稱": "開倉時市價 (Price)", "數值": f"${snap.price:,.2f}"},
                {"指標名稱": "14 期相對強弱指標 (RSI)", "數值": f"{snap.rsi:.2f}"},
                {"指標名稱": "EMA21 指數移動平均線", "數值": f"${snap.ema21:,.2f}"},
                {"指標名稱": "均線乖離率 (Bias %)", "數值": f"{snap.bias_pct:+.2f}%"},
                {"指標名稱": "14 期真實波動幅度 (ATR)", "數值": f"${snap.atr:,.2f}"},
                {"指標名稱": "委買 / 委賣盤口 (Bid / Ask)", "數值": f"${snap.bid:,.2f} / ${snap.ask:,.2f}"},
            ]
            st.dataframe(pd.DataFrame(snap_rows), use_container_width=True, hide_index=True)

        with insp_c2:
            st.markdown("##### 2. 風控計畫與動態軌跡 (Risk Plan & Trajectory)")
            rp = sel_entry.risk_plan
            tj = sel_entry.trajectory
            risk_rows = [
                {"項目": "硬停損價格 / 幅度", "數值": f"${rp.stop_loss_price:,.2f} (-{rp.stop_loss_pct:.1f}%)"},
                {"項目": "最大允許虧損 (USDT)", "數值": f"${rp.max_loss_usdt:,.2f} U"},
                {"項目": "動態移動停利回撤門檻", "數值": f"{rp.trailing_pullback_pct:.1f}%"},
                {"項目": "持倉期間最高價 (Peak)", "數值": f"${tj.highest_price:,.2f}"},
                {"項目": "持倉期間最低價 (Trough)", "數值": f"${tj.lowest_price:,.2f}"},
                {"項目": "最大有利/不利幅度 (MFE / MAE)", "數值": f"{tj.mfe_pct:+.2f}% / {tj.mae_pct:+.2f}%"},
                {"項目": "動態軌跡更新次數", "數值": f"{tj.updates_count} 次"},
            ]
            st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True)

        with st.expander("【進場核心邏輯與假說 (Pre-trade Thesis)】", expanded=True):
            st.write(sel_entry.review.thesis or "--")

        with st.expander("【出場原因與策略評估 (Exit & Strategy Evaluation)】", expanded=True):
            st.write(f"**出場原因與狀態**: {sel_entry.review.exit_reason}")
            st.write(f"**策略品質評估**: {sel_entry.review.strategy_evaluation}")

        with st.expander("【交易教學與覆盤心得 (Pedagogical Takeaway)】", expanded=False):
            st.info(sel_entry.review.pedagogical_takeaway or "嚴格遵守紀律，落實交易計畫。")

        with st.expander("【原始 Markdown 覆盤卡片原始碼 (Raw Markdown Entry)】", expanded=False):
            st.code(sel_entry.to_markdown(), language="markdown")

    # Collapsible technical inspection for deep exploration
    with st.expander("展開完整日誌資料庫彙總表 (所有歷史紀錄)", expanded=False):
        db_entries = jm.get_entries()
        if db_entries:
            table_rows = []
            for e in db_entries:
                pnl_s = f"${e.pnl_usdt:+,.2f}" if e.status == "CLOSED" else "持倉中"
                roi_s = f"{e.pnl_pct:+.2f}%" if e.status == "CLOSED" else "--"
                exit_s = f"${e.exit_price:,.2f}" if e.status == "CLOSED" else "持倉中"
                table_rows.append({
                    "日誌編號": e.journal_id,
                    "開倉時間": e.entry_time[:16] if e.entry_time else "--",
                    "市場": e.market_type,
                    "方向": e.side,
                    "開倉均價 ($)": round(e.entry_price, 2),
                    "平倉均價 ($)": exit_s,
                    "實現盈虧 ($)": pnl_s,
                    "報酬率 (%)": roi_s,
                    "狀態": e.status,
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True)
        else:
            st.caption("無額外底層快照。")
