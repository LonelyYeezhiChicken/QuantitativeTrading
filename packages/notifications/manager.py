"""Notification Manager for Outbound Multi-Channel Push."""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Dict, List, Optional

from packages.notifications.base import BaseNotifier
from packages.notifications.line import LineNotifier
from packages.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class NotificationManager:
    """Dispatches outbound push notifications to all configured channels.

    Guarantees:
    - Never blocks the caller if async_send=True (uses thread pool).
    - Never raises exceptions: any network/credential failure is safely caught.
    - Zero inbound ports or webhooks opened.
    """

    def __init__(
        self,
        notifiers: Optional[List[BaseNotifier]] = None,
        max_workers: int = 2,
    ) -> None:
        if notifiers is not None:
            self.notifiers = notifiers
        else:
            self.notifiers = [
                TelegramNotifier(),
                LineNotifier(),
            ]
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="NotificationWorker",
        )

    def get_enabled_notifiers(self) -> List[BaseNotifier]:
        """Return list of notifiers that have valid credentials configured."""
        return [n for n in self.notifiers if n.is_enabled()]

    def send(
        self,
        message: str,
        title: Optional[str] = None,
        async_send: bool = True,
    ) -> Dict[str, bool]:
        """Dispatch message to all enabled notifiers.

        Args:
            message: Message body.
            title: Optional title.
            async_send: If True, executes in a background thread and returns immediately.

        Returns:
            Dictionary mapping notifier name to success boolean.
            If async_send is True, indicates whether each notifier is enabled and was scheduled.
        """
        enabled = self.get_enabled_notifiers()
        if not enabled:
            logger.debug("No notification channels are enabled.")
            return {}

        if async_send:
            for notifier in enabled:
                self._executor.submit(self._safe_send, notifier, message, title)
            return {n.name: True for n in enabled}

        results: Dict[str, bool] = {}
        for notifier in enabled:
            results[notifier.name] = self._safe_send(notifier, message, title)
        return results

    @staticmethod
    def _safe_send(notifier: BaseNotifier, message: str, title: Optional[str]) -> bool:
        try:
            return notifier.send(message=message, title=title)
        except Exception as exc:
            logger.warning("Error running notifier %s: %s", notifier.name, exc)
            return False

    def shutdown(self, wait: bool = False) -> None:
        """Shutdown the underlying thread pool executor."""
        self._executor.shutdown(wait=wait)


# Global singleton instance
_GLOBAL_NOTIFICATION_MANAGER: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Retrieve or initialize the global NotificationManager singleton."""
    global _GLOBAL_NOTIFICATION_MANAGER
    if _GLOBAL_NOTIFICATION_MANAGER is None:
        _GLOBAL_NOTIFICATION_MANAGER = NotificationManager()
    return _GLOBAL_NOTIFICATION_MANAGER


def send_notification(
    message: str,
    title: Optional[str] = None,
    async_send: bool = True,
) -> bool:
    """Convenience helper to send notification across all configured channels.

    Returns:
        True if at least one channel was dispatched/delivered, False otherwise.
    """
    manager = get_notification_manager()
    results = manager.send(message=message, title=title, async_send=async_send)
    return any(results.values())
