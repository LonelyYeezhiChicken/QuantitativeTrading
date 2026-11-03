"""BDD Scenario Implementation Tests: Verifying Given-When-Then User Behaviors."""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from packages.data import CCXTFetcher, DataManager
from packages.features import FeaturePipeline
from packages.models import LGBMAgent, DualEMACrossoverModel, RSIMomentumModel
from packages.backtest import BacktestEngine, RollingBacktestEvaluator, RollingEvaluationResult
from packages.execution import PaperBroker, BingXGateway, MarketType


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

    def test_scenario_manual_order_execution_and_dual_channel(self, tmp_path):
        """Scenario: 手動模擬買賣與雙通道下單撮合"""
        # Given 交易員操作手動下單面板
        state_file = tmp_path / "manual_paper_broker.json"
        broker = PaperBroker(initial_balance=1000.0, state_file=str(state_file))
        gw = BingXGateway(dry_run=True, enable_ws=False)
        cur_price = 50000.0

        # When 交易員透過本地模擬經紀商執行市價買入 100.0 USDT
        buy_res = broker.buy("BTC/USDT", current_price=cur_price, usdt_amount=100.0)

        # Then 買單回傳物件應具備成交數量與價格且無 KeyError 異常
        assert buy_res is not None
        assert "quantity" in buy_res
        assert "price" in buy_res
        assert buy_res["quantity"] > 0
        assert broker.positions["BTC/USDT"]["amount"] == pytest.approx(buy_res["quantity"])

        # When 交易員執行市價全額平倉賣出
        sell_res = broker.sell("BTC/USDT", current_price=51000.0, pct_position=1.0)

        # Then 賣單回傳物件應具備平倉數量與實現盈虧且持倉歸零
        assert sell_res is not None
        assert "quantity" in sell_res
        assert "realized_pnl" in sell_res
        assert "BTC/USDT" not in broker.positions

        # When 交易員切換至 BingX OpenAPI 通道發送模擬買單
        gw_res = gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.002,
            market_type=MarketType.SPOT.value,
        )

        # Then 網關應返回撮合成交結果與訂單識別碼
        assert gw_res.get("result") is True
        assert "data" in gw_res
        assert "orderId" in gw_res["data"]

    def test_scenario_multi_model_backtesting_and_rolling_evaluator(self, tmp_path):
        """Scenario: 多模型特徵擬合與年度滾動複利評估"""
        # Given 具備完整 78+ 技術因子的特徵矩陣
        fetcher = CCXTFetcher()
        raw_df = fetcher.generate_mock_ohlcv(symbol="BTC/USDT", timeframe="1h", days=40)
        pipeline = FeaturePipeline(target_horizon=3)
        feat_df, cols = pipeline.build_features(raw_df)

        # When 針對特徵數據擬合 Dual EMA 與 RSI 規則策略
        ema_model = DualEMACrossoverModel(fast_span=21, slow_span=50)
        rsi_model = RSIMomentumModel(lower_thresh=35.0, upper_thresh=65.0)

        ema_model.fit(feat_df, cols)
        rsi_model.fit(feat_df, cols)

        ema_signals = ema_model.predict(feat_df)
        rsi_signals = rsi_model.predict(feat_df)

        # Then 策略應產出連續數值化交易訊號且無前視偏差
        assert len(ema_signals) == len(feat_df)
        assert len(rsi_signals) == len(feat_df)
        assert isinstance(ema_signals, np.ndarray)

        # When 回測引擎以自訂手續費費率 0.0006 執行推演
        engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.0006, confidence_threshold=0.002)
        results_df, perf = engine.run(feat_df, ema_signals)

        # Then 應回傳包含資產淨值曲線與績效指標字典的元組結構
        assert isinstance(results_df, pd.DataFrame)
        assert isinstance(perf, dict)
        assert "equity" in results_df.columns
        assert results_df["equity"].iloc[-1] > 0
        assert "Total Return (%)" in perf
        assert "Sharpe Ratio" in perf
        assert "Max Drawdown (%)" in perf

        # When 年度滾倉評估器傳入交易模型與年份
        evaluator = RollingBacktestEvaluator(initial_capital=100.0)
        rolling_res = evaluator.evaluate(
            model=ema_model,
            df=raw_df,
            symbol="BTC/USDT",
            period_description="BDD Test Year",
            train_model=False,
        )

        # Then 應回傳標準 RollingEvaluationResult 數據類別且可讀取期末淨值與年度收益率
        assert isinstance(rolling_res, RollingEvaluationResult)
        assert rolling_res.final_equity > 0
        assert isinstance(rolling_res.total_return_pct, float)
        assert isinstance(rolling_res.monthly_breakdown, pd.DataFrame)
