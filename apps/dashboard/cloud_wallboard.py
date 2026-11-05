"""Streamlit Cloud Wallboard: Zero-Button Read-Only Status & Mission Control Dashboard.

Designed specifically for 24/7 Cloud VPS Deployment:
- Pure read-only status display: Zero buttons, zero forms, zero risk of accidental misclicks.
- High-visibility executive HUD: Live Total Equity, 3 Bot Status Cards (3x, 10x, 50x), Market Regime.
- Real-time auto-refresh every 5 seconds.
- Multi-device responsive: Renders cleanly on iPhone, iPad, Android, and Desktop browsers.
"""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.state_repository import BotStateRepository
from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager

TZ_TAIPEI = timezone(timedelta(hours=8))

# 1. Page Configuration (Wide layout, Trading Terminal Title)
st.set_page_config(
    page_title="量化操盤雲端即時監控看板",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. High-Tech Dark Terminal Styling (No hard meta refresh, uses smooth st.fragment)
st.markdown(
    """
    <style>
        /* Overall Dark Theme & Clean Background */
        .stApp {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        /* Top Navigation Bar */
        .hud-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 20px;
            background: linear-gradient(90deg, #161b22 0%, #0d1117 100%);
            border: 1px solid #30363d;
            border-radius: 8px;
            margin-bottom: 16px;
        }
        .status-badge {
            background-color: #238636;
            color: #ffffff;
            font-size: 0.85rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .pulse-dot {
            width: 8px;
            height: 8px;
            background-color: #3fb950;
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px #3fb950;
        }
        /* Metric Card Container */
        .metric-card {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .metric-title {
            color: #8b949e;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .metric-value {
            font-size: 1.8rem;
            font-weight: 800;
            color: #f0f6fc;
        }
        .metric-sub {
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 4px;
        }
        .text-green { color: #3fb950 !important; }
        .text-red { color: #f85149 !important; }
        .text-blue { color: #58a6ff !important; }
        .text-purple { color: #bc8cff !important; }
        .text-orange { color: #f0883e !important; }
        
        /* Bot Standalone Card */
        .bot-card {
            background-color: #161b22;
            border-radius: 8px;
            padding: 18px;
            border: 1px solid #30363d;
            margin-bottom: 12px;
        }
        .bot-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #21262d;
            padding-bottom: 10px;
            margin-bottom: 12px;
        }
        .bot-title {
            font-size: 1.15rem;
            font-weight: 700;
        }
        .pos-badge-flat {
            background-color: #21262d;
            color: #8b949e;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .pos-badge-long {
            background-color: #238636;
            color: #ffffff;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 700;
        }
        .pos-badge-short {
            background-color: #da3633;
            color: #ffffff;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 700;
        }
        .kv-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.9rem;
            padding: 4px 0;
            border-bottom: 1px dashed #21262d;
        }
        .kv-row:last-child {
            border-bottom: none;
        }
        .kv-key {
            color: #8b949e;
        }
        .kv-val {
            font-weight: 600;
            color: #c9d1d9;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3)
def fetch_live_market_data() -> tuple[float, dict]:
    """Fetch real-time BTC ticker and 1h technical indicators without blocking."""
    try:
        gw = BingXGateway(dry_run=True, enable_ws=False)
        ticker = gw.fetch_ticker("BTC/USDT", market_type=MarketType.SWAP.value)
        cur_p = float(ticker.get("price") or 80000.0)
    except Exception:
        cur_p = 80000.0

    sig = {"rsi": 50.0, "ema21": cur_p, "bias_pct": 0.0}
    try:
        resp = gw.client.fetch_klines("BTC-USDT", interval="1h", limit=50)
        k_data = resp.get("data", [])
        if k_data and len(k_data) >= 21:
            closes = [float(x[4]) for x in k_data][::-1]
            from packages.core.autopilot_engine import compute_structural_indicators_from_ohlc
            highs = [float(x[2]) for x in k_data][::-1]
            lows = [float(x[3]) for x in k_data][::-1]
            sig_calc = compute_structural_indicators_from_ohlc(closes, highs, lows, cur_p)
            ema21 = float(sig_calc.get("ema21", cur_p))
            rsi = float(sig_calc.get("rsi", 50.0))
            bias_pct = ((cur_p - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0
            sig = {"rsi": rsi, "ema21": ema21, "bias_pct": bias_pct}
    except Exception:
        pass

    return cur_p, sig


def format_to_taipei_time(utc_time_str: str | None) -> str:
    """Convert UTC or ISO string to Asia/Taipei formatted timestamp."""
    if not utc_time_str:
        return "—"
    try:
        clean = str(utc_time_str).replace(" UTC", "").strip()
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_tp = dt.astimezone(TZ_TAIPEI)
        return dt_tp.strftime("%m/%d %H:%M:%S")
    except Exception:
        return str(utc_time_str)[:19]


@st.fragment(run_every=5)
def render_live_wallboard():
    now_tp = datetime.now(TZ_TAIPEI)
    cur_p, sig = fetch_live_market_data()

    # Discover the 3 bots dynamically from disk state
    bots = BotStateRepository.discover_active_bots(cur_p, root_dir=ROOT_DIR)

    # Calculate Totals
    total_capital = sum(b.get("init_cap", 200.0) for b in bots) or 600.0
    total_equity = sum(b.get("equity", 200.0) for b in bots) or total_capital
    total_upnl = sum(b.get("upnl", 0.0) for b in bots)
    total_net_pnl = total_equity - total_capital
    total_net_pct = (total_net_pnl / total_capital * 100.0) if total_capital > 0 else 0.0
    active_in_pos = sum(1 for b in bots if b.get("side") not in ("NONE", None, ""))

    # ================= Header Bar =================
    st.markdown(
        f"""
        <div class="hud-header">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.4rem; font-weight: 800; color: #f0f6fc;">⚡ 量化操盤即時監控看板</span>
                <span class="status-badge"><span class="pulse-dot"></span> 24/7 雲端守護中</span>
            </div>
            <div style="text-align: right;">
                <span style="font-size: 1.1rem; font-weight: 700; color: #58a6ff;">BTC/USDT: ${cur_p:,.2f}</span>
                <span style="font-size: 0.85rem; color: #8b949e; margin-left: 12px;">台北時間: {now_tp.strftime('%Y-%m-%d %H:%M:%S')} (每 5 秒自動更新)</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ================= Top 4 KPI Cards =================
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">總帳戶淨值 (USDT)</div>
                <div class="metric-value text-blue">${total_equity:,.2f}</div>
                <div class="metric-sub text-blue">總初始本金: ${total_capital:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        pnl_class = "text-green" if total_net_pnl >= 0 else "text-red"
        pnl_sign = "+" if total_net_pnl >= 0 else ""
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">累計總淨利 (REALIZED)</div>
                <div class="metric-value {pnl_class}">{pnl_sign}${total_net_pnl:,.2f}</div>
                <div class="metric-sub {pnl_class}">{pnl_sign}{total_net_pct:.2f}% 實盤總報酬</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        upnl_class = "text-green" if total_upnl > 0 else ("text-red" if total_upnl < 0 else "text-blue")
        upnl_sign = "+" if total_upnl >= 0 else ""
        pos_desc = f"{active_in_pos} / {len(bots)} 台持倉中" if active_in_pos > 0 else "全部空倉待機中"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">當前浮動損益 (UNREALIZED)</div>
                <div class="metric-value {upnl_class}">{upnl_sign}${total_upnl:,.2f}</div>
                <div class="metric-sub text-blue">{pos_desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        bias = sig.get("bias_pct", 0.0)
        rsi = sig.get("rsi", 50.0)
        bias_color = "text-orange" if bias > 0.45 else ("text-green" if bias >= -1.0 else "text-red")
        bias_text = "正乖離偏大 (防追高生效中)" if bias > 0.45 else "均線貼近健康區間"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">BTC 1H 盤勢位階</div>
                <div class="metric-value" style="font-size: 1.4rem; padding-top: 5px;">RSI: {rsi:.1f} ｜ Bias: {bias:+.2f}%</div>
                <div class="metric-sub {bias_color}">{bias_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ================= 3 Bot Cards (賽馬榜) =================
    st.markdown("### 🏇 三合約守護戰隊實時賽馬榜 (均攤總本金，獨立風控)")

    if not bots:
        st.info("💡 尚未偵測到運行中的守護進程狀態檔案，正在等待交易中樞啟動寫入...")
    else:
        b_cols = st.columns(len(bots))
        for idx, b in enumerate(bots):
            with b_cols[idx]:
                lev = b.get("leverage", 3)
                side = b.get("side", "NONE")
                qty = b.get("qty", 0.0)
                cost = b.get("cost", 0.0)
                avail = b.get("avail", 200.0)
                equity = b.get("equity", 200.0)
                init_cap = b.get("init_cap", 200.0)
                upnl = b.get("upnl", 0.0)
                upnl_pct = b.get("upnl_pct", 0.0)
                bot_ret = ((equity - init_cap) / init_cap * 100.0) if init_cap > 0 else 0.0
                border_c = b.get("border_color", "#58a6ff")

                if side == "LONG":
                    badge_html = '<span class="pos-badge-long">🚀 多單 (LONG)</span>'
                elif side == "SHORT":
                    badge_html = '<span class="pos-badge-short">🔻 空單 (SHORT)</span>'
                else:
                    badge_html = '<span class="pos-badge-flat">🟢 空倉待機</span>'

                ret_class = "text-green" if bot_ret >= 0 else "text-red"
                ret_sign = "+" if bot_ret >= 0 else ""

                st.markdown(
                    f"""
                    <div class="bot-card" style="border-top: 4px solid {border_c};">
                        <div class="bot-header">
                            <span class="bot-title" style="color: {border_c};">{b.get('title', f'SWAP {lev}x')}</span>
                            {badge_html}
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">總可用淨值</span>
                            <span class="kv-val" style="font-size: 1.1rem; color: #f0f6fc;">${equity:,.2f} U</span>
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">初始本金 / 可用現金</span>
                            <span class="kv-val">${init_cap:,.0f} U / ${avail:,.2f} U</span>
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">累計總回報 (ROE)</span>
                            <span class="kv-val {ret_class}">{ret_sign}{bot_ret:.2f}% ({ret_sign}${equity - init_cap:+,.2f} U)</span>
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">目前持倉數量</span>
                            <span class="kv-val">{qty:.5f} BTC</span>
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">持倉均價 / 浮動盈虧</span>
                            <span class="kv-val">{f'${cost:,.1f}' if side != 'NONE' else '—'} ｜ {f'{upnl:+,.2f} U ({upnl_pct:+.2f}%)' if side != 'NONE' else '—'}</span>
                        </div>
                        <div class="kv-row">
                            <span class="kv-key">風控策略機制</span>
                            <span class="kv-val" style="font-size: 0.8rem; color: #8b949e;">{b.get('risk_desc', '移動停利 ｜ 原生硬止損')}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ================= Recent 5 Trade Journals =================
    st.markdown("### 📋 最近 5 筆戰果覆盤與出入場歸因")

    jm = TradeJournalManager(
        db_path=str(ROOT_DIR / "data" / "trade_journal_db.json"),
        journals_dir=str(ROOT_DIR / "journals"),
    )
    jm._load_db(merge=True)
    all_entries = jm.get_entries()

    # Filter closed trades sorted by exit_time reverse
    closed_trades = [e for e in all_entries if e.status == "CLOSED"]
    closed_trades.sort(key=lambda x: str(x.exit_time or ""), reverse=True)

    if not closed_trades:
        st.info("目前尚無平倉歷史紀錄。")
    else:
        table_rows = []
        for e in closed_trades[:5]:
            exit_t = format_to_taipei_time(e.exit_time)
            side_badge = "🟢 LONG" if e.side == "LONG" else "🔴 SHORT"
            pnl_c = "text-green" if e.pnl_usdt >= 0 else "text-red"
            pnl_str = f"{e.pnl_usdt:+,.2f} U ({e.pnl_pct:+.2f}%)"
            reason_str = e.review.exit_reason if hasattr(e, "review") and hasattr(e.review, "exit_reason") else "移動停利"
            # Strip prefix
            clean_reason = reason_str.replace("平倉原因：", "").split(" | ")[0]

            table_rows.append(
                f'<tr style="border-bottom: 1px solid #21262d; font-size: 0.9rem;">'
                f'<td style="padding: 10px 8px; color: #8b949e;">{exit_t}</td>'
                f'<td style="padding: 10px 8px; font-weight: 700; color: #58a6ff;">{e.symbol} ({e.leverage}x)</td>'
                f'<td style="padding: 10px 8px; font-weight: 700;">{side_badge}</td>'
                f'<td style="padding: 10px 8px; color: #c9d1d9;">${e.entry_price:,.1f} ➔ ${e.exit_price:,.1f}</td>'
                f'<td style="padding: 10px 8px; font-weight: 800;" class="{pnl_c}">{pnl_str}</td>'
                f'<td style="padding: 10px 8px; color: #8b949e;">{clean_reason}</td>'
                f'</tr>'
            )

        table_html = (
            f'<div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; overflow-x: auto;">'
            f'<table style="width: 100%; border-collapse: collapse; text-align: left;">'
            f'<thead>'
            f'<tr style="border-bottom: 2px solid #30363d; color: #8b949e; font-size: 0.85rem; text-transform: uppercase;">'
            f'<th style="padding: 8px;">平倉時間 (台北 UTC+8)</th>'
            f'<th style="padding: 8px;">合約規格</th>'
            f'<th style="padding: 8px;">方向</th>'
            f'<th style="padding: 8px;">開倉 ➔ 平倉</th>'
            f'<th style="padding: 8px;">淨盈虧 (USDT / ROE)</th>'
            f'<th style="padding: 8px;">出場歸因摘要</th>'
            f'</tr>'
            f'</thead>'
            f'<tbody>{"".join(table_rows)}</tbody>'
            f'</table>'
            f'</div>'
        )
        st.html(table_html)

    # Footer
    st.markdown(
        """
        <div style="text-align: center; color: #484f58; font-size: 0.8rem; margin-top: 30px; padding: 10px;">
            Crypto AI Quantitative Trading Platform ｜ 雲端純讀取高頻儀表板 ｜ 零按鈕物理防護
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    render_live_wallboard()


if __name__ == "__main__":
    main()
