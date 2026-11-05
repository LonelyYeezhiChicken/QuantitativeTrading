"""Unit tests for CloudAiDecisionAgent & High-Speed Deterministic Fallback."""

import json
import socket
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from packages.models.cloud_ai_agent import CloudAiDecisionAgent, get_ai_decision_agent


class TestCloudAiDecisionAgent(unittest.TestCase):
    """Test suite ensuring Cloud AI operates with sub-second timeout and instant fallback."""

    def test_pure_rule_provider_executes_immediately(self):
        """Pure rule provider should execute in ~1ms without making any network calls."""
        agent = CloudAiDecisionAgent(provider="rule")
        self.assertEqual(agent.provider, "rule")

        # Healthy bull trend -> EXECUTE
        res = agent.evaluate_signal_choice(
            symbol="BTC/USDT",
            signal_side="LONG",
            market_state={"price": 80000.0, "rsi": 55.0, "ema21": 79500.0, "reason": "順勢回踩"},
        )
        self.assertEqual(res["choice"], "EXECUTE")
        self.assertEqual(res["mode"], "fallback_rule")
        self.assertIn("健康", res["reason"])

        # Extreme overbought -> VETO
        res_veto = agent.evaluate_signal_choice(
            symbol="BTC/USDT",
            signal_side="LONG",
            market_state={"price": 80000.0, "rsi": 75.0, "ema21": 75000.0, "reason": "突破"},
        )
        self.assertEqual(res_veto["choice"], "VETO")
        self.assertIn("超買", res_veto["reason"])

    @patch("urllib.request.urlopen")
    def test_gemini_api_success_parsing(self, mock_urlopen):
        """Gemini JSON response parsed accurately into EXECUTE."""
        mock_resp = MagicMock()
        gemini_response_payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"choice": "EXECUTE", "reason": "指標健康核准進場"})}
                        ]
                    }
                }
            ]
        }
        mock_resp.read.return_value = json.dumps(gemini_response_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        agent = CloudAiDecisionAgent(provider="gemini", api_key="fake_key_123", timeout=1.0)
        res = agent.evaluate_signal_choice(
            symbol="BTC/USDT",
            signal_side="LONG",
            market_state={"price": 80000.0, "rsi": 52.0, "ema21": 79800.0},
        )
        self.assertEqual(res["choice"], "EXECUTE")
        self.assertEqual(res["mode"], "cloud_gemini")
        self.assertIn("指標健康核准進場", res["reason"])

    @patch("urllib.request.urlopen")
    def test_cloud_ai_timeout_immediately_switches_to_mathematical_rules(self, mock_urlopen):
        """User core requirement: if Cloud AI is too slow, immediately cut off and switch to math rules."""
        mock_urlopen.side_effect = socket.timeout("Timed out waiting for Gemini server")

        agent = CloudAiDecisionAgent(provider="gemini", api_key="fake_key", timeout=0.5)
        res = agent.evaluate_signal_choice(
            symbol="BTC/USDT",
            signal_side="LONG",
            market_state={"price": 80000.0, "rsi": 55.0, "ema21": 79600.0},
        )

        # Must not raise exception, must return mathematical fallback immediately
        self.assertEqual(res["choice"], "EXECUTE")
        self.assertEqual(res["mode"], "fallback_rule")
        self.assertIn("響應逾時", res["reason"])

    @patch("urllib.request.urlopen")
    def test_cloud_ai_http_error_fallback(self, mock_urlopen):
        """Any HTTP 500 / 429 error gracefully switches to mathematical rules without crashing."""
        mock_urlopen.side_effect = urllib.error.HTTPError("http://...", 429, "Too Many Requests", {}, None)

        agent = CloudAiDecisionAgent(provider="openai", api_key="fake_openai", timeout=1.0)
        res = agent.evaluate_signal_choice(
            symbol="BTC/USDT",
            signal_side="LONG",
            market_state={"price": 80000.0, "rsi": 55.0, "ema21": 79600.0},
        )
        self.assertEqual(res["choice"], "EXECUTE")
        self.assertEqual(res["mode"], "fallback_rule")
        self.assertIn("高階數學風控規則", res["reason"])

    def test_factory_get_ai_decision_agent_env_resolution(self):
        """Factory initializes agent based on environment variables."""
        with patch.dict("os.environ", {"AI_PROVIDER": "rule", "AI_DECISION_TIMEOUT_SEC": "1.5"}):
            agent = get_ai_decision_agent()
            self.assertEqual(agent.provider, "rule")
            self.assertEqual(agent.timeout, 1.5)


if __name__ == "__main__":
    unittest.main()
