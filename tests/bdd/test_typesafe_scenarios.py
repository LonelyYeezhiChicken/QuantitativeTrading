"""BDD Scenario Implementation Tests: TypeSafe AI (Jev) Decision Agent."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.data import CCXTFetcher
from packages.models import TypeSafeAIAgent
from packages.backtest import RollingBacktestEvaluator, RollingEvaluationResult

class TestTypeSafeBDDScenarios:
    """BDD Step implementations matching typesafe_decision.feature."""

    def test_scenario_market_state_serialization(self):
        """Scenario: 市場狀態字串序列化"""
        # Given 一組即時市場特徵包含收益率、RSI、EMA 偏離度與成交量
        row = pd.Series({
            "ret_1": 0.005,
            "ret_3": 0.012,
            "rsi_14": 58.5,
            "natr_14": 0.015,
            "ema_ratio_21": 0.008,
            "ema_ratio_200": 0.025,
            "volume_ratio_24": 1.6,
            "bb_percent": 0.72,
        })
        agent = TypeSafeAIAgent()

        # When Agent 執行 format_state 進行狀態序列化
        state_str = agent.format_state(row)

        # Then 產出的 state 字串應精確包含量化指標與趨勢資訊
        assert "Asset: BTC/USDT" in state_str
        assert "1h_Return: +0.50%" in state_str
        assert "RSI(14): 58.5" in state_str
        assert "Vol_Multiplier: 1.6x" in state_str
        assert "EMA_200_Trend: +2.50%" in state_str

    def test_scenario_typed_question_contract(self):
        """Scenario: 強型別提問合約生成"""
        agent = TypeSafeAIAgent()

        # When Agent 構建決策提問規格 (build_questions)
        questions = agent.build_questions()

        # Then 規格中應包含 "action" 的 choice 分類 (BUY, SELL, HOLD)
        assert "action" in questions
        assert questions["action"]["type"] == "choice"
        criteria = questions["action"]["criteria"]
        assert {"BUY", "SELL", "HOLD"}.issubset(set(criteria.keys()))

        # And 應包含 "is_high_conviction" 的 noul 伯努利二元機率合約
        assert "is_high_conviction" in questions
        assert questions["is_high_conviction"]["type"] == "noul"

        # And 應包含 "volatility_risk" 的 1 到 5 分 score 階梯評級合約
        assert "volatility_risk" in questions
        assert questions["volatility_risk"]["type"] == "score"
        assert "5" in questions["volatility_risk"]["legend"]

    def test_scenario_modular_backtest_compatibility(self):
        """Scenario: TypeSafe AI 決策驅動之回測相容性"""
        # Given 存在歷史 OHLCV 測試數據
        fetcher = CCXTFetcher()
        mock_df = fetcher.generate_mock_ohlcv(days=45, seed=123)
        agent = TypeSafeAIAgent()
        evaluator = RollingBacktestEvaluator(initial_capital=100.0)

        # When 將 TypeSafeAIAgent 傳入 RollingBacktestEvaluator 進行回測
        res = evaluator.evaluate(
            model=agent,
            df=mock_df,
            symbol="BTC/USDT",
            period_description="Mock 45 Days",
            train_model=False,
        )

        # Then Agent 應正常輸出符合 BaseTradingModel 規範的預測向量
        assert isinstance(res, RollingEvaluationResult)
        assert res.model_name == "TypeSafe_Jev_Decision"
        assert res.final_equity > 0

        # And 回測評估器應成功計算出策略總收益率、夏普比率與月度資產成長表
        assert "Sharpe Ratio" in res.metrics
        assert not res.monthly_breakdown.empty
        assert "Total Return (%)" in res.metrics
