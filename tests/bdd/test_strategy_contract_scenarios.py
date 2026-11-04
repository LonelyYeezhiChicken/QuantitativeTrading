"""BDD Scenario Implementation Tests: Strategy Contract Polymorphism & Dependency Injection."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.data import CCXTFetcher
from packages.features import FeaturePipeline
from packages.models.base import BaseTradingModel
from packages.models.rule_based import DualEMACrossoverModel
from packages.models.advanced_strategies import SwapMultiRegimeModel, FibonacciSNRModel
from packages.models.lgbm_agent import LGBMAgent
from packages.execution.paper_broker import PaperBroker
from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState


class TestStrategyContractBDDScenarios:
    """BDD Step implementations matching strategy_contract_polymorphism.feature."""

    def test_scenario_base_trading_model_polymorphism(self):
        """Scenario: 多元策略模型滿足 BaseTradingModel 統一契約規範"""
        # Given 系統載入多元策略模型包含雙均線、LightGBM 代理人、多體制合約模型與斐波那契黃金口袋模型
        fetcher = CCXTFetcher()
        df = fetcher.generate_mock_ohlcv(days=20, seed=42)
        pipeline = FeaturePipeline(target_horizon=3)
        features_df, feature_cols = pipeline.build_features(df)

        models: list[BaseTradingModel] = [
            DualEMACrossoverModel(fast_span=21, slow_span=50),
            SwapMultiRegimeModel(ema_span=21),
            FibonacciSNRModel(swing_window=24),
            LGBMAgent(num_boost_round=10),
        ]

        # When 對標準化行情數據特徵集調用 fit 與 predict 方法
        for model in models:
            assert isinstance(model, BaseTradingModel)
            fit_res = model.fit(features_df, feature_cols=feature_cols)
            assert isinstance(fit_res, dict)

            preds = model.predict(features_df)

            # Then 所有策略模型均能回傳長度完全匹配之 numpy array 預測信號
            assert isinstance(preds, np.ndarray)
            assert len(preds) == len(features_df)

            # And 所有信號強度數值皆嚴格收斂在 [-1.0, 1.0] 區間之內
            assert np.all(preds >= -1.0)
            assert np.all(preds <= 1.0)

    def test_scenario_autopilot_dependency_injection(self, tmp_path):
        """Scenario: 任意 BaseTradingModel 策略模型無縫注入自動操盤中樞"""
        # Given 開發者自訂了一個繼承自 BaseTradingModel 之斐波那契黃金口袋策略模型
        custom_strategy = FibonacciSNRModel(swing_window=36, fib_lower=0.50, fib_upper=0.65)
        paper_state = tmp_path / "autopilot_di_paper.json"
        custom_gateway = PaperBroker(initial_balance=500.0, state_file=str(paper_state))
        custom_state = tmp_path / "autopilot_di_state.json"

        # When 初始化 UnifiedAutopilotEngine 時透過 strategy 與 gateway 參數進行依賴注入
        engine = UnifiedAutopilotEngine(
            mode="SWAP_10X",
            capital=100.0,
            symbol="BTC/USDT",
            leverage=10,
            gateway=custom_gateway,
            strategy=custom_strategy,
            state_file=custom_state,
            enable_ai_veto=False,
        )

        # Then 操盤中樞之內部策略應成功綁定為注入之斐波那契模型
        assert engine.strategy is custom_strategy
        assert engine.gw is custom_gateway
        assert engine.strategy.name.startswith("Fibonacci_SNR")

        # And 操盤中樞執行 step 評估時直接調度該注入策略產出決策信號
        step_res = engine.step()
        assert isinstance(step_res, dict)
        assert step_res["status"] == AutopilotState.STANDBY
        assert "price" in step_res
        assert step_res["price"] > 0
