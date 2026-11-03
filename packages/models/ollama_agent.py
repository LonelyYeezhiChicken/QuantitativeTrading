"""Local Ollama AI Decision & Review Agent (Qwen2.5).

Provides:
1. Low-latency Multiple-Choice Sanity/Veto Check for candidate trade signals.
2. High-signal, noise-free Trade Journal Summaries answering:
   - 為什麼要進場 (Why Enter)
   - 決策是什麼 (AI Decision)
   - 出場與結果 (Exit & Result)
3. Safe offline mock fallback when Ollama is unavailable or times out.
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple


class OllamaDecisionAgent:
    """Local offline AI Copilot connecting to Ollama (default: qwen2.5:7b / qwen2.5-coder:1.5b)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        timeout: float = 3.5,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def check_health(self) -> Tuple[bool, list[str]]:
        """Verify if local Ollama daemon is reachable and list available models."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                return True, models
        except Exception:
            return False, []

    def evaluate_signal_choice(
        self,
        symbol: str,
        signal_side: str,         # 'LONG' or 'SHORT'
        market_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ask Ollama a multiple-choice question to sanity-check/veto a candidate signal.

        Returns:
            {
                "choice": "EXECUTE" | "VETO",
                "reason": str,
                "latency_ms": int,
                "model_used": str,
                "mode": "live_ollama" | "fallback_rule",
            }
        """
        price = market_state.get("price", 0.0)
        rsi = market_state.get("rsi", 50.0)
        ema21 = market_state.get("ema21", price)
        bias_pct = ((price - ema21) / ema21 * 100) if ema21 > 0 else 0.0
        candidate_reason = market_state.get("reason", "均線與動量信號觸發")

        # Dense, structured context for low cognitive load
        prompt = f"""你是加密貨幣量化風控副駕。
請評估以下客觀市場狀態，並針對候選交易信號做出二選一決策：

【市場當前狀態】
- 標的：{symbol}
- 最新市價：${price:,.2f}
- 1h RSI(14)：{rsi:.1f}
- 距 1h EMA21 乖離率：{bias_pct:+.2f}%
- 候選策略信號：建議【{signal_side} 開倉】
- 策略進場觸發點：{candidate_reason}

【決策選項】
- 選項 A (EXECUTE): 核准進場。市場指標正常，無極端超買追高或超賣破位風險。
- 選項 B (VETO): 否決觀望。動能過熱、逆勢風險過高或點位欠佳。

請直接以 JSON 格式輸出，不得附帶任何其他開頭或結尾文字：
{{"choice": "EXECUTE", "reason": "簡短說明核准理由"}} 或 {{"choice": "VETO", "reason": "簡短說明否決理由"}}
"""
        t0 = time.time()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 100},
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_resp = json.loads(resp.read().decode("utf-8"))
                response_text = raw_resp.get("response", "").strip()
                latency_ms = int((time.time() - t0) * 1000)

                # Parse JSON output
                parsed = self._extract_json(response_text)
                if parsed and "choice" in parsed:
                    choice = str(parsed["choice"]).upper().strip()
                    if "EXECUTE" in choice or "A" in choice:
                        c_final = "EXECUTE"
                    else:
                        c_final = "VETO"
                    reason = str(parsed.get("reason", "Ollama 審查通過"))
                    return {
                        "choice": c_final,
                        "reason": reason,
                        "latency_ms": latency_ms,
                        "model_used": self.model,
                        "mode": "live_ollama",
                    }
        except Exception:
            pass

        # Graceful Deterministic Fallback Rule
        return self._rule_fallback_choice(signal_side, rsi, bias_pct)

    def summarize_trade_journal(
        self,
        trade_record: Dict[str, Any],
    ) -> Dict[str, str]:
        """Generate high-signal, noise-free trade summary answering the 3 core questions:

        1. 為什麼要進場 (Why Enter)
        2. 決策是什麼 (AI Decision)
        3. 出場與結果 (Exit & Result)
        """
        symbol = trade_record.get("symbol", "BTC/USDT")
        side = trade_record.get("side", "LONG")
        entry_p = trade_record.get("entry_price", 0.0)
        exit_p = trade_record.get("exit_price", entry_p)
        pnl_usdt = trade_record.get("pnl_usdt", 0.0)
        pnl_pct = trade_record.get("pnl_pct", 0.0)
        entry_reason = trade_record.get("entry_reason", "均線回踩與動量確認")
        ai_decision = trade_record.get("ai_decision", "AI 風控核准進場")
        exit_reason = trade_record.get("exit_reason", "觸發動態追蹤停利")

        prompt = f"""你是專業量化交易日誌秘書。請將以下這筆平倉紀錄整理為三個清晰、極簡的項目（每項 20 字以內，繁體中文）：

【交易數據】
- 標的與方向：{symbol} {side}
- 開倉價：${entry_p:,.2f} | 平倉價：${exit_p:,.2f}
- 實現盈虧：${pnl_usdt:+,.2f} USDT ({pnl_pct:+.2f}%)
- 策略進場原因：{entry_reason}
- AI 風控決策：{ai_decision}
- 出場平倉原因：{exit_reason}

請務必輸出 JSON 格式：
{{
  "why_enter": "精簡說明為什麼要進場",
  "ai_decision": "精簡說明 AI 當初核准的決策依據",
  "exit_result": "精簡說明出場原因與盈虧結算"
}}
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 120},
        }

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_resp = json.loads(resp.read().decode("utf-8"))
                parsed = self._extract_json(raw_resp.get("response", ""))
                if parsed and "why_enter" in parsed:
                    return {
                        "why_enter": str(parsed["why_enter"]),
                        "ai_decision": str(parsed.get("ai_decision", ai_decision)),
                        "exit_result": str(parsed.get("exit_result", f"平倉 {exit_reason}，盈虧 ${pnl_usdt:+,.2f} ({pnl_pct:+.2f}%)")),
                        "source": "live_ollama",
                    }
        except Exception:
            pass

        # Deterministic Clean Fallback
        return {
            "why_enter": f"{symbol} {side}：{entry_reason}",
            "ai_decision": f"{ai_decision}",
            "exit_result": f"平倉原因：{exit_reason} | 盈虧：${pnl_usdt:+,.2f} ({pnl_pct:+.2f}%)",
            "source": "deterministic_fallback",
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """Robustly locate and parse JSON substring from model response."""
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
    def _rule_fallback_choice(side: str, rsi: float, bias_pct: float) -> Dict[str, Any]:
        """Deterministic safety rule when Ollama is offline."""
        if side == "LONG":
            if rsi > 70.0 or bias_pct > 3.0:
                return {
                    "choice": "VETO",
                    "reason": f"防追高規則觸發 (RSI={rsi:.1f}>70 或 乖離={bias_pct:+.1f}%>3%)",
                    "latency_ms": 1,
                    "model_used": "offline_fallback",
                    "mode": "fallback_rule",
                }
            return {
                "choice": "EXECUTE",
                "reason": f"指標處於健康區間 (RSI={rsi:.1f}, 乖離={bias_pct:+.1f}%)，核准開多",
                "latency_ms": 1,
                "model_used": "offline_fallback",
                "mode": "fallback_rule",
            }
        else:  # SHORT
            if rsi < 30.0 or bias_pct < -3.0:
                return {
                    "choice": "VETO",
                    "reason": f"防殺跌規則觸發 (RSI={rsi:.1f}<30 或 乖離={bias_pct:+.1f}%<-3%)",
                    "latency_ms": 1,
                    "model_used": "offline_fallback",
                    "mode": "fallback_rule",
                }
            return {
                "choice": "EXECUTE",
                "reason": f"指標處於健康空方動能 (RSI={rsi:.1f}, 乖離={bias_pct:+.1f}%)，核准開空",
                "latency_ms": 1,
                "model_used": "offline_fallback",
                "mode": "fallback_rule",
            }
