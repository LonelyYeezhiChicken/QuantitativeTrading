"""Base interface for all Quantitative Trading Models and Strategies."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

class BaseTradingModel(ABC):
    """Abstract base class that all quant models/strategies must implement.
    
    Whether it's LightGBM, XGBoost, PyTorch LSTM, Reinforcement Learning,
    or a traditional rule-based strategy, implementing this interface allows
    plug-and-play evaluation in the modular backtest engine.
    """

    @property
    def name(self) -> str:
        """Name of the strategy/model for reports."""
        return self.__class__.__name__

    @abstractmethod
    def fit(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str = "target_forward_return",
        **kwargs,
    ) -> Dict[str, float]:
        """Train or calibrate the model on historical feature data."""
        pass

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Generate predicted returns or directional signal scores for input dataframe.

        Returns:
            np.ndarray: Predicted return values (e.g. 0.003 for +0.3% expected return)
                        or directional strength scores.
        """
        pass

    def out_of_sample_predictions(self) -> Optional[np.ndarray]:
        """Predictions for the rows of the last `fit` dataframe made by models that never saw them.

        Learning models MUST return their walk-forward / out-of-fold predictions here
        (NaN for rows that were never in a test fold) so that backtests never score a
        model on data it was trained on. Models that learn nothing from the data
        (rule-based strategies) return None and are evaluated with `predict` directly.
        """
        return None
