"""Bot State Repository: Isolated Domain Repository for Bot Instance States & Discovery."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class BotStateRepository:
    """Authoritative repository to discover and query persistent trading bot states."""

    @staticmethod
    def discover_active_bots(btc_p: float, root_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Scan data/ directory dynamically for all active bot state files (SPOT, SWAP 3x, 10x, 50x, etc.)."""
        base_dir = root_dir or ROOT_DIR
        instances: List[Dict[str, Any]] = []
        data_dir = base_dir / "data"
        if not data_dir.exists():
            return instances

        # 1. Spot bots (bingx_paper_*.json)
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
                    "stop_flag": data_dir / "bot_stop.flag",
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

                if lev <= 3:
                    b_color = "#a371f7"
                    t_label = f"永續合約守護 (SWAP {lev}x)"
                    risk_info = f"動態追蹤停利 (回撤 1.0%) | 原生硬止損 (-{4.0 if lev<=3 else 15.0}% 雲端守護)"
                elif lev <= 10:
                    b_color = "#f0883e"
                    t_label = f"高槓桿合約 (SWAP {lev}x)"
                    risk_info = "價格停損 (-1.5%) | 目標停利 (+20.0% ROE) | 雲端原生硬停損"
                else:
                    b_color = "#f85149"
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
                    "stop_flag": data_dir / stop_flag_name,
                    "stop_btn_label": f"安全停止 {lev}x 進程",
                })
            except Exception:
                pass

        # 3. Autopilot bots (autopilot_*.json)
        for f in sorted(data_dir.glob("autopilot_*.json")):
            if "journal" in f.name or f.name.endswith(".control.json"):
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    st_data = json.load(fp)
                pos = st_data.get("position", {})
                side = pos.get("side", "NONE")
                qty = pos.get("amount", pos.get("amount_btc", 0.0))
                cost = pos.get("entry_price", btc_p)
                margin = pos.get("margin_used", 50.0)
                avail = st_data.get("cash", 50.0)
                init_cap = st_data.get("capital", 100.0)
                lev = st_data.get("leverage", 10)
                m_mode = st_data.get("mode", "SWAP_10X")
                is_swap = "SWAP" in m_mode
                liq_p = cost * (1.0 - (0.9 / lev)) if (is_swap and side == "LONG") else (cost * (1.0 + (0.9 / lev)) if is_swap and side == "SHORT" else 0.0)

                if side == "LONG":
                    upnl = (btc_p - cost) * qty
                elif side == "SHORT":
                    upnl = (cost - btc_p) * qty
                else:
                    upnl = 0.0
                equity = avail + (margin if side != "NONE" else 0.0) + upnl
                upnl_pct = (upnl / margin * 100.0) if (margin > 0 and side != "NONE") else 0.0

                if not is_swap:
                    b_color = "#58a6ff"
                    t_label = "全自動現貨中樞 (SPOT 1x)"
                    risk_info = "動態回踩動量 | 原生硬止損 (-2.0%)"
                elif lev <= 3:
                    b_color = "#a371f7"
                    t_label = f"全自動合約中樞 (SWAP {lev}x)"
                    risk_info = "多體制順勢突破 | 移動停利 | 雲端原生硬停損"
                else:
                    b_color = "#f0883e" if lev <= 10 else "#f85149"
                    t_label = f"全自動高槓桿中樞 (SWAP {lev}x)"
                    risk_info = f"自適應槓桿停損 (-{round(15.0/lev, 2)}%) | 移動鎖利 | 雲端原生硬停損"

                instances.append({
                    "id": f.stem,
                    "file": f,
                    "title": t_label,
                    "short_title": f"AUTO {lev}x",
                    "market_type": "SWAP" if is_swap else "SPOT",
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
                    "stop_flag": data_dir / "autopilot_stop.flag",
                    "control_file": f.with_suffix(".control.json"),
                    "status": st_data.get("status", "STANDBY"),
                    "stop_btn_label": f"切換待機 ({lev}x)" if st_data.get("status") == "ARMED" else f"啟動操盤 ({lev}x)",
                })
            except Exception:
                pass

        instances.sort(key=lambda b: (0 if b.get("market_type") == "SPOT" else 1, int(b.get("leverage", 1)), str(b.get("id", ""))))
        return instances
