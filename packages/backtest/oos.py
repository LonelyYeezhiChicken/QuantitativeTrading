"""Out-of-sample evaluation window selection (no backtest may score a model on its own training rows)."""

from typing import Tuple

import numpy as np
import pandas as pd

from packages.models.base import BaseTradingModel

SCOPE_OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
SCOPE_NO_TRAINING = "NO_TRAINING"


def select_evaluation_window(model: BaseTradingModel, features_df: pd.DataFrame) -> Tuple[pd.DataFrame, np.ndarray, str]:
    """Return (eval_df, predictions, scope) for a model that was just fit on `features_df`.

    - Learning models expose out-of-fold predictions; only rows they never trained on
      are kept (scope OUT_OF_SAMPLE). The leading rows that only ever served as training
      history are dropped from the backtest.
    - Models without out-of-sample predictions learn nothing from the data
      (rule-based) and are evaluated on every row (scope NO_TRAINING).
    """
    oos = model.out_of_sample_predictions()
    if oos is None:
        return features_df.reset_index(drop=True), np.asarray(model.predict(features_df)), SCOPE_NO_TRAINING

    oos = np.asarray(oos, dtype=float)
    if len(oos) != len(features_df):
        raise ValueError(
            f"Out-of-sample predictions ({len(oos)}) do not match the evaluated dataframe ({len(features_df)}); "
            "fit the model on the same dataframe that is being backtested."
        )
    mask = np.isfinite(oos)
    if not mask.any():
        raise ValueError("Model produced no out-of-sample predictions; increase the data length or CV folds.")
    eval_df = features_df.loc[mask].reset_index(drop=True)
    return eval_df, oos[mask], SCOPE_OUT_OF_SAMPLE
