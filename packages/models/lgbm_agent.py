"""LightGBM Agent for Multi-Factor Return Prediction using Native LightGBM API."""

from typing import Dict, List, Optional, Tuple
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from packages.models.base import BaseTradingModel
from packages.models.dataset import PurgedTimeSeriesSplit

class LGBMAgent(BaseTradingModel):
    """Trains and predicts asset forward returns using native LightGBM."""

    def __init__(self, params: Optional[Dict] = None, num_boost_round: int = 250):
        self.params = params or {
            "objective": "regression",
            "metric": "rmse",
            "boosting_type": "gbdt",
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "verbose": -1,
        }
        self.num_boost_round = num_boost_round
        self.booster: Optional[lgb.Booster] = None
        self.feature_names: List[str] = []
        self.feature_importances_: Optional[pd.DataFrame] = None

    @property
    def name(self) -> str:
        return "LightGBM_MultiFactor"

    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str = "target_forward_return",
        n_splits: int = 5,
        **kwargs,
    ) -> Dict[str, float]:
        """Standard interface for training the model using Purged TimeSeries CV."""
        return self.train_cv(df=df, feature_cols=feature_cols, target_col=target_col, n_splits=n_splits)

    def train_cv(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str = "target_forward_return",
        n_splits: int = 5,
    ) -> Dict[str, float]:
        """Train across Purged TimeSeries folds and calculate Out-Of-Fold metrics.

        Leakage guards:
        - Early stopping uses an inner validation slice carved from the END of each
          training fold (with a purge gap), never the test fold itself.
        - Out-of-fold predictions are kept in `oof_predictions_` so backtests can be
          scored strictly out of sample (see `out_of_sample_predictions`).
        """
        self.feature_names = feature_cols
        cv = PurgedTimeSeriesSplit(n_splits=n_splits)

        oof_preds = np.full(len(df), np.nan)
        oof_mask = np.zeros(len(df), dtype=bool)
        feature_importance_accum = np.zeros(len(feature_cols))

        fold_rmse = []
        fold_ic = []
        best_iterations: List[int] = []
        self.cv_fold_indices_: List[Dict[str, np.ndarray]] = []

        X = df[feature_cols].values
        y = df[target_col].values
        purge_size = max(1, int(len(df) * cv.purge_pct))

        for fold, (train_idx, test_idx) in enumerate(cv.split(df)):
            inner_train_idx, inner_valid_idx = self._inner_early_stopping_split(train_idx, purge_size)
            self.cv_fold_indices_.append({
                "train": inner_train_idx,
                "valid": inner_valid_idx,
                "test": test_idx,
            })

            if len(inner_valid_idx) > 0:
                train_data = lgb.Dataset(X[inner_train_idx], label=y[inner_train_idx], feature_name=feature_cols)
                valid_data = lgb.Dataset(
                    X[inner_valid_idx], label=y[inner_valid_idx], feature_name=feature_cols, reference=train_data
                )
                booster = lgb.train(
                    self.params,
                    train_data,
                    num_boost_round=self.num_boost_round,
                    valid_sets=[valid_data],
                    callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
                )
                if booster.best_iteration > 0:
                    best_iterations.append(int(booster.best_iteration))
            else:
                # Too little history for an inner split: fixed rounds, no early stopping.
                train_data = lgb.Dataset(X[train_idx], label=y[train_idx], feature_name=feature_cols)
                booster = lgb.train(self.params, train_data, num_boost_round=self.num_boost_round)

            X_test, y_test = X[test_idx], y[test_idx]
            preds = booster.predict(X_test)
            oof_preds[test_idx] = preds
            oof_mask[test_idx] = True

            rmse = float(np.sqrt(np.mean((y_test - preds) ** 2)))
            ic, _ = spearmanr(y_test, preds)
            fold_rmse.append(rmse)
            if not np.isnan(ic):
                fold_ic.append(float(ic))

            feature_importance_accum += booster.feature_importance(importance_type="gain")

        self.oof_predictions_ = oof_preds
        self.oof_mask_ = oof_mask

        # Final fit on entire historical dataset (for live / future inference only).
        # Its round count comes from the folds' early stopping, not from any test data.
        final_rounds = int(np.median(best_iterations)) if best_iterations else self.num_boost_round
        final_rounds = max(10, min(final_rounds, self.num_boost_round))
        full_train_data = lgb.Dataset(X, label=y, feature_name=feature_cols)
        self.booster = lgb.train(
            self.params,
            full_train_data,
            num_boost_round=final_rounds,
        )

        avg_importance = feature_importance_accum / max(len(fold_rmse), 1)
        self.feature_importances_ = pd.DataFrame({
            "feature": feature_cols,
            "importance": avg_importance
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        return {
            "avg_rmse": float(np.mean(fold_rmse)) if fold_rmse else 0.0,
            "avg_ic": float(np.mean(fold_ic)) if fold_ic else 0.0,
            "evaluated_samples": int(np.sum(oof_mask)),
            "final_boost_rounds": final_rounds,
        }

    @staticmethod
    def _inner_early_stopping_split(
        train_idx: np.ndarray, purge_size: int, valid_frac: float = 0.15, min_train: int = 50
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Split a training fold into (inner_train, inner_valid) taken from its tail, with a purge gap."""
        n = len(train_idx)
        valid_size = int(n * valid_frac)
        train_end = n - valid_size - purge_size
        if valid_size < 10 or train_end < min_train:
            return train_idx, np.array([], dtype=train_idx.dtype)
        return train_idx[:train_end], train_idx[n - valid_size:]

    def out_of_sample_predictions(self) -> Optional[np.ndarray]:
        """Out-of-fold predictions for the last `train_cv` dataframe (NaN where never tested)."""
        oof = getattr(self, "oof_predictions_", None)
        return None if oof is None else np.asarray(oof, dtype=float).copy()

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Generate forward return predictions for input dataframe."""
        if self.booster is None:
            raise ValueError("Model is not trained yet. Call fit() or train_cv() first.")
        X = df[self.feature_names].values
        return self.booster.predict(X)

    def get_top_features(self, n: int = 10) -> pd.DataFrame:
        """Return top N predictive features."""
        if self.feature_importances_ is None:
            return pd.DataFrame()
        return self.feature_importances_.head(n)
