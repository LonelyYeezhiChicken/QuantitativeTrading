"""BDD Scenario Implementation Tests: Verifying Given-When-Then User Behaviors."""

import sys
from pathlib import Path
import pytest
import pandas as pd

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from packages.data import CCXTFetcher, DataManager
from packages.features import FeaturePipeline
from packages.models import LGBMAgent
from packages.backtest import BacktestEngine
from packages.execution import PaperBroker

class TestDashboardBDDScenarios:
    """BDD Step Implementations matching dashboard_behavior.feature."""

    def test_scenario_one_click_market_data_download(self, tmp_path):
        """Scenario: 一鍵下載並檢視市場行情數據"""
        # Given 使用者選擇交易對 "BTC/USDT" 且時間週期為 "1h"
        symbol = "BTC/USDT"
        timeframe = "1h"
        dm = DataManager(raw_dir=str(tmp_path / "raw"), processed_dir=str(tmp_path / "proc"))

        # When 使用者觸發數據下載管線
        fetcher = CCXTFetcher()
        df = fetcher.generate_mock_ohlcv(symbol=symbol, timeframe=timeframe, days=30)
        saved_path = dm.save_raw_data(df, symbol, timeframe)

        # Then 系統應在本地儲存有效的 OHLCV 歷史數據
        assert saved_path.exists()
        loaded_df = dm.load_raw_data(symbol, timeframe)
        assert loaded_df is not None

        # And 數據總筆數應大於 50 筆
        assert len(loaded_df) >= 50

        # And 應能產生包含開高低收與成交量的圖表資料
        expected_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        assert expected_cols.issubset(set(loaded_df.columns))

    def test_scenario_one_click_model_training_and_backtesting(self, tmp_path):
        """Scenario: 一鍵執行 LightGBM 模型訓練與回測"""
        # Given 本地已存在 "BTC/USDT" 的歷史行情數據
        symbol = "BTC/USDT"
        timeframe = "1h"
        fetcher = CCXTFetcher()
        raw_df = fetcher.generate_mock_ohlcv(symbol=symbol, timeframe=timeframe, days=60)

        # And 設定交易信心閥值為 0.002
        threshold = 0.002

        # When 使用者點擊開始訓練與回測
        pipeline = FeaturePipeline(target_horizon=3)
        features_df, feature_cols = pipeline.build_features(raw_df)
        
        agent = LGBMAgent(num_boost_round=50)
        cv_metrics = agent.train_cv(features_df, feature_cols, target_col="target_forward_return", n_splits=3)
        preds = agent.predict(features_df)

        engine = BacktestEngine(initial_capital=10000.0, confidence_threshold=threshold)
        results_df, perf = engine.run(features_df, preds)

        # Then 系統應使用時序淨化交叉驗證 (Purged CV) 完成模型訓練
        assert cv_metrics["evaluated_samples"] > 0
        assert "avg_rmse" in cv_metrics
        assert "avg_ic" in cv_metrics

        # And 系統應輸出核心績效指標 (Sharpe Ratio, Max Drawdown, 勝率)
        assert "Sharpe Ratio" in perf
        assert "Max Drawdown (%)" in perf
        assert "Win Rate (%)" in perf
        assert "Total Return (%)" in perf

        # And 系統應產生策略權益曲線 (Equity Curve) 與特徵重要性分析
        assert "equity" in results_df.columns
        assert len(results_df["equity"]) == len(features_df)
        top_features = agent.get_top_features(5)
        assert len(top_features) == 5

    def test_scenario_paper_trading_step_simulation(self, tmp_path):
        """Scenario: 模擬盤即時交易與帳戶狀態更新"""
        # Given 模擬盤帳戶可用資金為 10000.0 USDT
        state_file = tmp_path / "paper_state_bdd.json"
        broker = PaperBroker(initial_balance=10000.0, state_file=str(state_file))
        assert broker.cash == 10000.0

        # And 當前市場價格為 50000.0 USDT
        current_price = 50000.0

        # When 策略發出買入信號並投入 2000.0 USDT
        order = broker.buy("BTC/USDT", current_price=current_price, usdt_amount=2000.0)

        # Then 模擬盤應自動扣除 0.05% 手續費與滑價並增加持倉部位
        assert order is not None
        assert "BTC/USDT" in broker.positions
        assert broker.positions["BTC/USDT"]["amount"] > 0

        # And 帳戶剩餘現金應正確扣減
        assert broker.cash == pytest.approx(8000.0)

        # And 交易紀錄流水應新增一筆 BUY 訂單紀錄
        assert len(broker.trade_history) == 1
        assert broker.trade_history[0]["side"] == "BUY"
        assert broker.trade_history[0]["symbol"] == "BTC/USDT"
