"""Cloud AI Decision & Veto Agent with Ultra-Low Latency Fallback.

Supports:
1. Google Gemini API (gemini-1.5-flash / gemini-2.0-flash)
2. OpenAI / DeepSeek compatible APIs (gpt-4o-mini / deepseek-chat)
3. Local Ollama (qwen2.5)
4. Instant Deterministic Rule Fallback (under timeout / network drops / offline)

Design Mandate:
- Low-latency sanity check for trade entry (EXECUTE vs VETO).
- Strictly enforced timeout (default 2.0s). If the cloud AI takes too long,
  it immediately falls back to high-level mathematical deterministic rules
  to guarantee zero missed trades and zero execution blocking.
"""

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("CloudAiDecisionAgent")


class CloudAiDecisionAgent:
    """Production Cloud AI Decision Agent with sub-second timeout & deterministic rule fallback."""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        # 1. Resolve Provider
        env_provider = os.getenv("AI_PROVIDER", "").lower().strip()
        if provider:
            self.provider = provider.lower().strip()
        elif env_provider:
            self.provider = env_provider
        elif os.getenv("GEMINI_API_KEY"):
            self.provider = "gemini"
        elif os.getenv("DEEPSEEK_API_KEY"):
            self.provider = "deepseek"
        elif os.getenv("OPENAI_API_KEY"):
            self.provider = "openai"
        else:
            self.provider = "rule"

        # 2. Strict Timeout (User mandate: auto-switch to mathematical rules if response is slow)
        env_timeout = os.getenv("AI_DECISION_TIMEOUT_SEC")
        if timeout is not None:
            self.timeout = float(timeout)
        elif env_timeout:
            try:
                self.timeout = float(env_timeout)
            except ValueError:
                self.timeout = 2.0
        else:
            self.timeout = 2.0

        # 3. Resolve API Key & Model based on Provider
        if self.provider == "gemini":
            self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
            self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
            self.base_url = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        elif self.provider == "deepseek":
            self.api_key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
            self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
            self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        elif self.provider == "openai":
            self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
            self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        elif self.provider == "ollama":
            self.api_key = ""
            self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip()
            self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        else:
            # Deterministic Rule
            self.provider = "rule"
            self.api_key = ""
            self.model = "deterministic_rules"
            self.base_url = ""

    def evaluate_signal_choice(
        self,
        symbol: str,
        signal_side: str,  # 'LONG' or 'SHORT'
        market_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ask Cloud AI / Local AI for multiple-choice entry sanity check (EXECUTE vs VETO).

        If the AI response takes longer than self.timeout (default 2.0s) or fails,
        instantly switch to high-level mathematical deterministic rules.
        """
        price = float(market_state.get("price", 0.0))
        rsi = float(market_state.get("rsi", 50.0))
        ema21 = float(market_state.get("ema21", price))
        bias_pct = ((price - ema21) / ema21 * 100.0) if ema21 > 0 else 0.0
        candidate_reason = str(market_state.get("reason", "趨勢回踩動能確認"))

        # If provider is rule or no API key, execute mathematical rules directly (0ms)
        if self.provider == "rule" or (self.provider in ("gemini", "openai", "deepseek") and not self.api_key):
            return self._rule_fallback_choice(signal_side, rsi, bias_pct)

        prompt = (
            f"你是加密貨幣量化風控專家。\n"
            f"請評估以下候選進場信號，並從選項二選一：\n\n"
            f"【市場參數】\n"
            f"- 標的：{symbol}\n"
            f"- 現價：${price:,.2f}\n"
            f"- 1h RSI(14)：{rsi:.1f}\n"
            f"- 距 1h EMA21 乖離率：{bias_pct:+.2f}%\n"
            f"- 候選信號：{signal_side}\n"
            f"- 觸發理由：{candidate_reason}\n\n"
            f"【二選一選項】\n"
            f"- 選項 A (EXECUTE): 核准進場。指標正常，無追高接刀極端風險。\n"
            f"- 選項 B (VETO): 否決觀望。動能過熱或乖離過大。\n\n"
            f"請務必輸出 JSON 格式：\n"
            f'{{"choice": "EXECUTE", "reason": "核准簡由"}} 或 {{"choice": "VETO", "reason": "否決簡由"}}'
        )

        t0 = time.time()
        try:
            if self.provider == "gemini":
                choice, reason = self._call_gemini(prompt)
            elif self.provider in ("openai", "deepseek"):
                choice, reason = self._call_openai_compatible(prompt)
            elif self.provider == "ollama":
                choice, reason = self._call_ollama(prompt)
            else:
                return self._rule_fallback_choice(signal_side, rsi, bias_pct)

            latency_ms = int((time.time() - t0) * 1000)
            return {
                "choice": choice,
                "reason": reason,
                "latency_ms": latency_ms,
                "model_used": self.model,
                "mode": f"cloud_{self.provider}",
            }
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            elapsed = time.time() - t0
            # Immediate fallback to mathematical rules
            return self._rule_fallback_choice(
                signal_side,
                rsi,
                bias_pct,
                fallback_reason=f"雲端 AI 響應逾時 ({elapsed:.2f}s > {self.timeout}s)，立即切換為高階數學風控規則",
            )
        except Exception as exc:
            return self._rule_fallback_choice(
                signal_side,
                rsi,
                bias_pct,
                fallback_reason=f"雲端 AI 異常 ({str(exc)[:40]})，切換為高階數學風控規則",
            )

    def _call_gemini(self, prompt: str) -> Tuple[str, str]:
        """Call Google Gemini generateContent endpoint with responseMimeType=application/json."""
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 120,
                "responseMimeType": "application/json",
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            candidates = body.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                parsed = self._extract_json(text)
                if parsed and "choice" in parsed:
                    c_str = str(parsed["choice"]).upper()
                    choice = "EXECUTE" if ("EXECUTE" in c_str or "A" in c_str) else "VETO"
                    reason = str(parsed.get("reason", "Gemini 風控審核"))
                    return choice, reason

        raise ValueError("Invalid or empty response from Gemini API")

    def _call_openai_compatible(self, prompt: str) -> Tuple[str, str]:
        """Call OpenAI or DeepSeek chat/completions endpoint."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a quantitative risk management assistant. Answer only in JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 120,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            choices = body.get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "")
                parsed = self._extract_json(text)
                if parsed and "choice" in parsed:
                    c_str = str(parsed["choice"]).upper()
                    choice = "EXECUTE" if ("EXECUTE" in c_str or "A" in c_str) else "VETO"
                    reason = str(parsed.get("reason", f"{self.provider} 風控審核"))
                    return choice, reason

        raise ValueError(f"Invalid or empty response from {self.provider} API")

    def _call_ollama(self, prompt: str) -> Tuple[str, str]:
        """Call local Ollama endpoint."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 100},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            parsed = self._extract_json(body.get("response", ""))
            if parsed and "choice" in parsed:
                c_str = str(parsed["choice"]).upper()
                choice = "EXECUTE" if ("EXECUTE" in c_str or "A" in c_str) else "VETO"
                reason = str(parsed.get("reason", "Ollama 風控審核"))
                return choice, reason

        raise ValueError("Invalid or empty response from Ollama")

    def summarize_trade_journal(self, trade_record: Dict[str, Any]) -> Dict[str, str]:
        """Summarize trade record answering Why Enter, AI Decision, and Exit Result."""
        symbol = trade_record.get("symbol", "BTC/USDT")
        side = trade_record.get("side", "LONG")
        entry_reason = trade_record.get("entry_reason", "雙均線順勢回踩確認")
        ai_decision = trade_record.get("ai_decision", "AI 風控核准")
        exit_reason = trade_record.get("exit_reason", "動態移動停利鎖利")
        pnl_usdt = trade_record.get("pnl_usdt", 0.0)
        pnl_pct = trade_record.get("pnl_pct", 0.0)

        # Fast deterministic summary (safe, low token consumption)
        return {
            "why_enter": f"{symbol} {side}：{entry_reason}",
            "ai_decision": f"{ai_decision}",
            "exit_result": f"平倉原因：{exit_reason} ｜ 盈虧：${pnl_usdt:+,.2f} ({pnl_pct:+.2f}%)",
            "source": f"cloud_{self.provider}" if self.provider != "rule" else "deterministic_fallback",
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """Robustly extract JSON substring."""
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
        return None

    @staticmethod
    def _rule_fallback_choice(
        side: str,
        rsi: float,
        bias_pct: float,
        fallback_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """High-level mathematical deterministic rules for instant fallback."""
        prefix = f"[{fallback_reason}] " if fallback_reason else ""
        if side.upper() == "LONG":
            if rsi > 70.0 or bias_pct > 3.0:
                return {
                    "choice": "VETO",
                    "reason": f"{prefix}超買過熱防追高 (RSI={rsi:.1f}>70 或 乖離={bias_pct:+.1f}%>3%)",
                    "latency_ms": 1,
                    "model_used": "deterministic_rules",
                    "mode": "fallback_rule",
                }
            return {
                "choice": "EXECUTE",
                "reason": f"{prefix}指標處於健康順勢區間 (RSI={rsi:.1f}, 乖離={bias_pct:+.1f}%)，核准開多",
                "latency_ms": 1,
                "model_used": "deterministic_rules",
                "mode": "fallback_rule",
            }
        else:  # SHORT
            if rsi < 30.0 or bias_pct < -3.0:
                return {
                    "choice": "VETO",
                    "reason": f"{prefix}超賣過度防追空 (RSI={rsi:.1f}<30 或 乖離={bias_pct:+.1f}%<-3%)",
                    "latency_ms": 1,
                    "model_used": "deterministic_rules",
                    "mode": "fallback_rule",
                }
            return {
                "choice": "EXECUTE",
                "reason": f"{prefix}指標處於健康順勢區間 (RSI={rsi:.1f}, 乖離={bias_pct:+.1f}%)，核准開空",
                "latency_ms": 1,
                "model_used": "deterministic_rules",
                "mode": "fallback_rule",
            }


def get_ai_decision_agent(
    provider: Optional[str] = None,
    ollama_model: str = "qwen2.5:7b",
    timeout: Optional[float] = None,
) -> CloudAiDecisionAgent:
    """Factory creating the appropriate AI Decision Agent with automatic fallback."""
    return CloudAiDecisionAgent(provider=provider, timeout=timeout)
