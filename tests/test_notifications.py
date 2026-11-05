"""Tests for Outbound Push Notification Clients (Telegram Bot & LINE Bot)."""

from unittest.mock import MagicMock, patch
import requests
import pytest

from packages.notifications.base import BaseNotifier
from packages.notifications.line import LineNotifier
from packages.notifications.manager import (
    NotificationManager,
    get_notification_manager,
    send_notification,
)
from packages.notifications.telegram import TelegramNotifier


# ==============================================================================
# TelegramNotifier Tests
# ==============================================================================

def test_telegram_notifier_disabled_when_credentials_missing(monkeypatch):
    """When no credentials are provided in env or constructor, it should be disabled."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    notifier = TelegramNotifier()
    assert notifier.name == "telegram"
    assert notifier.is_enabled() is False
    assert notifier.send("Test message") is False


def test_telegram_notifier_successful_send():
    """Verify standard HTML send via Telegram API."""
    notifier = TelegramNotifier(token="mock_token", chat_id="123456789")
    assert notifier.is_enabled() is True

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {}}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = notifier.send("Order filled successfully", title="Trade Executed")
        assert success is True

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.telegram.org/botmock_token/sendMessage"
        payload = kwargs["json"]
        assert payload["chat_id"] == "123456789"
        assert "<b>Trade Executed</b>" in payload["text"]
        assert "Order filled successfully" in payload["text"]
        assert payload["parse_mode"] == "HTML"


def test_telegram_notifier_html_error_fallback_to_plain_text():
    """If HTML formatting is rejected with 400 Bad Request, it falls back to plain text."""
    notifier = TelegramNotifier(token="mock_token", chat_id="123456789")

    fail_resp = MagicMock()
    fail_resp.status_code = 400
    fail_resp.text = "Bad Request: can't parse entities"

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"ok": True}

    with patch("requests.post", side_effect=[fail_resp, ok_resp]) as mock_post:
        success = notifier.send("Unclosed <tag message", title="Alert")
        assert success is True
        assert mock_post.call_count == 2
        # Second call should not have parse_mode='HTML'
        second_payload = mock_post.call_args_list[1][1]["json"]
        assert "parse_mode" not in second_payload


def test_telegram_notifier_timeout_and_exceptions():
    """Network timeout or generic exception must not raise and should return False."""
    notifier = TelegramNotifier(token="mock_token", chat_id="123456789", timeout=1.0)

    with patch("requests.post", side_effect=requests.exceptions.Timeout("Read timeout")):
        assert notifier.send("Hello") is False

    with patch("requests.post", side_effect=RuntimeError("Unexpected connection drop")):
        assert notifier.send("Hello") is False


def test_telegram_notifier_empty_message():
    """Empty message should return False without making HTTP calls."""
    notifier = TelegramNotifier(token="mock_token", chat_id="123456789")
    with patch("requests.post") as mock_post:
        assert notifier.send("   ", title="") is False
        mock_post.assert_not_called()


# ==============================================================================
# LineNotifier Tests
# ==============================================================================

def test_line_notifier_disabled_when_credentials_missing(monkeypatch):
    """When no credentials are provided, line notifier is disabled."""
    monkeypatch.delenv("LINE_CHANNEL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINE_USER_ID", raising=False)
    monkeypatch.delenv("LINE_NOTIFY_TOKEN", raising=False)

    notifier = LineNotifier()
    assert notifier.name == "line"
    assert notifier.is_enabled() is False
    assert notifier.send("Hello") is False


def test_line_notifier_messaging_api_successful_push():
    """Verify push message via official LINE Messaging API."""
    notifier = LineNotifier(
        channel_access_token="mock_channel_token",
        user_id="U1234567890abcdef",
    )
    assert notifier.is_enabled() is True

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = notifier.send("Cloud stop-loss pushed", title="Breakeven Shield")
        assert success is True

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.line.me/v2/bot/message/push"
        assert kwargs["headers"]["Authorization"] == "Bearer mock_channel_token"
        payload = kwargs["json"]
        assert payload["to"] == "U1234567890abcdef"
        assert len(payload["messages"]) == 1
        assert "【Breakeven Shield】" in payload["messages"][0]["text"]


def test_line_notifier_legacy_notify_fallback():
    """Verify fallback to LINE Notify when only notify_token is provided."""
    notifier = LineNotifier(notify_token="mock_notify_token")
    assert notifier.is_enabled() is True

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        success = notifier.send("Legacy notify test")
        assert success is True

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://notify-api.line.me/api/notify"
        assert kwargs["headers"]["Authorization"] == "Bearer mock_notify_token"


def test_line_notifier_error_and_timeout():
    """Verify error status and timeout handling without crashing."""
    notifier = LineNotifier(channel_access_token="tok", user_id="uid")

    mock_err = MagicMock()
    mock_err.status_code = 401
    mock_err.text = "Unauthorized"

    with patch("requests.post", return_value=mock_err):
        assert notifier.send("Test") is False

    with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout):
        assert notifier.send("Test") is False


# ==============================================================================
# NotificationManager Tests
# ==============================================================================

class DummyNotifier(BaseNotifier):
    def __init__(self, name: str, enabled: bool = True, should_fail: bool = False):
        self._name = name
        self._enabled = enabled
        self._should_fail = should_fail
        self.sent_messages = []

    @property
    def name(self) -> str:
        return self._name

    def is_enabled(self) -> bool:
        return self._enabled

    def send(self, message: str, title=None) -> bool:
        if self._should_fail:
            raise RuntimeError("Boom!")
        self.sent_messages.append((title, message))
        return True


def test_notification_manager_sync_broadcast():
    """Manager dispatches synchronously to all enabled channels."""
    n1 = DummyNotifier("tg", enabled=True)
    n2 = DummyNotifier("line", enabled=True)
    n3 = DummyNotifier("disabled_ch", enabled=False)

    manager = NotificationManager(notifiers=[n1, n2, n3])
    assert len(manager.get_enabled_notifiers()) == 2

    results = manager.send("System online", title="Startup", async_send=False)
    assert results == {"tg": True, "line": True}
    assert len(n1.sent_messages) == 1
    assert len(n2.sent_messages) == 1
    assert len(n3.sent_messages) == 0
    manager.shutdown()


def test_notification_manager_async_send():
    """Manager dispatches asynchronously via background thread pool."""
    n1 = DummyNotifier("tg", enabled=True)
    manager = NotificationManager(notifiers=[n1])

    results = manager.send("Async ping", async_send=True)
    assert results == {"tg": True}

    # Wait for thread pool to finish
    manager.shutdown(wait=True)
    assert len(n1.sent_messages) == 1


def test_notification_manager_exception_isolation():
    """If one notifier raises an unexpected error, other notifiers still succeed."""
    bad_n = DummyNotifier("bad", enabled=True, should_fail=True)
    good_n = DummyNotifier("good", enabled=True, should_fail=False)

    manager = NotificationManager(notifiers=[bad_n, good_n])
    results = manager.send("Test message", async_send=False)

    assert results["bad"] is False
    assert results["good"] is True
    assert len(good_n.sent_messages) == 1
    manager.shutdown()


def test_notification_manager_no_enabled_channels():
    """When no channels are configured, returns empty dict safely."""
    manager = NotificationManager(notifiers=[])
    assert manager.send("Hello", async_send=False) == {}
    manager.shutdown()


def test_global_send_notification_helper():
    """Global send_notification helper delegates cleanly."""
    with patch("packages.notifications.manager.NotificationManager.send") as mock_send:
        mock_send.return_value = {"telegram": True}
        ok = send_notification("Global ping", title="Ping")
        assert ok is True
        mock_send.assert_called_once_with(message="Global ping", title="Ping", async_send=True)
