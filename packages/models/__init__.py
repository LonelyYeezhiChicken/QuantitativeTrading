"""Models Package: Trading Model Interfaces and Implementations."""

from packages.models.base import BaseTradingModel
from packages.models.dataset import PurgedTimeSeriesSplit
from packages.models.lgbm_agent import LGBMAgent
from packages.models.rule_based import DualEMACrossoverModel, RSIMomentumModel
from packages.models.typesafe_agent import TypeSafeAIAgent
from packages.models.advanced_strategies import (
    FibonacciSNRModel,
    SpotMomentumPullbackModel,
    SwapMultiRegimeModel,
    RSIBottomHunterModel,
    BollingerBreakoutModel,
)
from packages.models.ollama_agent import OllamaDecisionAgent
from packages.models.cloud_ai_agent import CloudAiDecisionAgent, get_ai_decision_agent

__all__ = [
    "BaseTradingModel",
    "PurgedTimeSeriesSplit",
    "LGBMAgent",
    "DualEMACrossoverModel",
    "RSIMomentumModel",
    "TypeSafeAIAgent",
    "FibonacciSNRModel",
    "SpotMomentumPullbackModel",
    "SwapMultiRegimeModel",
    "RSIBottomHunterModel",
    "BollingerBreakoutModel",
    "OllamaDecisionAgent",
    "CloudAiDecisionAgent",
    "get_ai_decision_agent",
]
