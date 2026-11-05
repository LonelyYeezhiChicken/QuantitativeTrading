#!/usr/bin/env python3
"""Unified Healthcheck Probe CLI for Quantitative Trading Containers.

Used by Docker compose HEALTHCHECK commands to detect zombie/frozen processes,
unresponsive HTTP servers, or stalled heartbeat files.

Exit Codes:
  0: HEALTHY (Normal execution)
  1: UNHEALTHY (Stalled, crashed, unresponsive, or invalid state)
"""

import argparse
import logging
from pathlib import Path
import sys
import urllib.error
import urllib.request

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from packages.core.heartbeat import check_heartbeat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("HealthcheckProbe")


def check_http_endpoint(url: str, timeout: float = 5.0) -> bool:
    """Perform non-blocking HTTP health check."""
    logger.info(f"Checking HTTP endpoint: {url} (timeout: {timeout}s)")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Quant-Healthcheck-Probe/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 300:
                logger.info(f"[HEALTHY] Endpoint responded with HTTP {code}")
                return True
            else:
                logger.error(f"[UNHEALTHY] Endpoint responded with HTTP {code}")
                return False
    except urllib.error.HTTPError as exc:
        logger.error(f"[UNHEALTHY] HTTP Error {exc.code}: {exc.reason}")
        return False
    except urllib.error.URLError as exc:
        logger.error(f"[UNHEALTHY] Connection failed: {exc.reason}")
        return False
    except Exception as exc:
        logger.error(f"[UNHEALTHY] Unexpected error while querying {url}: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Container Internal Healthcheck Probe")
    parser.add_argument(
        "--target",
        type=str,
        default="",
        help="Target service name (e.g. swap_3x, swap_10x, swap_50x, reporter, dashboard)",
    )
    parser.add_argument(
        "--max-stale",
        type=float,
        default=180.0,
        help="Max allowed stale seconds since last heartbeat (default: 180s)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="",
        help="Optional HTTP URL for dashboard/web health checks (e.g. http://localhost:8501/_stcore/health)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP request timeout in seconds (default: 5.0s)",
    )
    args = parser.parse_args()

    target = args.target.strip()
    url = args.url.strip()

    if not target and not url:
        logger.error("[ERROR] Either --target or --url must be specified.")
        sys.exit(1)

    # 1. HTTP Probe Mode (Dashboard or explicit URL)
    if target == "dashboard" or url:
        check_url = url or "http://localhost:8501/_stcore/health"
        is_ok = check_http_endpoint(check_url, timeout=args.timeout)
        sys.exit(0 if is_ok else 1)

    # 2. Heartbeat File Probe Mode (swap_3x, swap_10x, swap_50x, reporter)
    is_healthy, msg, data = check_heartbeat(
        name=target,
        max_stale_sec=args.max_stale,
        root_dir=ROOT_DIR,
    )

    if is_healthy:
        logger.info(f"[HEALTHY] [{target}] {msg} (pid: {data.get('pid', 'N/A')})")
        sys.exit(0)
    else:
        logger.error(f"[UNHEALTHY] [{target}] {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
