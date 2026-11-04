"""BDD Scenario Implementation Tests: backtest_out_of_sample_and_stop_accounting.feature."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

import packages.backtest.rolling_evaluator as rolling_module
from packages.backtest import BacktestEngine, RollingBacktestEvaluator
from packages.data import CCXTFetcher, DataManager
from packages.features import FeaturePipeline
from packages.models import DualEMACrossoverModel, LGBMAgent


def _frame(closes, natr=0.01) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC"),
        "close": np.asarray(closes, dtype=float),
        "natr_14": np.full(n, natr),
    })


class TestBacktestLeakageBDDScenarios:
    """BDD Step implementations matching backtest_out_of_sample_and_stop_accounting.feature."""

    def test_scenario_stop_bar_loss_is_booked(self):
        """Scenario: 觸發停損的 K 線虧損必須計入權益."""
        # Given 策略於收盤價 100 進場做多且 2 倍 ATR 停損位於 98 (frictionless for exact arithmetic)
        df = _frame([100.0, 100.0, 100.0, 90.0, 90.0])
        preds = np.full(len(df), 0.01)
        engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.0, slippage=0.0,
                                confidence_threshold=0.003, atr_stop_multiplier=2.0)

        # When 下一根 K 線收盤跌至 90 觸發停損
        res, _ = engine.run(df, preds)

        # Then 權益必須反映持倉期間 -10% 的虧損後才於收盤出場
        assert res["equity"].iloc[3] == pytest.approx(9000.0)
        assert res["strategy_return"].iloc[3] == pytest.approx(-0.10)
        # And 出場後不再持倉 (stopped-out lock until the signal resets)
        assert res["position"].iloc[4] == 0.0
        assert res["equity"].iloc[-1] == pytest.approx(9000.0)

    def test_scenario_returns_only_use_previous_signal_without_stops(self):
        """Scenario: 未觸發停損時每根 K 線報酬只由前一根的訊號決定."""
        rng = np.random.default_rng(3)
        closes = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.01, 300))
        df = _frame(closes)
        preds = rng.normal(0, 0.006, len(df))
        engine = BacktestEngine(fee_rate=0.0, slippage=0.0, allow_short=True, atr_stop_multiplier=1e9)

        res, _ = engine.run(df, preds)

        signals = res["signal"].to_numpy()
        asset_ret = np.r_[0.0, closes[1:] / closes[:-1] - 1.0]
        expected = np.r_[0.0, signals[:-1] * asset_ret[1:]]
        np.testing.assert_allclose(res["strategy_return"].to_numpy(), expected, atol=1e-12)

    def test_scenario_lgbm_cv_keeps_oof_and_early_stops_off_test_fold(self):
        """Scenario: LightGBM 交叉驗證保留樣本外預測且早停不使用測試折."""
        raw = CCXTFetcher().generate_mock_ohlcv(days=90, seed=11)
        features_df, cols = FeaturePipeline(target_horizon=3).build_features(raw)
        agent = LGBMAgent(num_boost_round=60)
        agent.train_cv(features_df, cols, target_col="target_forward_return", n_splits=4)

        # Then 早停驗證集必須取自訓練折尾端且與測試折完全不重疊並早於測試折
        assert agent.cv_fold_indices_
        for fold in agent.cv_fold_indices_:
            train, valid, test = fold["train"], fold["valid"], fold["test"]
            assert len(valid) > 0
            assert not set(valid) & set(test)
            assert valid.max() < test.min()
            assert train.max() < valid.min()

        # And 模型應提供僅含測試折的樣本外預測 (其餘列為 NaN)
        oos = agent.out_of_sample_predictions()
        assert oos is not None and len(oos) == len(features_df)
        tested = np.zeros(len(features_df), dtype=bool)
        for fold in agent.cv_fold_indices_:
            tested[fold["test"]] = True
        assert np.array_equal(np.isfinite(oos), tested)
        assert not tested[0]  # the first block is training history only
        # In-sample predictions of the final booster differ from honest out-of-fold ones.
        in_sample = agent.predict(features_df)
        assert not np.allclose(in_sample[tested], oos[tested])

    def test_scenario_rolling_evaluator_scores_only_unseen_rows(self, tmp_path, monkeypatch):
        """Scenario: 滾動回測只在模型未訓練過的資料上評分."""
        # Keep the evaluator's feature parquet cache out of the repository data/ folder.
        monkeypatch.setattr(
            rolling_module, "DataManager",
            lambda: DataManager(raw_dir=str(tmp_path / "raw"), processed_dir=str(tmp_path / "processed")),
        )
        raw = CCXTFetcher().generate_mock_ohlcv(days=90, seed=21)
        evaluator = RollingBacktestEvaluator(initial_capital=100.0)

        # Given 滾動回測評估器以 train_model=True 評估 LightGBM
        agent = LGBMAgent(num_boost_round=40)
        res = evaluator.evaluate(agent, raw, period_description="BDD_OOS_LGBM", train_model=True)

        # Then 評估範圍應為 "OUT_OF_SAMPLE" 且評估 K 線數等於樣本外預測數
        assert res.evaluation_scope == "OUT_OF_SAMPLE"
        oos = agent.out_of_sample_predictions()
        assert res.evaluated_bars == int(np.isfinite(oos).sum())
        # And 僅作訓練歷史的前段資料不得出現在回測權益曲線中
        features_df, _ = FeaturePipeline(target_horizon=3, label_threshold=0.005).build_features(raw)
        first_oos_ts = features_df.loc[np.isfinite(oos), "timestamp"].iloc[0]
        assert res.results_df["timestamp"].iloc[0] == first_oos_ts
        assert res.results_df["timestamp"].iloc[0] > features_df["timestamp"].iloc[0]

        # And 規則型策略不需訓練，評估範圍為 "NO_TRAINING" 並涵蓋全部資料
        rule = DualEMACrossoverModel(fast_span=12, slow_span=26)
        res_rule = evaluator.evaluate(rule, raw, period_description="BDD_OOS_RULE", train_model=True)
        assert res_rule.evaluation_scope == "NO_TRAINING"
        assert res_rule.evaluated_bars == len(features_df)
