"""Unit and Integration Tests for Container Internal Healthcheck Probes.

Verifies:
1. Non-blocking atomic heartbeat generation and serialization.
2. Fresh heartbeat verification (healthy status).
3. Stale heartbeat detection (frozen/zombie process identification).
4. Missing, corrupt, or invalid heartbeat handling.
5. HTTP health probe verification for dashboard endpoint.
6. CLI healthcheck script exit code behavior (0 for healthy, 1 for unhealthy).
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from packages.core.heartbeat import (
    check_heartbeat,
    get_heartbeat_path,
    record_heartbeat,
)
from scripts.healthcheck import check_http_endpoint


class TestHeartbeatModule:
    """Test core heartbeat recording and verification logic."""

    def test_record_and_check_heartbeat_healthy(self, tmp_path: Path):
        """A freshly recorded heartbeat must be detected as healthy."""
        bot_name = "test_bot_3x"
        hb_file = record_heartbeat(
            name=bot_name,
            metadata={"loop": 10, "symbol": "BTC/USDT"},
            root_dir=tmp_path,
        )

        assert hb_file.exists()
        assert hb_file.name == ".heartbeat_test_bot_3x.json"

        # Verify contents
        with open(hb_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["bot_id"] == bot_name
        assert data["status"] == "ALIVE"
        assert data["pid"] == os.getpid()
        assert data["metadata"]["loop"] == 10
        assert "timestamp" in data

        # Check freshness
        is_healthy, msg, parsed = check_heartbeat(bot_name, max_stale_sec=60.0, root_dir=tmp_path)
        assert is_healthy is True
        assert "正常運作中" in msg
        assert parsed["bot_id"] == bot_name

    def test_check_heartbeat_stale_detected(self, tmp_path: Path):
        """A heartbeat older than max_stale_sec must be reported as unhealthy (frozen)."""
        bot_name = "frozen_bot"
        hb_file = get_heartbeat_path(bot_name, root_dir=tmp_path)
        hb_file.parent.mkdir(parents=True, exist_ok=True)

        stale_time = time.time() - 300.0  # 5 minutes ago
        with open(hb_file, "w", encoding="utf-8") as f:
            json.dump({
                "bot_id": bot_name,
                "pid": 99999,
                "timestamp": stale_time,
                "status": "ALIVE",
            }, f)

        is_healthy, msg, _ = check_heartbeat(bot_name, max_stale_sec=120.0, root_dir=tmp_path)
        assert is_healthy is False
        assert "可能卡死或停滯" in msg

    def test_check_heartbeat_missing_file(self, tmp_path: Path):
        """Missing heartbeat file must report unhealthy without raising exceptions."""
        is_healthy, msg, _ = check_heartbeat("non_existent_bot", root_dir=tmp_path)
        assert is_healthy is False
        assert "心跳檔案不存在" in msg

    def test_check_heartbeat_corrupt_json(self, tmp_path: Path):
        """Corrupt/truncated heartbeat file must report unhealthy cleanly."""
        bot_name = "corrupt_bot"
        hb_file = get_heartbeat_path(bot_name, root_dir=tmp_path)
        hb_file.parent.mkdir(parents=True, exist_ok=True)
        hb_file.write_text("{invalid_json: true", encoding="utf-8")

        is_healthy, msg, _ = check_heartbeat(bot_name, root_dir=tmp_path)
        assert is_healthy is False
        assert "心跳檔案解析失敗" in msg

    def test_check_heartbeat_missing_timestamp(self, tmp_path: Path):
        """JSON missing timestamp field must report unhealthy."""
        bot_name = "notimestamp_bot"
        hb_file = get_heartbeat_path(bot_name, root_dir=tmp_path)
        hb_file.parent.mkdir(parents=True, exist_ok=True)
        hb_file.write_text(json.dumps({"bot_id": bot_name}), encoding="utf-8")

        is_healthy, msg, _ = check_heartbeat(bot_name, root_dir=tmp_path)
        assert is_healthy is False
        assert "缺少 timestamp" in msg


class TestHttpProbe:
    """Test HTTP health probe for dashboard endpoint."""

    @patch("urllib.request.urlopen")
    def test_http_endpoint_success(self, mock_urlopen):
        """HTTP 200 responses must be detected as healthy."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_http_endpoint("http://localhost:8501/_stcore/health")
        assert result is True

    @patch("urllib.request.urlopen")
    def test_http_endpoint_500_error(self, mock_urlopen):
        """HTTP 500 error must be detected as unhealthy."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 500
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = check_http_endpoint("http://localhost:8501/_stcore/health")
        assert result is False

    @patch("urllib.request.urlopen")
    def test_http_endpoint_connection_refused(self, mock_urlopen):
        """Connection refused must be caught and reported as unhealthy."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = check_http_endpoint("http://localhost:8501/_stcore/health")
        assert result is False


class TestHealthcheckCli:
    """Test CLI invocation of scripts/healthcheck.py."""

    def test_cli_healthy_exit_code_0(self, tmp_path: Path):
        """CLI must exit with code 0 for healthy heartbeats."""
        bot_name = "cli_bot_active"
        record_heartbeat(bot_name, root_dir=tmp_path)

        # Run script with custom PYTHONPATH and tmp_path
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "healthcheck.py"
        cmd = [
            sys.executable,
            str(script_path),
            "--target",
            bot_name,
            "--max-stale",
            "60",
        ]
        # Monkeypatch ROOT_DIR inside subprocess via script or test against default root
        default_root = Path(__file__).resolve().parent.parent
        record_heartbeat(bot_name, root_dir=default_root)
        try:
            res = subprocess.run(
                cmd,
                cwd=str(default_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert res.returncode == 0
            assert "[HEALTHY]" in res.stdout
        finally:
            hb = get_heartbeat_path(bot_name, root_dir=default_root)
            if hb.exists():
                hb.unlink()

    def test_cli_unhealthy_exit_code_1_for_missing(self):
        """CLI must exit with code 1 for missing heartbeats."""
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "healthcheck.py"
        default_root = Path(__file__).resolve().parent.parent
        cmd = [
            sys.executable,
            str(script_path),
            "--target",
            "completely_ghost_bot_999",
            "--max-stale",
            "30",
        ]
        res = subprocess.run(
            cmd,
            cwd=str(default_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert res.returncode == 1
        assert "[UNHEALTHY]" in res.stdout or "[UNHEALTHY]" in res.stderr
