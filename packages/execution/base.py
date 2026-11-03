"""Abstract Base Broker Gateway for all Live and Paper Exchanges."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class MarketType(str, Enum):
    """Trading market type distinction."""
    SPOT = "SPOT"      # 現貨交易 (Spot Asset Trading)
    SWAP = "SWAP"      # 永續合約 (Perpetual Futures / Swap)


class BaseBrokerGateway(ABC):
    """Universal interface that all exchange gateways (Pionex, BingX, Paper) must implement."""

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Name of the broker / exchange."""
        pass

    @property
    @abstractmethod
    def is_dry_run(self) -> bool:
        """True if operating in simulated dry-run mode, False if live."""
        pass

    @property
    def default_market_type(self) -> str:
        """Default market type ('SPOT' or 'SWAP'). Defaults to SPOT."""
        return MarketType.SPOT.value

    @abstractmethod
    def get_balance(self, asset: str = "USDT", market_type: Optional[str] = None) -> float:
        """Get available / free balance of a given asset for SPOT or SWAP."""
        pass

    @abstractmethod
    def fetch_ticker(self, symbol: str, market_type: Optional[str] = None) -> Dict[str, float]:
        """Fetch current ticker price: returns {'price': float, 'bid': float, 'ask': float, 'timestamp': int}."""
        pass

    @abstractmethod
    def create_order(
        self,
        symbol: str,
        side: str,                            # 'BUY' or 'SELL'
        order_type: str,                      # 'LIMIT' or 'MARKET'
        size: float,                          # Base asset quantity (e.g. BTC amount)
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
        market_type: Optional[str] = None,     # 'SPOT' or 'SWAP'
        position_side: str = "LONG",          # 'LONG' or 'SHORT' (for SWAP)
        leverage: int = 1,                    # Leverage multiplier (for SWAP)
    ) -> Dict[str, Any]:
        """Create and submit an order (supports both SPOT and SWAP)."""
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str, market_type: Optional[str] = None) -> bool:
        """Cancel an open order by ID."""
        pass

    @abstractmethod
    def get_open_orders(self, symbol: str, market_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve list of active open orders for symbol."""
        pass

    # ================= Optional Contract / Swap Specific Methods =================

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve open contract / swap positions (LONG / SHORT)."""
        return []

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for perpetual swap contract."""
        return True

    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> bool:
        """Set margin type ('ISOLATED' or 'CROSSED') for swap contract."""
        return True
