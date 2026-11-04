from packages.core.state_repository import BotStateRepository
"""Overview Tab View (Mission Control): Executive KPIs, Market Pulse, Dual Bots, and Live Journal."""

import json
from pathlib import Path
import streamlit as st
import pandas as pd

from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager
from packages.core import UnifiedAutopilotEngine, AutopilotState
from apps.dashboard.ui.responsive import render_market_pulse_card

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def discover_active_bot_instances(btc_p: float) -> list[dict]:
    """Scan data/ directory dynamically via domain repository for all active bot state files."""
    return BotStateRepository.discover_active_bots(btc_p)


def render_overview_tab(
    gw: BingXGateway,
    jm: TradeJournalManager,
    autopilot: UnifiedAutopilotEngine,
    load_bot_states_fn,
    get_unified_journal_entries_fn,
):
    """Render the main executive overview tab with fully dynamic multi-bot discovery."""
    journal_stats = jm.get_summary_stats()

    # Dynamic live timestamp banner
    now_str = pd.Timestamp.now().strftime("%H:%M:%S")
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-size: 13px; color: #8b949e;">🟢 即時串流中 | 系統時間: <b style="color:#58a6ff;">{now_str}</b></span>
        <span style="font-size: 12px; color: #8b949e;">自動更新已啟用</span>
    </div>
    """, unsafe_allow_html=True)

    # Fetch real-time market tickers via Gateway
    t_btc = gw.fetch_ticker("BTC/USDT", market_type=MarketType.SPOT.value)
    t_eth = gw.fetch_ticker("ETH/USDT", market_type=MarketType.SPOT.value)
    t_sol = gw.fetch_ticker("SOL/USDT", market_type=MarketType.SPOT.value)

    btc_p = t_btc.get("price", 77400.0)

    # Dynamically scan and discover all active bots in data/
    active_bots = discover_active_bot_instances(btc_p)

    # Compile unified journal entries directly from authoritative TradeJournalManager
    entries, total_realized_pnl, _ = get_unified_journal_entries_fn(jm, btc_p)

    # Dynamic Portfolio Valuation Calculation
    capital_base = sum(b["init_cap"] for b in active_bots) if active_bots else 200.0
    total_portfolio_upnl = sum(b["upnl"] for b in active_bots)
    total_portfolio_equity = capital_base + total_realized_pnl + total_portfolio_upnl
    total_net_pnl = total_realized_pnl + total_portfolio_upnl
    total_pnl_pct = (total_net_pnl / capital_base) * 100.0 if capital_base > 0 else 0.0
    open_trades_count = len([b for b in active_bots if b.get("side") != "NONE"])
    closed_trades_count = len([e for e in entries if e.get("status") == "CLOSED"])

    # ---- Section 0: Compact Autopilot Control Bar ----
    arm_col1, arm_col2, arm_col3 = st.columns([5, 2, 2])
    with arm_col1:
        if autopilot.status == AutopilotState.ARMED:
            status_html = f"""
            <div style="display: flex; align-items: center; gap: 10px; background: rgba(63, 185, 80, 0.12); border: 1px solid #3fb950; border-radius: 6px; padding: 7px 12px;">
                <span style="background: #3fb950; color: #0d1117; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;">ARMED 運行中</span>
                <span style="color: #e6edf3; font-size: 13px;"><b>全自動中樞運行中</b> | 模式: {autopilot.mode} ({autopilot.leverage}x) | AI 風控守門員生效</span>
            </div>
            """
        else:
            status_html = """
            <div style="display: flex; align-items: center; gap: 10px; background: rgba(210, 153, 34, 0.12); border: 1px solid #d29922; border-radius: 6px; padding: 7px 12px;">
                <span style="background: #d29922; color: #0d1117; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;">STANDBY 待機</span>
                <span style="color: #c9d1d9; font-size: 13px;">中樞待機中 (無主動交易指令，需手動授權啟動)</span>
            </div>
            """
        st.markdown(status_html, unsafe_allow_html=True)

    with arm_col2:
        if autopilot.status != AutopilotState.ARMED:
            if st.button("啟動操盤 (ARM)", type="primary", use_container_width=True, key="btn_arm_autopilot"):
                msg = autopilot.arm()
                st.success(msg)
                st.rerun()
        else:
            if st.button("切換待機 (STANDBY)", use_container_width=True, key="btn_disarm_autopilot"):
                msg = autopilot.disarm()
                st.info(msg)
                st.rerun()

    with arm_col3:
        if st.button("緊急全平停機", use_container_width=True, key="btn_emergency_stop"):
            msg = autopilot.emergency_close_and_stop()
            st.warning(msg)
            st.rerun()

    # ---- Section 1: Trader KPI Metric Cards ----
    st.markdown("#### 核心資產與守護狀態")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

    with kpi_col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">總帳戶資產淨值</div>
            <div class="stat-value text-cyan">${total_portfolio_equity:,.2f} USDT</div>
            <div class="stat-sub">本金: ${capital_base:,.2f} | 總淨益: {('+' if total_net_pnl>=0 else '')}${total_net_pnl:,.2f} U ({('+' if total_pnl_pct>=0 else '')}{total_pnl_pct:.2f}%)</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col2:
        pnl_cls = "text-green" if total_portfolio_upnl >= 0 else "text-red"
        sign = "+" if total_portfolio_upnl >= 0 else ""
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">未平倉浮動盈虧</div>
            <div class="stat-value {pnl_cls}">{sign}${total_portfolio_upnl:,.2f} USDT</div>
            <div class="stat-sub">持倉中: {open_trades_count} 筆 | 浮動回報: <span class="{pnl_cls}">{sign}{((total_portfolio_upnl/capital_base)*100 if capital_base>0 else 0):.2f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col3:
        real_cls = "text-green" if total_realized_pnl >= 0 else "text-red"
        r_sign = "+" if total_realized_pnl >= 0 else ""
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">歷史已平倉實現盈虧</div>
            <div class="stat-value {real_cls}">{r_sign}${total_realized_pnl:,.2f} USDT</div>
            <div class="stat-sub">已結算: {closed_trades_count} 筆 | 勝率: {journal_stats['win_rate']:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col4:
        auto_cls = "text-green" if (autopilot.status == AutopilotState.ARMED or len(active_bots) > 0) else "text-amber"
        auto_lbl = f"{len(active_bots)} 守護運行中" if len(active_bots) > 0 else ("中樞已啟動" if autopilot.status == AutopilotState.ARMED else "中樞待機")
        bots_summary_str = " | ".join(f"{b['short_title']}" for b in active_bots) if active_bots else "無活躍進程"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">守護進程狀態</div>
            <div class="stat-value {auto_cls}">{auto_lbl}</div>
            <div class="stat-sub">{bots_summary_str}</div>
        </div>
        """, unsafe_allow_html=True)

    # ---- Section 2: Real-time Market Pulse Grid (3 Clean Crypto Majors) ----
    st.markdown("#### 即時行情脈動")
    pulse_col1, pulse_col2, pulse_col3 = st.columns(3)

    with pulse_col1:
        render_market_pulse_card(
            symbol="BTC/USDT",
            name="比特幣",
            price=btc_p,
            change_24h_pct=t_btc.get("change_24h_pct", 0.0),
            high_24h=t_btc.get("high_24h", btc_p),
            low_24h=t_btc.get("low_24h", btc_p),
            source=t_btc.get("source", "WEBSOCKET"),
        )

    with pulse_col2:
        render_market_pulse_card(
            symbol="ETH/USDT",
            name="以太幣",
            price=t_eth.get("price", 0.0),
            change_24h_pct=t_eth.get("change_24h_pct", 0.0),
            high_24h=t_eth.get("high_24h", 0.0),
            low_24h=t_eth.get("low_24h", 0.0),
            source=t_eth.get("source", "WEBSOCKET"),
        )

    with pulse_col3:
        render_market_pulse_card(
            symbol="SOL/USDT",
            name="Solana",
            price=t_sol.get("price", 0.0),
            change_24h_pct=t_sol.get("change_24h_pct", 0.0),
            high_24h=t_sol.get("high_24h", 0.0),
            low_24h=t_sol.get("low_24h", 0.0),
            source=t_sol.get("source", "WEBSOCKET"),
        )

    # ---- Section 3: Dynamic Multi-Bot Live Monitor ----
    st.markdown("#### 量化守護進程倉位與風控")
    if active_bots:
        cols_per_row = min(len(active_bots), 4)
        for i in range(0, len(active_bots), cols_per_row):
            row_bots = active_bots[i:i + cols_per_row]
            cols = st.columns(len(row_bots))
            for col, b in zip(cols, row_bots):
                with col:
                    is_none = (b['side'] == "NONE")
                    if is_none:
                        st.markdown(f"""
                        <div class="stat-card" style="border-left: 4px solid {b['border_color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-weight: 700; font-size: 14px; color: {b['title_color']};">{b['title']}</span>
                                <div>
                                    <span class="badge-lev">{b['leverage']}x</span>
                                    &nbsp;
                                    <span class="badge-idle">空倉待機</span>
                                </div>
                            </div>
                            <div style="text-align: center; padding: 16px 0; color: #8b949e;">
                                <div style="font-size: 18px; font-weight: 700; color: #f0f6fc; margin-bottom: 4px;">${b['avail']:.2f} USDT</div>
                                <div style="font-size: 12px;">100% 現金儲備 | 監控切入點</div>
                            </div>
                            <div style="font-size: 11px; color: #8b949e; border-top: 1px solid #21262d; padding-top: 4px; margin-bottom: 8px;">
                                風控: {b['risk_desc']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        liq_str = f"${b['liq_price']:,.2f}" if b['liq_price'] > 0 else "現貨無強平"
                        pnl_color = "text-green" if b['upnl'] >= 0 else "text-red"
                        badge_cls = "badge-long" if b['side'] == "LONG" else "badge-short"
                        side_name = "多頭 LONG" if b['side'] == "LONG" else "空頭 SHORT"

                        st.markdown(f"""
                        <div class="stat-card" style="border-left: 4px solid {b['border_color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <span style="font-weight: 700; font-size: 14px; color: {b['title_color']};">{b['title']}</span>
                                <div>
                                    <span class="badge-lev">{b['leverage']}x</span>
                                    &nbsp;
                                    <span class="{badge_cls}">{side_name}</span>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
                                <span style="font-size: 12px; color: #8b949e;">未實現損益 (ROE)</span>
                                <span class="{pnl_color}" style="font-size: 16px; font-weight: 700;">${b['upnl']:+,.2f} U ({b['upnl_pct']:+.2f}%)</span>
                            </div>
                            <div style="font-size: 12px; color: #c9d1d9; line-height: 1.7; margin-bottom: 6px;">
                                <div style="display: flex; justify-content: space-between;">
                                    <span style="color: #8b949e;">持倉數量</span>
                                    <b>{b['qty']:.6f} BTC</b>
                                </div>
                                <div style="display: flex; justify-content: space-between;">
                                    <span style="color: #8b949e;">進場均價</span>
                                    <b>${b['cost']:,.2f}</b>
                                </div>
                                <div style="display: flex; justify-content: space-between;">
                                    <span style="color: #8b949e;">保證金 / 淨值</span>
                                    <span>${b['avail']:.1f} / <b>${b['equity']:.1f} U</b></span>
                                </div>
                                <div style="display: flex; justify-content: space-between;">
                                    <span style="color: #8b949e;">強平參考</span>
                                    <span style="color: #e3b341;">{liq_str}</span>
                                </div>
                            </div>
                            <div style="font-size: 11px; color: #8b949e; border-top: 1px solid #21262d; padding-top: 4px; margin-bottom: 8px;">
                                風控: {b['risk_desc']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                    if st.button(b["stop_btn_label"], key=f"btn_stop_{b['id']}", use_container_width=True):
                        b["stop_flag"].touch()
                        st.success(f"已發送停止信號 ({b['stop_flag'].name})")
    else:
        st.info("目前無任何活躍的守護進程，請透過 CLI 或自動操盤中樞啟動。")

    # ---- Section 4: Latest Trade Reflection ----
    st.markdown("#### 最新精簡覆盤 (進場依據 / 風控決策 / 出場結果)")
    if entries:
        lj = entries[0]
        with st.container():
            pnl_color = "#3fb950" if lj.get("pnl_usdt", 0) >= 0 else "#f85149"
            sign = "+" if lj.get("pnl_usdt", 0) >= 0 else ""
            is_open = lj.get("status") == "OPEN"
            status_tag = '<span class="badge-long">持倉中 OPEN</span>' if is_open else '<span class="badge-idle">已平倉結算 CLOSED</span>'
            pnl_title = "浮動盈虧" if is_open else "實現盈虧"

            # Clean repetitive boilerplate from thesis
            raw_thesis = lj.get('why_enter', '--')
            clean_thesis = raw_thesis.split('\n【系統觸發信號】')[0].split('\n【交易架構】')[0].strip()

            st.markdown(f"""
            <div class="stat-card" style="border-left: 4px solid {pnl_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div>
                        <span style="color: #f0f6fc; font-weight: bold; font-size: 15px;">
                            #{lj.get('id', '--')} ({lj.get('market', '--')})
                        </span>
                        &nbsp; {status_tag}
                    </div>
                    <span style="font-weight: bold; color: {pnl_color}; font-size: 15px;">
                        {pnl_title}: {sign}${lj.get('pnl_usdt', 0):.2f} USDT ({sign}{lj.get('pnl_pct', 0):.2f}%)
                    </span>
                </div>
                <div style="font-size: 13px; line-height: 1.8; color: #c9d1d9;">
                    <div><b style="color: #58a6ff;">【進場依據】：</b> {clean_thesis}</div>
                    <div><b style="color: #bc8cff;">【風控決策】：</b> {lj.get('ai_decision', '--')}</div>
                    <div><b style="color: #3fb950;">【出場結果】：</b> {lj.get('exit_result', '--')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("目前尚無交易紀錄。")

    return entries, btc_p
