"""Notifications package for outbound messaging (Telegram Bot & LINE Bot)."""

from dotenv import load_dotenv

# Ensure .env is loaded if present
load_dotenv()

from packages.notifications.base import BaseNotifier
from packages.notifications.line import LineNotifier
from packages.notifications.manager import (
    NotificationManager,
    get_notification_manager,
    send_notification,
)
from packages.notifications.telegram import TelegramNotifier

__all__ = [
    "BaseNotifier",
    "TelegramNotifier",
    "LineNotifier",
    "NotificationManager",
    "get_notification_manager",
    "send_notification",
]
