"""Lightweight in-process cron runner for daily & weekly quantitative reports.

Designed for Docker / Linux VPS deployments where external cron daemon is not desired.
Monitors Asia/Taipei timezone and executes:
- Daily Morning Report: 08:00 AM
- Daily Evening Report: 18:00 PM
- Weekly Monday Report: 08:00 AM (Monday)
"""

from datetime import datetime, timezone, timedelta
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TZ_TAIPEI = timezone(timedelta(hours=8))
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from packages.core.heartbeat import record_heartbeat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("CronRunner")


def _mask_secret(text: str, secret: str) -> str:
    if not text or not secret:
        return text or ""
    return text.replace(secret, "***")


def sync_journals_to_git(session_label: str, root_dir: Path = ROOT_DIR) -> bool:
    """Automatically commit and push `data/trade_journal_db.json` and `journals/` to GitHub.

    Safely handles headless VPS / Docker environments using GITHUB_TOKEN without exposing secrets.
    """
    if not shutil.which("git"):
        logger.warning("[Git Auto-Backup] git executable not found, skipping backup.")
        return False

    git_dir = root_dir / ".git"
    if not git_dir.exists():
        logger.info("[Git Auto-Backup] .git directory not present in container/workspace, skipping backup.")
        return False

    target_paths = ["data/trade_journal_db.json", "journals"]
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    repo = (os.getenv("GITHUB_REPOSITORY") or "LonelyYeezhiChicken/QuantitativeTrading").strip()
    branch = (os.getenv("GIT_BACKUP_BRANCH") or "main").strip()

    try:
        # 1. Ensure safe.directory for container UID compatibility
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", str(root_dir)],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        # 2. Check if there are any changes in trade_journal_db.json or journals/
        status_res = subprocess.run(
            ["git", "status", "--porcelain", "--"] + target_paths,
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        if status_res.returncode != 0:
            logger.warning(f"[Git Auto-Backup] git status failed: {_mask_secret(status_res.stderr, token)}")
            return False

        if not status_res.stdout.strip():
            logger.info("[Git Auto-Backup] No changes in journals or trade_journal_db.json, nothing to commit.")
            return True

        # 3. Stage only journal files
        add_res = subprocess.run(
            ["git", "add", "--"] + target_paths,
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        if add_res.returncode != 0:
            logger.warning(f"[Git Auto-Backup] git add failed: {_mask_secret(add_res.stderr, token)}")
            return False

        # 4. Commit with explicit bot author identity
        commit_msg = f"chore(journal): auto-backup trade journals and reports ({session_label})"
        commit_res = subprocess.run(
            [
                "git",
                "-c",
                "user.name=Quant Reporter Bot",
                "-c",
                "user.email=quant-bot@users.noreply.github.com",
                "commit",
                "-m",
                commit_msg,
                "--",
            ]
            + target_paths,
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        if commit_res.returncode != 0 and "nothing to commit" not in (commit_res.stdout + commit_res.stderr).lower():
            logger.warning(f"[Git Auto-Backup] git commit failed: {_mask_secret(commit_res.stderr, token)}")
            return False

        # 5. Push to remote (use token URL if available for headless VPS compatibility)
        if token and repo:
            remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
            push_cmd = ["git", "push", remote_url, f"HEAD:{branch}"]
        else:
            push_cmd = ["git", "push", "origin", f"HEAD:{branch}"]

        push_res = subprocess.run(
            push_cmd,
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if push_res.returncode == 0:
            logger.info(f"[Git Auto-Backup] Successfully backed up journals to GitHub ({repo}@{branch}).")
            return True
        else:
            logger.error(f"[Git Auto-Backup] git push failed: {_mask_secret(push_res.stderr, token)}")
            return False
    except Exception as exc:
        logger.error(f"[Git Auto-Backup] Unexpected error: {_mask_secret(str(exc), token)}")
        return False


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

                    sync_journals_to_git(f"{date_str}_AM")

            # 2. 18:00 PM Evening Report
            elif hour == 18 and minute == 0:
                if last_triggered_date != date_str or last_triggered_session != "PM":
                    logger.info("Executing 18:00 PM Daily Evening Report...")
                    run_report(["--type", "daily", "--session", "PM"])
                    last_triggered_date = date_str
                    last_triggered_session = "PM"
                    sync_journals_to_git(f"{date_str}_PM")

            # Record healthcheck heartbeat for container probe
            record_heartbeat("reporter", metadata={"now_tp": str(now)})

            time.sleep(15)
        except KeyboardInterrupt:
            logger.info("Cron runner stopped by user.")
            break
        except Exception as exc:
            logger.error(f"Cron loop unexpected error: {exc}")
            time.sleep(30)


if __name__ == "__main__":
    main()
