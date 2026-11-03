"""Responsive UI Components and CSS Styling for Tablet and Desktop Quantitative Dashboard."""

import streamlit as st
from typing import Dict, Any, Optional


def inject_responsive_css():
    """Inject responsive CSS tailored for Tablet (iPad/Android) and Desktop screens."""
    css = """
    <style>
        /* Modern Dark Financial Typography & Background */
        .stApp {
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        /* Tablet & Desktop Touch Targets (Minimum 48px height for touch accessibility) */
        button, .stButton > button {
            min-height: 48px !important;
            font-size: 15px !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
            padding: 10px 18px !important;
            transition: all 0.2s ease !important;
        }

        /* Large touch-friendly Tab Bar */
        div[data-baseweb="tab-list"] {
            gap: 8px !important;
            background-color: #161b22 !important;
            padding: 6px !important;
            border-radius: 12px !important;
            border: 1px solid #30363d !important;
            margin-bottom: 20px !important;
        }

        button[data-baseweb="tab"] {
            min-height: 46px !important;
            font-size: 15px !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
            padding: 10px 20px !important;
            color: #8b949e !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            background-color: #238636 !important;
            color: #ffffff !important;
        }

        /* Input Controls Touch Optimization */
        .stSelectbox div[data-baseweb="select"] > div {
            min-height: 46px !important;
            border-radius: 8px !important;
            font-size: 15px !important;
        }

        /* High-contrast Financial Card Style */
        .stat-card {
            background: linear-gradient(145deg, #161b22, #1c2128);
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 14px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
        }

        .stat-title {
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #8b949e;
            margin-bottom: 6px;
            font-weight: 600;
        }

        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: #f0f6fc;
            margin-bottom: 4px;
        }

        .stat-sub {
            font-size: 13px;
            color: #8b949e;
        }

        /* Color Utility Classes */
        .text-green { color: #3fb950 !important; }
        .text-red { color: #f85149 !important; }
        .text-gold { color: #e3b341 !important; }
        .text-cyan { color: #58a6ff !important; }

        /* Responsive Breakpoints: Tablet (iPad 768px - 1024px) */
        @media (max-width: 1024px) {
            /* Force Streamlit Columns to wrap gracefully into 2-column or 1-column layouts */
            div[data-testid="column"] {
                min-width: 47% !important;
                flex: 1 1 47% !important;
                margin-bottom: 12px !important;
            }

            .stat-value {
                font-size: 20px !important;
            }

            /* Expand container padding on touchscreens */
            .block-container {
                padding-top: 1.5rem !important;
                padding-bottom: 2rem !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
        }

        /* Mobile / Small Tablet (<= 768px) */
        @media (max-width: 768px) {
            div[data-testid="column"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }

            .stat-value {
                font-size: 22px !important;
            }
        }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_gold_macro_card(btc_price: float, xaut_price: float):
    """Render BTC/XAUT digital vs physical gold macro ratio card."""
    if xaut_price <= 0:
        ratio = 0.0
    else:
        ratio = btc_price / xaut_price

    html = f"""
    <div class="stat-card" style="border-left: 4px solid #e3b341;">
        <div class="stat-title text-gold">宏觀資產對沖指標：BTC / XAUT 比值</div>
        <div class="stat-value text-gold">1 BTC = {ratio:.2f} 盎司實體黃金</div>
        <div class="stat-sub">
            比特幣 (${btc_price:,.2f}) 相對於 泰達實體黃金代幣 (${xaut_price:,.2f}/oz)。<br>
            當比值走高代表加密資產強勢擴張；當比值回落代表實體黃金避險資金流入。
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_market_pulse_card(
    symbol: str,
    name: str,
    price: float,
    change_24h_pct: float,
    high_24h: float = 0.0,
    low_24h: float = 0.0,
    is_gold: bool = False,
    source: str = "WEBSOCKET",
):
    """Render clean, responsive market pulse card."""
    color_cls = "text-green" if change_24h_pct >= 0 else "text-red"
    border_color = "#e3b341" if is_gold else ("#3fb950" if change_24h_pct >= 0 else "#f85149")
    sign = "+" if change_24h_pct >= 0 else ""
    src_badge = "WS 即時" if source == "WEBSOCKET" else "REST"

    html = f"""
    <div class="stat-card" style="border-top: 3px solid {border_color};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span class="stat-title" style="margin: 0; font-size: 14px; font-weight: 700; color: #f0f6fc;">{symbol}</span>
            <span style="font-size: 11px; background: #21262d; padding: 2px 8px; border-radius: 6px; color: #8b949e;">{src_badge}</span>
        </div>
        <div style="font-size: 12px; color: #8b949e; margin-bottom: 8px;">{name}</div>
        <div class="stat-value">${price:,.2f}</div>
        <div style="display: flex; justify-content: space-between; font-size: 13px;">
            <span class="{color_cls}" style="font-weight: 600;">24h 漲跌: {sign}{change_24h_pct:.2f}%</span>
            <span style="color: #8b949e;">高: ${high_24h:,.1f} | 低: ${low_24h:,.1f}</span>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
