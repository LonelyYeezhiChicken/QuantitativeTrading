"""Unit Tests for Wallboard Active Position Focus & Repository Data Extraction.

Verifies:
1. BotStateRepository discovers and extracts rich position metadata:
   - margin_used
   - entry_time
   - entry_why
   - ai_decision
   - native_sl_price
   - cloud_sl_tier
2. Active position vs Flat position data integrity for dashboard rendering.
"""

import json
from pathlib import Path

import pytest

from packages.core.state_repository import BotStateRepository


class TestWallboardPositionData:
    """Test data extraction for Wallboard Active Position panel."""

    def test_discover_active_bots_extracts_rich_position_fields(self, tmp_path: Path):
        """Repository must extract entry_why, ai_decision, native_sl_price, and margin_used."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        bot_state = {
            "status": "ARMED",
            "mode": "SWAP_3X",
            "capital": 200.0,
            "cash": 50.0,
            "leverage": 3,
            "position": {
                "side": "LONG",
                "amount": 0.0056,
                "amount_btc": 0.0056,
                "entry_price": 80000.0,
                "margin_used": 150.0,
                "entry_time": "2026-11-05 09:19:08 UTC",
                "entry_why": "雙均線多頭排列強勢動能突破",
                "ai_decision": "Ollama EXECUTE: 核准開多",
                "native_sl_price": 78800.0,
                "cloud_sl_tier": 1,
                "highest_pnl_pct": 1.5,
            },
            "circuit_breaker_triggered": False,
        }

        state_file = data_dir / "autopilot_BTC_USDT_swap_3x_200u.json"
        state_file.write_text(json.dumps(bot_state), encoding="utf-8")

        # Discover with market price = 81000.0 (in profit)
        bots = BotStateRepository.discover_active_bots(btc_p=81000.0, root_dir=tmp_path)
        assert len(bots) == 1
        b = bots[0]

        # Verify rich position fields
        assert b["side"] == "LONG"
        assert b["cost"] == 80000.0
        assert b["margin_used"] == 150.0
        assert b["entry_why"] == "雙均線多頭排列強勢動能突破"
        assert b["ai_decision"] == "Ollama EXECUTE: 核准開多"
        assert b["native_sl_price"] == 78800.0
        assert b["cloud_sl_tier"] == 1
        assert b["highest_pnl_pct"] == 1.5
        assert b["entry_time"] == "2026-11-05 09:19:08 UTC"

        # Verify profit calculations
        # upnl = (81000 - 80000) * 0.0056 = 5.6 U
        assert pytest.approx(b["upnl"], rel=1e-3) == 5.6
        # upnl_pct = 5.6 / 150.0 * 100 = 3.73%
        assert pytest.approx(b["upnl_pct"], rel=1e-2) == 3.73
        # equity = cash (50) + margin (150) + upnl (5.6) = 205.6
        assert pytest.approx(b["equity"], rel=1e-3) == 205.6

    def test_discover_active_bots_flat_position_clean_defaults(self, tmp_path: Path):
        """Flat bots must have clean defaults without missing key exceptions."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        bot_state = {
            "status": "ARMED",
            "mode": "SWAP_10X",
            "capital": 200.0,
            "cash": 200.0,
            "leverage": 10,
            "position": {
                "side": "NONE",
                "amount": 0.0,
                "entry_price": 0.0,
            },
            "circuit_breaker_triggered": False,
        }

        state_file = data_dir / "autopilot_BTC_USDT_swap_10x_200u.json"
        state_file.write_text(json.dumps(bot_state), encoding="utf-8")

        bots = BotStateRepository.discover_active_bots(btc_p=81000.0, root_dir=tmp_path)
        assert len(bots) == 1
        b = bots[0]

        assert b["side"] == "NONE"
        assert b["margin_used"] == 0.0
        assert b["upnl"] == 0.0
        assert b["native_sl_price"] == 0.0
        assert b["entry_why"] == ""
