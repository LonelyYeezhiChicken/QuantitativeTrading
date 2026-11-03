"""Overview Tab View (Mission Control): Executive KPIs, Market Pulse, Dual Bots, and Live Journal."""

import json
from pathlib import Path
import streamlit as st
import pandas as pd

from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager
from packages.core import UnifiedAutopilotEngine, AutopilotState
from apps.dashboard.ui.responsive import render_market_pulse_card, render_gold_macro_card

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def discover_active_bot_instances(btc_p: float) -> list[dict]:
    """Scan data/ directory dynamically for all active bot state files (SPOT, SWAP 3x, 10x, 50x, etc.)."""
    instances = []
    data_dir = ROOT_DIR / "data"
    if not data_dir.exists():
        return instances

    # 1. Spot bots
    for f in sorted(data_dir.glob("bingx_paper_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                st_data = json.load(fp)
            pos = st_data.get("position", {})
            side = pos.get("side", "NONE")
            qty = pos.get("amount_btc", 0.0)
            cost = pos.get("entry_price", btc_p)
            cash = st_data.get("cash_usdt", 0.0)
            init_cap = st_data.get("initial_capital", 100.0)
            mkt_val = qty * btc_p
            upnl = (btc_p - cost) * qty if side == "LONG" else 0.0
            equity = cash + mkt_val
            instances.append({
                "id": f.stem,
                "file": f,
                "title": "現貨交易守護 (SPOT 1x)",
                "short_title": "SPOT 1x",
                "market_type": "SPOT",
                "leverage": 1,
                "border_color": "#58a6ff",
                "title_color": "#58a6ff",
                "side": side,
                "qty": qty,
                "cost": cost,
                "mkt_val": mkt_val,
                "upnl": upnl,
                "upnl_pct": (upnl / 50.0 * 100.0) if side != "NONE" else 0.0,
                "avail": cash,
                "equity": equity,
                "init_cap": init_cap,
                "liq_price": 0.0,
                "risk_desc": "移動停利 (回撤 0.4%) | 硬停損 (-1.5%)",
                "stop_flag": ROOT_DIR / "data" / "bot_stop.flag",
                "stop_btn_label": "安全停止現貨進程",
            })
        except Exception:
            pass

    # 2. Swap bots (bingx_swap_*.json)
    for f in sorted(data_dir.glob("bingx_swap_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                st_data = json.load(fp)
            pos = st_data.get("position", {})
            side = pos.get("side", "NONE")
            qty = pos.get("amount_btc", 0.0)
            cost = pos.get("entry_price", btc_p)
            margin = pos.get("margin_used", 50.0)
            avail = st_data.get("available_margin", 50.0)
            init_cap = st_data.get("initial_capital", 100.0)
            lev = pos.get("leverage", st_data.get("leverage", 3))
            liq_p = pos.get("liquidation_price", 0.0)

            if side == "LONG":
                upnl = (btc_p - cost) * qty
            elif side == "SHORT":
                upnl = (cost - btc_p) * qty
            else:
                upnl = 0.0
            equity = avail + margin + upnl
            upnl_pct = (upnl / margin * 100.0) if (margin > 0 and side != "NONE") else 0.0

            # Styling and labeling based on leverage
            if lev <= 3:
                b_color = "#a371f7"  # Purple
                t_label = f"永續合約守護 (SWAP {lev}x)"
                risk_info = f"動態追蹤停利 (回撤 1.0%) | 原生硬止損 (-{4.0 if lev<=3 else 15.0}% 雲端守護)"
            elif lev <= 10:
                b_color = "#f0883e"  # Orange
                t_label = f"高槓桿合約 (SWAP {lev}x)"
                risk_info = "價格停損 (-1.5%) | 目標停利 (+20.0% ROE) | 雲端原生硬停損"
            else:
                b_color = "#f85149"  # Crimson / Red
                t_label = f"超高槓桿合約 (SWAP {lev}x)"
                risk_info = f"自適應超微停損 (-{round(15.0/lev, 2)}%) | 移動鎖利 | 雲端原生硬停損"

            stem_name = f.stem.replace("bingx_", "")
            stop_flag_name = "swap_stop.flag" if stem_name == "swap_100u" else f"{stem_name}_stop.flag"

            instances.append({
                "id": f.stem,
                "file": f,
                "title": t_label,
                "short_title": f"SWAP {lev}x",
                "market_type": "SWAP",
                "leverage": lev,
                "border_color": b_color,
                "title_color": b_color,
                "side": side,
                "qty": qty,
                "cost": cost,
                "mkt_val": qty * btc_p,
                "upnl": upnl,
                "upnl_pct": upnl_pct,
                "avail": avail,
                "equity": equity,
                "init_cap": init_cap,
                "liq_price": liq_p,
                "risk_desc": risk_info,
                "stop_flag": ROOT_DIR / "data" / stop_flag_name,
                "stop_btn_label": f"安全停止 {lev}x 進程",
            })
        except Exception:
            pass

    return instances


def render_overview_tab(
    gw: BingXGateway,
    jm: TradeJournalManager,
    autopilot: UnifiedAutopilotEngine,
    load_bot_states_fn,
    get_unified_journal_entries_fn,
):
    """Render the main executive overview tab with fully dynamic multi-bot discovery."""
    journal_stats = jm.get_summary_stats()

    # Fetch real-time market tickers via Gateway
    t_btc = gw.fetch_ticker("BTC/USDT", market_type=MarketType.SPOT.value)
    t_eth = gw.fetch_ticker("ETH/USDT", market_type=MarketType.SPOT.value)
    t_sol = gw.fetch_ticker("SOL/USDT", market_type=MarketType.SPOT.value)
    t_xaut = gw.fetch_ticker("XAUT/USDT", market_type=MarketType.SPOT.value)

    btc_p = t_btc.get("price", 77400.0)
    xaut_p = t_xaut.get("price", 3935.0)

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

    # ---- Section 0: Autopilot Safety & Manual Arming Hub ----
    st.markdown("#### 自動操盤中樞與手動啟動控制")
    arm_col1, arm_col2, arm_col3 = st.columns([2, 1, 1])

    with arm_col1:
        if autopilot.status == AutopilotState.ARMED:
            st.markdown("""
            <div style="background: rgba(63, 185, 80, 0.15); border: 1px solid #3fb950; border-radius: 8px; padding: 12px 16px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="background: #3fb950; color: #0d1117; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 13px;">[ARMED 守護運行中]</span>
                    <b style="color: #e6edf3; font-size: 15px;">自動操盤中樞已武裝上線</b>
                </div>
                <div style="color: #8b949e; font-size: 13px; margin-top: 5px;">
                    運作流程：即時時序特徵 -> Ollama 二選一風控守門員 (EXECUTE/VETO) -> 嚴格硬停損與動態移動停利。
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background: rgba(210, 153, 34, 0.15); border: 1px solid #d29922; border-radius: 8px; padding: 12px 16px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="background: #d29922; color: #0d1117; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 13px;">[STANDBY 安全待機]</span>
                    <b style="color: #e6edf3; font-size: 15px;">安全待機模式 (未經手動授權絕不自動下單)</b>
                </div>
                <div style="color: #8b949e; font-size: 13px; margin-top: 5px;">
                    防呆保護：系統啟動預設待機，絕不主動下單，等待交易員手動指令。
                </div>
            </div>
            """, unsafe_allow_html=True)

    with arm_col2:
        st.write("")
        if autopilot.status != AutopilotState.ARMED:
            if st.button("手動啟動自動操盤 (ARM)", type="primary", use_container_width=True, key="btn_arm_autopilot"):
                msg = autopilot.arm()
                st.success(msg)
                st.rerun()
        else:
            if st.button("暫停操盤 (STANDBY)", use_container_width=True, key="btn_disarm_autopilot"):
                msg = autopilot.disarm()
                st.info(msg)
                st.rerun()

    with arm_col3:
        st.write("")
        if st.button("緊急平倉並停機", use_container_width=True, key="btn_emergency_stop"):
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
            <div class="stat-sub">配置本金: ${capital_base:,.2f} (總淨盈虧: {('+' if total_net_pnl>=0 else '')}${total_net_pnl:,.2f} U)</div>
        </div>
        """, unsafe_allow_html=True)

    with kpi_col2:
        pnl_cls = "text-green" if total_portfolio_upnl >= 0 else "text-red"
        sign = "+" if total_portfolio_upnl >= 0 else ""
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">當前未平倉浮動盈虧</div>
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
        auto_lbl = f"{len(active_bots)} 守護運行中" if len(active_bots) > 0 else ("已啟動守護 (ARMED)" if autopilot.status == AutopilotState.ARMED else "待機安全模式 (STANDBY)")
        bots_summary_str = " | ".join(f"{b['short_title']}" for b in active_bots) if active_bots else "無活躍進程"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">自動操盤中樞狀態</div>
            <div class="stat-value {auto_cls}">{auto_lbl}</div>
            <div class="stat-sub">{bots_summary_str}</div>
        </div>
        """, unsafe_allow_html=True)

    # ---- Section 2: Real-time Market Pulse Grid ----
    st.markdown("#### 即時行情脈動")
    pulse_col1, pulse_col2, pulse_col3, pulse_col4 = st.columns(4)

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

    with pulse_col4:
        render_market_pulse_card(
            symbol="XAUT/USDT",
            name="泰達黃金 (1 盎司純金)",
            price=xaut_p,
            change_24h_pct=t_xaut.get("change_24h_pct", 0.0),
            high_24h=t_xaut.get("high_24h", xaut_p),
            low_24h=t_xaut.get("low_24h", xaut_p),
            is_gold=True,
            source=t_xaut.get("source", "WEBSOCKET"),
        )

    # Macro Gold Ratio
    render_gold_macro_card(btc_price=btc_p, xaut_price=xaut_p)

    # ---- Section 3: Dynamic Multi-Bot Live Monitor ----
    st.markdown("#### 量化守護進程倉位與風控")
    if active_bots:
        cols_per_row = min(len(active_bots), 4)
        for i in range(0, len(active_bots), cols_per_row):
            row_bots = active_bots[i:i + cols_per_row]
            cols = st.columns(len(row_bots))
            for col, b in zip(cols, row_bots):
                with col:
                    liq_str = f"${b['liq_price']:,.2f}" if b['liq_price'] > 0 else "現貨無強平"
                    pnl_color = "text-green" if b['upnl'] >= 0 else "text-red"
                    st.markdown(f"""
                    <div class="stat-card" style="border-left: 4px solid {b['border_color']};">
                        <div class="stat-title" style="color: {b['title_color']}; font-weight: bold;">{b['title']}</div>
                        <div style="font-size: 15px; margin-bottom: 8px;">
                            持倉狀態: <b>{b['side']}</b> ({b['qty']:.6f} BTC, {b['leverage']}x 槓桿)<br>
                            進場均價: <b>${b['cost']:,.2f}</b> | 強平價: <b>{liq_str}</b><br>
                            未實現盈虧: <span class="{pnl_color}"><b>${b['upnl']:+,.2f} U ({b['upnl_pct']:+.2f}%)</b></span><br>
                            可用資金: <b>${b['avail']:.2f} U</b> | 單元權益: <b>${b['equity']:.2f} USDT</b>
                        </div>
                        <div class="stat-sub">風控規則: {b['risk_desc']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(b["stop_btn_label"], key=f"btn_stop_{b['id']}", use_container_width=True):
                        b["stop_flag"].touch()
                        st.success(f"已寫入停止標誌 ({b['stop_flag'].name})")
    else:
        st.info("目前無任何活躍的守護進程，請透過 CLI 或自動操盤中樞啟動。")

    # ---- Section 4: Latest Trade Reflection ----
    st.markdown("#### 最新精簡覆盤 (為什麼進場 / 決策是什麼 / 出場與結果)")
    if entries:
        lj = entries[0]
        with st.container():
            pnl_color = "#3fb950" if lj.get("pnl_usdt", 0) >= 0 else "#f85149"
            sign = "+" if lj.get("pnl_usdt", 0) >= 0 else ""
            is_open = lj.get("status") == "OPEN"
            status_tag = '<span style="background: rgba(63, 185, 80, 0.2); color: #3fb950; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">[持倉中 OPEN]</span>' if is_open else '<span style="background: rgba(88, 166, 255, 0.2); color: #58a6ff; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;">[已平倉結算 CLOSED]</span>'
            pnl_title = "當前浮動盈虧" if is_open else "實現盈虧"

            st.markdown(f"""
            <div class="stat-card" style="border-left: 4px solid {pnl_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div>
                        <span class="stat-title" style="color: {pnl_color}; font-weight: bold; font-size: 15px;">
                            日誌編號：{lj.get('id', '--')} ({lj.get('side', '--')})
                        </span>
                        &nbsp; {status_tag}
                    </div>
                    <span style="font-weight: bold; color: {pnl_color}; font-size: 15px;">
                        {pnl_title}: {sign}${lj.get('pnl_usdt', 0):.2f} USDT ({sign}{lj.get('pnl_pct', 0):.2f}%)
                    </span>
                </div>
                <div style="font-size: 14px; line-height: 1.8; color: #c9d1d9;">
                    <div><b style="color: #58a6ff;">【為什麼要進場】：</b> {lj.get('why_enter', '--')}</div>
                    <div><b style="color: #bc8cff;">【AI 的決策是什麼】：</b> {lj.get('ai_decision', '--')}</div>
                    <div><b style="color: #3fb950;">【出場原因與結果】：</b> {lj.get('exit_result', '--')}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("目前尚無交易紀錄。")

    return entries, btc_p
