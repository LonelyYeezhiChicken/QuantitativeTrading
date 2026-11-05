"""Lightweight in-process cron runner for daily & weekly quantitative reports.

Designed for Docker / Linux VPS deployments where external cron daemon is not desired.
Monitors Asia/Taipei timezone and executes:
- Daily Morning Report: 08:00 AM
- Daily Evening Report: 18:00 PM
- Weekly Monday Report: 08:00 AM (Monday)
"""

from datetime import datetime, timezone, timedelta
import logging
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("CronRunner")

TZ_TAIPEI = timezone(timedelta(hours=8))
ROOT_DIR = Path(__file__).resolve().parent.parent


def run_report(args: list[str]) -> bool:
    """Execute report generator script via Python subprocess."""
    cmd = [sys.executable, str(ROOT_DIR / "apps" / "cli" / "generate_report.py")] + args
    logger.info(f"Triggering scheduled report: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, encoding="utf-8", check=False)
        if res.returncode == 0:
            logger.info("Scheduled report generated successfully.")
            return True
        else:
            logger.error(f"Report generation exited with code {res.returncode}:\n{res.stderr}")
            return False
    except Exception as exc:
        logger.error(f"Failed to execute report generator: {exc}")
        return False


def main():
    logger.info("Starting Quant Report Cron Runner (Timezone: Asia/Taipei)...")
    last_triggered_date = ""
    last_triggered_session = ""
    last_triggered_weekly = ""

    while True:
        try:
            now = datetime.now(TZ_TAIPEI)
            date_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # 1. 08:00 AM Morning Report
            if hour == 8 and minute == 0:
                if last_triggered_date != date_str or last_triggered_session != "AM":
                    logger.info("Executing 08:00 AM Daily Morning Report...")
                    run_report(["--type", "daily", "--session", "AM"])
                    last_triggered_date = date_str
                    last_triggered_session = "AM"

                    # Monday 08:00 Weekly Report
                    if now.weekday() == 0 and last_triggered_weekly != date_str:
                        logger.info("Executing Monday 08:00 Weekly Report...")
                        run_report(["--type", "weekly"])
                        last_triggered_weekly = date_str

            # 2. 18:00 PM Evening Report
            elif hour == 18 and minute == 0:
                if last_triggered_date != date_str or last_triggered_session != "PM":
                    logger.info("Executing 18:00 PM Daily Evening Report...")
                    run_report(["--type", "daily", "--session", "PM"])
                    last_triggered_date = date_str
                    last_triggered_session = "PM"

            time.sleep(15)
        except KeyboardInterrupt:
            logger.info("Cron runner stopped by user.")
            break
        except Exception as exc:
            logger.error(f"Cron loop unexpected error: {exc}")
            time.sleep(30)


if __name__ == "__main__":
    main()
