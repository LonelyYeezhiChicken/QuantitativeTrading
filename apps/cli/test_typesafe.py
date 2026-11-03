"""CLI Diagnostic Tool: Test TypeSafe AI (Jev) Short-Term Decision Engine."""

import argparse
import sys
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.models import TypeSafeAIAgent

def main():
    parser = argparse.ArgumentParser(description="Test TypeSafe AI Short-Term Decision Making")
    parser.add_argument("--key", default="", help="TypeSafe AI API Key (Optional)")
    parser.add_argument("--model", default="jev-latest", help="TypeSafe model name")
    args = parser.parse_args()

    print("=" * 70)
    print("  TypeSafe AI (Jev) 短線量化決策引擎診斷工具")
    print("  官網: https://typesafe.ai/")
    print("=" * 70)

    agent = TypeSafeAIAgent(api_key=args.key, model=args.model)

    print(f"\n[Step 1] 初始化 TypeSafe AI Agent...")
    fit_info = agent.fit(pd.DataFrame(), [])
    print(f"  -> 模型名稱 : {agent.name} ({fit_info['model']})")
    print(f"  -> 運行模式 : {fit_info['mode']} (未填金鑰時自動開啟安全演練)")

    # 2. Simulate 3 Market States (Bullish breakout, Bearish reversal, Sideways)
    test_scenarios = [
        {
            "name": "🔥 強烈多頭突破 (Bullish Breakout)",
            "row": pd.Series({
                "ret_1": 0.008, "ret_3": 0.015, "rsi_14": 62.0, "natr_14": 0.018,
                "ema_ratio_21": 0.012, "ema_ratio_200": 0.035, "volume_ratio_24": 2.4, "bb_percent": 0.85
            })
        },
        {
            "name": "❄️ 超賣反彈契機 (Oversold Dip)",
            "row": pd.Series({
                "ret_1": -0.012, "ret_3": -0.025, "rsi_14": 28.5, "natr_14": 0.022,
                "ema_ratio_21": -0.015, "ema_ratio_200": 0.010, "volume_ratio_24": 1.8, "bb_percent": 0.12
            })
        },
        {
            "name": "💤 弱勢盤整觀望 (Choppy Neutral)",
            "row": pd.Series({
                "ret_1": 0.0005, "ret_3": -0.001, "rsi_14": 49.0, "natr_14": 0.010,
                "ema_ratio_21": 0.001, "ema_ratio_200": -0.005, "volume_ratio_24": 0.8, "bb_percent": 0.48
            })
        }
    ]

    print("\n[Step 2] 執行三組短線情境之 TypeSafe AI 結構化決策推演:")
    for sc in test_scenarios:
        state_str = agent.format_state(sc["row"])
        resp = agent.query(state_str)

        action_data = resp.get("action", {})
        noul_data = resp.get("is_high_conviction", {})
        score_data = resp.get("volatility_risk", {})

        print(f"\n  情境: {sc['name']}")
        print(f"  State: \"{state_str}\"")
        print(f"  ┌─ Choice (行動決策) : {action_data.get('choice')} (置信度: {action_data.get('confidence', 0):.2f})")
        print(f"  ├─ 分類機率分佈       : {action_data.get('probabilities')}")
        print(f"  ├─ Noul (高勝率機率)  : {noul_data.get('noul', 0):.1%}")
        print(f"  └─ Score (波動風險評級): {score_data.get('score')} / 5")

    print("\n" + "=" * 70)
    print("  TypeSafe AI 結構化短線決策模組預留完畢！隨時可供調用。")
    print("=" * 70)

if __name__ == "__main__":
    main()
