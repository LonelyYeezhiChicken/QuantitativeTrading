"""Base Notification Interface for Outbound Messaging Push."""

from abc import ABC, abstractmethod
from typing import Optional


class BaseNotifier(ABC):
    """Abstract base class for all push notification clients.

    Strictly outbound-only:
    - Never opens a listening port or local server.
    - Never throws exceptions to caller on network or authentication failure.
    - Gracefully reports True on success, False on failure.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the notification channel (e.g., 'telegram', 'line')."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if required credentials are present and notifications are active."""
        pass

    @abstractmethod
    def send(self, message: str, title: Optional[str] = None) -> bool:
        """Send a push notification message.

        Args:
            message: The main message body.
            title: Optional subject/title to highlight the message.

        Returns:
            True if sent successfully, False otherwise.
        """
        pass
