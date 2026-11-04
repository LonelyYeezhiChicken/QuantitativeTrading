"""BDD Scenario Implementation Tests: Zero Data Leakage & Lookahead Bias Prevention."""

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
from packages.models.dataset import PurgedTimeSeriesSplit


class TestZeroDataLeakageBDDScenarios:
    """BDD Step implementations matching zero_data_leakage.feature."""

    def test_scenario_future_data_perturbation_does_not_affect_past_features(self):
        """Scenario: 未來價格數據異動時歷史特徵嚴格保持不變（無前視偏差）"""
        # Given 系統採集了標準 30 天歷史時序 OHLCV 行情數據
        fetcher = CCXTFetcher()
        df_history = fetcher.generate_mock_ohlcv(days=30, seed=100)
        df_future_perturbed = df_history.copy()

        # When 刻意對未來最後 5 根 K 棒的收盤價與最高價進行大幅擾動
        df_future_perturbed.iloc[-5:, df_future_perturbed.columns.get_loc("close")] *= 2.5
        df_future_perturbed.iloc[-5:, df_future_perturbed.columns.get_loc("high")] *= 2.5

        pipeline = FeaturePipeline(target_horizon=3)
        feat_clean, feature_cols = pipeline.build_features(df_history)
        feat_perturbed, _ = pipeline.build_features(df_future_perturbed)

        # Then 在擾動切分點之前的歷史技術因子數值應完全精確一致（差異為 0）
        cutoff = len(feat_clean) - 10
        for col in feature_cols:
            val_clean = feat_clean[col].iloc[:cutoff].values
            val_perturbed = feat_perturbed[col].iloc[:cutoff].values
            np.testing.assert_allclose(
                val_clean,
                val_perturbed,
                rtol=1e-5,
                atol=1e-8,
                err_msg=f"Data leakage detected in factor '{col}'!",
            )

        # And 證明所有 Alpha 因子均未讀取未來時序數據
        assert len(feature_cols) >= 10
        assert "target_forward_return" not in feature_cols

    def test_scenario_prediction_label_forward_shift(self):
        """Scenario: 預測標籤採用未來位移且絕不包含當前資訊外洩"""
        # Given 特徵工程流水線配置預測週期為 3 期 (target_horizon=3)
        pipeline = FeaturePipeline(target_horizon=3)
        fetcher = CCXTFetcher()
        df = fetcher.generate_mock_ohlcv(days=15, seed=42)

        # When 系統構建特徵資料集與預測目標 target_forward_return
        df_ref = df[["timestamp", "close"]].copy()
        df_ref["expected_target"] = (df_ref["close"].shift(-3) - df_ref["close"]) / df_ref["close"]
        features_df, feature_cols = pipeline.build_features(df)

        # Then 預測目標數值應嚴格使用未來收益率位移 (shift(-3))
        merged = pd.merge(features_df, df_ref[["timestamp", "expected_target"]], on="timestamp")
        assert len(merged) > 0
        np.testing.assert_allclose(
            merged["target_forward_return"].values,
            merged["expected_target"].values,
            rtol=1e-5,
            atol=1e-8,
        )

        # And 當前 K 棒的特徵集合中絕不包含未來收盤價
        for col in feature_cols:
            assert "future" not in col.lower()
            assert col != "target_forward_return"
            assert col != "target_direction"

    def test_scenario_purged_timeseries_cross_validation(self):
        """Scenario: Purged K-Fold 時序交叉驗證具備緩衝隔離帶 (Purge 與 Embargo)"""
        # Given 歷史資料集包含 1000 筆時序觀測樣本
        n_samples = 1000
        dummy_df = pd.DataFrame({"close": np.linspace(100, 200, n_samples)})

        # When 啟用具備 2% Purge 與 1% Embargo 之時序交叉驗證切分器 (PurgedTimeSeriesSplit)
        splitter = PurgedTimeSeriesSplit(n_splits=5, purge_pct=0.02, embargo_pct=0.01)
        splits = list(splitter.split(dummy_df))

        # Then 訓練集的最大時間索引必須早於驗證集的起始時間索引減去 Purge 緩衝區
        purge_size = int(n_samples * 0.02)
        assert len(splits) > 0
        for train_idx, test_idx in splits:
            max_train = np.max(train_idx)
            min_test = np.min(test_idx)
            # Training must strictly end before testing begins with purge gap
            assert max_train <= min_test - purge_size

        # And 各 Fold 之間絕不發生時序重疊或未來資訊洩漏
        for train_idx, test_idx in splits:
            overlap = set(train_idx).intersection(set(test_idx))
            assert len(overlap) == 0
