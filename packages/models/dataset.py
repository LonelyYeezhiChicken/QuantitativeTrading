"""Purged TimeSeries Cross-Validation for Financial Machine Learning."""

from typing import Generator, Tuple
import numpy as np
import pandas as pd

class PurgedTimeSeriesSplit:
    """Time-series cross-validator with purge and embargo buffers to prevent data leakage.
    
    Ref: Marcos Lopez de Prado, 'Advances in Financial Machine Learning' (2018).
    """

    def __init__(self, n_splits: int = 5, purge_pct: float = 0.02, embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(self, df: pd.DataFrame) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """Yield (train_indices, test_indices) for each fold."""
        n_samples = len(df)
        indices = np.arange(n_samples)
        
        test_size = n_samples // (self.n_splits + 1)
        purge_size = int(n_samples * self.purge_pct)
        embargo_size = int(n_samples * self.embargo_pct)

        for i in range(self.n_splits):
            test_start = (i + 1) * test_size
            test_end = test_start + test_size if i < self.n_splits - 1 else n_samples
            
            train_end = max(0, test_start - purge_size)
            train_indices = indices[:train_end]
            test_indices = indices[test_start:test_end]

            if len(train_indices) == 0 or len(test_indices) == 0:
                continue

            yield train_indices, test_indices
