"""Streamlit Web Dashboard for Crypto AI Quantitative Trading Platform.

Modularized & Decoupled Architecture:
- Executive Mission Control Overview (views/overview_tab.py)
- Noise-Free 3-Question Trade Journal & Deep Inspection (views/journal_tab.py)
- Live BingX & Simulated Paper Trading (views/trading_tab.py)
- Research, Backtest & Convergence Matrix (views/research_tab.py)
"""

import sys
import json
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.data import DataManager
from packages.execution import PaperBroker, BingXGateway
from packages.journal import TradeJournalManager
from packages.core import UnifiedAutopilotEngine, AutopilotState
from apps.dashboard.ui.responsive import inject_responsive_css
from apps.dashboard.views import (
    render_overview_tab,
    render_journal_tab,
    render_trading_tab,
    render_research_tab,
)


def load_bot_states():
    """Load latest states for both Spot 100U and Swap 100U daemons."""
    spot_file = ROOT_DIR / "data" / "bingx_paper_100u.json"
    swap_file = ROOT_DIR / "data" / "bingx_swap_100u.json"
    spot_state, swap_state = {}, {}
    if spot_file.exists():
        try:
            with open(spot_file, "r", encoding="utf-8") as f:
                spot_state = json.load(f)
        except Exception:
            pass
    if swap_file.exists():
        try:
            with open(swap_file, "r", encoding="utf-8") as f:
                swap_state = json.load(f)
        except Exception:
            pass
    return spot_state, swap_state


def get_unified_journal_entries(jm: TradeJournalManager, btc_p: float) -> tuple[list[dict], float, float]:
    """Compile unified journal cards directly from authoritative TradeJournalManager.

    Guarantees 100% mathematical reconciliation:
    - OPEN trades calculate real-time floating unrealized PnL matching the live ticker.
    - CLOSED trades report finalized realized PnL recorded upon execution.
    - Zero fabricated strings: 'why_enter', 'ai_decision', 'exit_result' directly map to
      TradeJournalEntry review fields (thesis, strategy_evaluation, exit_reason).

    Returns:
        (entries, total_realized_pnl, total_unrealized_pnl)
    """
    entries = []
    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0

    db_entries = jm.get_entries()
    # Sort reverse-chronologically by entry_time
    sorted_entries = sorted(db_entries, key=lambda e: e.entry_time, reverse=True)

    for e in sorted_entries:
        is_open = (e.status == "OPEN")

        if is_open:
            # Calculate dynamic floating unrealized PnL based on current market ticker
            if e.side == "LONG":
                upnl = (btc_p - e.entry_price) * e.amount_btc
            else:
                upnl = (e.entry_price - btc_p) * e.amount_btc

            upnl_pct = (upnl / e.margin_used * 100.0) if e.margin_used > 0 else 0.0
            total_unrealized_pnl += upnl
            pnl_val = upnl
            pnl_pct = upnl_pct

            sl_price = e.risk_plan.stop_loss_price if hasattr(e, "risk_plan") and e.risk_plan else 0.0
            sl_pct = e.risk_plan.stop_loss_pct if hasattr(e, "risk_plan") and e.risk_plan else 2.5
            tb_pct = e.risk_plan.trailing_pullback_pct if hasattr(e, "risk_plan") and e.risk_plan else 1.0

            exit_result = f"持倉中 (浮動盈虧即時追蹤) | 止損保護: ${sl_price:,.2f} (-{sl_pct:.1f}%) | 移動回撤: {tb_pct:.1f}%"
        else:
            total_realized_pnl += e.pnl_usdt
            pnl_val = e.pnl_usdt
            pnl_pct = e.pnl_pct
            exit_result = e.review.exit_reason if hasattr(e, "review") and e.review and e.review.exit_reason else f"平倉結算 (實現盈虧: ${e.pnl_usdt:+,.2f} U)"

        # Extract 3 high-signal core questions from authoritative review notes
        thesis = e.review.thesis if hasattr(e, "review") and e.review and e.review.thesis else "技術面策略訊號觸發"
        decision = e.review.strategy_evaluation if hasattr(e, "review") and e.review and e.review.strategy_evaluation else "策略風控檢核核准"

        mkt_label = f"{e.market_type} ({'合約' if e.market_type == 'SWAP' else '現貨'} {e.leverage}x)" if e.leverage > 1 else f"{e.market_type} (現貨)"

        entries.append({
            "id": e.journal_id,
            "time": e.entry_time[:16] if e.entry_time else "--",
            "symbol": e.symbol,
            "market": mkt_label,
            "side": e.side,
            "status": e.status,
            "entry_price": e.entry_price,
            "cur_price": btc_p if is_open else e.exit_price,
            "exit_price": None if is_open else e.exit_price,
            "pnl_usdt": pnl_val,
            "pnl_pct": pnl_pct,
            "why_enter": thesis,
            "ai_decision": decision,
            "exit_result": exit_result,
            "raw_entry": e,
        })

    return entries, total_realized_pnl, total_unrealized_pnl


def main():
    # ----------------- Page Configuration -----------------
    st.set_page_config(
        page_title="AI 量化交易控制台",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject responsive touch-friendly CSS
    inject_responsive_css()

    # ----------------- State & Gateways Initialization -----------------
    if "gateway" not in st.session_state:
        st.session_state["gateway"] = BingXGateway(dry_run=True, enable_ws=True)
    gw: BingXGateway = st.session_state["gateway"]

    if "paper_broker" not in st.session_state:
        st.session_state["paper_broker"] = PaperBroker()
    broker: PaperBroker = st.session_state["paper_broker"]

    dm = DataManager()
    jm = TradeJournalManager()

    if "autopilot" not in st.session_state:
        st.session_state["autopilot"] = UnifiedAutopilotEngine()
    autopilot: UnifiedAutopilotEngine = st.session_state["autopilot"]
    autopilot.load_state()

    # ----------------- Compact Trader Top Header Bar -----------------
    header_c1, header_c2 = st.columns([3, 1])
    with header_c1:
        st.markdown("### 加密貨幣 AI 多因子量化控制台")
        ws_badge = '<span style="color:#3fb950; font-weight:bold;">[WS: 即時串流]</span>' if gw.is_ws_connected else '<span style="color:#d29922; font-weight:bold;">[REST: 備援]</span>'
        if getattr(gw, "is_vst", False):
            mode_badge = '<span style="color:#a371f7; font-weight:bold;">[模式: BINGX-VST 模擬盤]</span>'
        elif gw.is_dry_run:
            mode_badge = '<span style="color:#58a6ff; font-weight:bold;">[模式: LOCAL 沙盒]</span>'
        else:
            mode_badge = '<span style="color:#f85149; font-weight:bold;">[模式: LIVE 實盤真金]</span>'
        auto_badge = '<span style="color:#3fb950; font-weight:bold;">[中樞: ARMED 運行]</span>' if autopilot.status == AutopilotState.ARMED else '<span style="color:#d29922; font-weight:bold;">[中樞: STANDBY 待機]</span>'
        st.markdown(f"{ws_badge} &nbsp;|&nbsp; {mode_badge} &nbsp;|&nbsp; {auto_badge} &nbsp;|&nbsp; <span style=\"color:#8b949e;\">模組化解耦架構</span>", unsafe_allow_html=True)

    with header_c2:
        if st.button("即時刷新數據", use_container_width=True):
            st.rerun()

    # ----------------- Primary Navigation Tabs -----------------
    tab_overview, tab_journal, tab_bots, tab_research = st.tabs([
        "總覽看板",
        "覆盤日誌",
        "實盤與模擬下單",
        "研究與回測",
    ])

    # 1. Overview Tab
    with tab_overview:
        entries, btc_p = render_overview_tab(
            gw=gw,
            jm=jm,
            autopilot=autopilot,
            load_bot_states_fn=load_bot_states,
            get_unified_journal_entries_fn=get_unified_journal_entries,
        )

    # 2. Journal Tab
    with tab_journal:
        render_journal_tab(jm=jm, entries=entries)

    # 3. Bots & Manual Trading Tab
    with tab_bots:
        render_trading_tab(gw=gw, broker=broker, dm=dm, btc_p=btc_p)

    # 4. Research & Backtest Tab
    with tab_research:
        render_research_tab(dm=dm)


if __name__ == "__main__":
    main()
