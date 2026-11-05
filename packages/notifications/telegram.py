"""Telegram Bot Outbound Push Client.

Uses standard Telegram Bot HTTP API (sendMessage).
Strictly outbound-only; never runs any inbound webhook or polling listener.
"""

import logging
import os
from typing import Optional
import requests

from packages.notifications.base import BaseNotifier

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    """Outbound Telegram Bot Notification Client."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "telegram"

    def is_enabled(self) -> bool:
        """True only if both Bot Token and Chat ID are configured."""
        return bool(self.token and self.chat_id)

    def send(self, message: str, title: Optional[str] = None) -> bool:
        """Send a message to the configured Telegram chat.

        Args:
            message: Message body.
            title: Optional title prepended in bold HTML.

        Returns:
            True if delivered successfully (HTTP 200 and ok=True), False otherwise.
        """
        if not self.is_enabled():
            logger.debug("TelegramNotifier is disabled (missing token or chat_id).")
            return False

        if not message.strip() and not (title and title.strip()):
            logger.warning("TelegramNotifier: empty message provided, skipping.")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Format HTML message
        if title and title.strip():
            formatted_text = f"<b>{title.strip()}</b>\n\n{message}"
        else:
            formatted_text = message

        payload = {
            "chat_id": self.chat_id,
            "text": formatted_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info("Telegram notification sent successfully.")
                    return True
                logger.warning("Telegram API error response: %s", data)
                return False

            # If HTML parsing failed (400 Bad Request), fallback to plain text
            if resp.status_code == 400:
                logger.warning("Telegram HTML parse failed, retrying in plain text...")
                fallback_payload = {
                    "chat_id": self.chat_id,
                    "text": f"[{title.strip()}]\n{message}" if title else message,
                    "disable_web_page_preview": True,
                }
                fallback_resp = requests.post(url, json=fallback_payload, timeout=self.timeout)
                if fallback_resp.status_code == 200 and fallback_resp.json().get("ok"):
                    logger.info("Telegram plain text notification sent successfully.")
                    return True

            logger.warning(
                "Telegram notification HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False

        except requests.exceptions.Timeout:
            logger.warning("Telegram notification timed out after %.1fs", self.timeout)
            return False
        except Exception as exc:
            logger.warning("Telegram notification failed: %s", exc)
            return False
