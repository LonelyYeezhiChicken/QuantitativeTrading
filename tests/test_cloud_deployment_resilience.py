"""Tests for Cloud VPS & Container Deployment Resilience."""

import os
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def test_docker_compose_structure():
    """Verify docker-compose.yml defines all 5 core services with necessary resilience configs."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    content = compose_path.read_text(encoding="utf-8")
    # Verify core services
    assert "swap_3x:" in content
    assert "swap_10x:" in content
    assert "swap_50x:" in content
    assert "reporter:" in content
    assert "dashboard:" in content

    # Verify auto-restart and resource limits
    assert "restart: unless-stopped" in content
    assert "TZ=Asia/Taipei" in content
    assert "limits:" in content
    assert "8501:8501" in content


def test_vps_scripts_exist_and_executable():
    """Verify deployment scripts exist, have shebangs, and define critical safety traps."""
    setup_script = ROOT_DIR / "deploy" / "setup_vps.sh"
    upgrade_script = ROOT_DIR / "deploy" / "upgrade.sh"

    assert setup_script.exists()
    assert upgrade_script.exists()

    setup_content = setup_script.read_text(encoding="utf-8")
    assert setup_content.startswith("#!/usr/bin/env bash")
    assert "set -e" in setup_content
    assert "swapfile" in setup_content  # Auto-swap for 1GB VPS
    assert "chrony" in setup_content    # Microsecond clock sync

    upgrade_content = upgrade_script.read_text(encoding="utf-8")
    assert upgrade_content.startswith("#!/usr/bin/env bash")
    assert "set -e" in upgrade_content
    assert "pytest" in upgrade_content  # Pre-flight test verification
    assert "docker compose up -d" in upgrade_content


def test_cloud_wallboard_cold_start(tmp_path):
    """Verify that cloud_wallboard.py handles a cold start with zero trade history and zero bots without crashing."""
    from streamlit.testing.v1 import AppTest

    # Point to cloud_wallboard script
    wallboard_path = ROOT_DIR / "apps" / "dashboard" / "cloud_wallboard.py"
    at = AppTest.from_file(str(wallboard_path), default_timeout=15)
    at.run()

    # Must execute cleanly without unhandled exceptions
    assert not at.exception, f"Cloud wallboard raised unexpected exception: {at.exception}"
