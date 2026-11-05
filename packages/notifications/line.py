"""LINE Bot Outbound Push Client.

Uses official LINE Messaging API Push Message endpoint.
Strictly outbound-only; never runs any inbound webhook or polling listener.
(Also supports legacy LINE Notify token fallback if configured).
"""

import logging
import os
from typing import Optional
import requests

from packages.notifications.base import BaseNotifier

logger = logging.getLogger(__name__)


class LineNotifier(BaseNotifier):
    """Outbound LINE Messaging API Push Notification Client."""

    LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
    LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"

    def __init__(
        self,
        channel_access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        notify_token: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.channel_access_token = (
            channel_access_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        ).strip()
        self.user_id = (user_id or os.getenv("LINE_USER_ID", "")).strip()
        self.notify_token = (notify_token or os.getenv("LINE_NOTIFY_TOKEN", "")).strip()
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "line"

    def is_enabled(self) -> bool:
        """True if either LINE Messaging API or legacy LINE Notify credentials are configured."""
        has_messaging_api = bool(self.channel_access_token and self.user_id)
        has_notify = bool(self.notify_token)
        return has_messaging_api or has_notify

    def send(self, message: str, title: Optional[str] = None) -> bool:
        """Send a push notification via LINE Messaging API (or Notify fallback).

        Args:
            message: Message body.
            title: Optional title prepended to message.

        Returns:
            True if delivered successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.debug("LineNotifier is disabled (missing credentials).")
            return False

        if not message.strip() and not (title and title.strip()):
            logger.warning("LineNotifier: empty message provided, skipping.")
            return False

        formatted_text = f"【{title.strip()}】\n\n{message}" if title and title.strip() else message

        # 1. Primary: Official LINE Messaging API (Long-term supported)
        if self.channel_access_token and self.user_id:
            return self._send_messaging_api(formatted_text)

        # 2. Secondary: Legacy LINE Notify API (until March 2025 deprecation)
        if self.notify_token:
            return self._send_line_notify(formatted_text)

        return False

    def _send_messaging_api(self, text: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self.channel_access_token}",
            "Content-Type": "application/json",
        }
        # LINE text message max length is 5000 chars
        payload = {
            "to": self.user_id,
            "messages": [
                {
                    "type": "text",
                    "text": text[:5000],
                }
            ],
        }

        try:
            resp = requests.post(
                self.LINE_PUSH_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                logger.info("LINE Messaging API push notification sent successfully.")
                return True

            logger.warning(
                "LINE Messaging API HTTP %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False

        except requests.exceptions.Timeout:
            logger.warning("LINE Messaging API timed out after %.1fs", self.timeout)
            return False
        except Exception as exc:
            logger.warning("LINE Messaging API push failed: %s", exc)
            return False

    def _send_line_notify(self, text: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self.notify_token}",
        }
        payload = {"message": f"\n{text[:1000]}"}

        try:
            resp = requests.post(
                self.LINE_NOTIFY_URL,
                data=payload,
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                logger.info("LINE Notify sent successfully.")
                return True

            logger.warning("LINE Notify HTTP %d: %s", resp.status_code, resp.text[:200])
            return False

        except Exception as exc:
            logger.warning("LINE Notify failed: %s", exc)
            return False
