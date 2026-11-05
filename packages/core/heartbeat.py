"""Container and Process Heartbeat Tracking Module.

Provides non-blocking, atomic heartbeat tracking and freshness verification
for long-running quantitative trading engines, scheduled cron runners, and microservices.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("HeartbeatTracker")
DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_heartbeat_path(name: str, root_dir: Optional[Path] = None) -> Path:
    """Return the canonical path for a process heartbeat file."""
    base = root_dir or DEFAULT_ROOT
    clean_name = name.strip().replace("/", "_").replace("\\", "_").replace(" ", "_")
    return base / "data" / f".heartbeat_{clean_name}.json"


def record_heartbeat(
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    root_dir: Optional[Path] = None,
) -> Path:
    """Atomically record process heartbeat to disk."""
    hb_file = get_heartbeat_path(name, root_dir=root_dir)
    hb_file.parent.mkdir(parents=True, exist_ok=True)

    now_ts = time.time()
    payload = {
        "bot_id": name,
        "pid": os.getpid(),
        "timestamp": now_ts,
        "iso_time": datetime.now(timezone.utc).isoformat(),
        "status": "ALIVE",
        "metadata": metadata or {},
    }

    # Atomic write pattern to avoid readers observing torn/empty writes
    tmp_file = hb_file.with_name(f"{hb_file.name}.{os.getpid()}.tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, hb_file)
    except Exception as exc:
        logger.warning(f"Failed to atomically write heartbeat for {name}: {exc}")
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        # Fallback direct write
        try:
            with open(hb_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return hb_file


def check_heartbeat(
    name: str,
    max_stale_sec: float = 180.0,
    root_dir: Optional[Path] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Verify if the targeted process has updated its heartbeat within the allowed threshold.

    Returns:
        (is_healthy, reason_message, parsed_data)
    """
    hb_file = get_heartbeat_path(name, root_dir=root_dir)
    if not hb_file.exists():
        return False, f"心跳檔案不存在: {hb_file.name}", {}

    try:
        with open(hb_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return False, f"心跳檔案解析失敗 ({exc})", {}

    if not isinstance(data, dict):
        return False, "心跳內容格式不正確 (非 JSON 字典)", {}

    hb_ts = data.get("timestamp")
    if hb_ts is None:
        return False, "心跳資料缺少 timestamp 欄位", data

    try:
        hb_ts = float(hb_ts)
    except (ValueError, TypeError):
        return False, f"無效的時間戳格式: {hb_ts}", data

    now_ts = time.time()
    age = now_ts - hb_ts

    if age < -5.0:
        # Time machine warning (clock desynchronization)
        return True, f"時間同步警告：心跳時間戳超前本機 {abs(age):.1f} 秒", data

    if age > max_stale_sec:
        return False, f"程式可能卡死或停滯！距上次心跳已逾 {age:.1f} 秒 (安全門檻: {max_stale_sec:.1f} 秒)", data

    return True, f"正常運作中 (距上次心跳 {age:.1f} 秒)", data
