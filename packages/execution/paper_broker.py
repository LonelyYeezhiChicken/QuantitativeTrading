"""Paper Broker: Simulates an exchange account for risk-free paper trading."""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.execution.base import BaseBrokerGateway, MarketType


class PaperBroker(BaseBrokerGateway):
    """Simulated exchange broker implementing universal BaseBrokerGateway."""

    def __init__(
        self,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.0005,
        slippage: float = 0.0002,
        state_file: str = "data/paper_account_state.json",
    ):
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.state_file = Path(state_file)

        self.cash = initial_balance
        self.positions: Dict[str, Dict[str, float]] = {}
        self.trade_history: List[Dict[str, Any]] = []
        self._last_prices: Dict[str, float] = {"BTC/USDT": 77400.0, "ETH/USDT": 2700.0, "SOL/USDT": 180.0}

        self.load_state()

    @property
    def exchange_name(self) -> str:
        return "PaperBroker"

    @property
    def is_dry_run(self) -> bool:
        return True

    @property
    def default_market_type(self) -> str:
        return MarketType.SPOT.value

    def load_state(self):
        """Load account state from file if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cash = data.get("cash", self.initial_balance)
                    self.positions = data.get("positions", {})
                    self.trade_history = data.get("trade_history", [])
            except Exception as e:
                print(f"[Warning] Failed to load paper state: {e}")

    def save_state(self):
        """Save account state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cash": self.cash,
            "positions": self.positions,
            "trade_history": self.trade_history,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_balance(self, asset: str = "USDT", market_type: Optional[str] = None) -> float:
        """Get available / free balance of given asset."""
        clean_asset = asset.upper()
        if clean_asset in ("USDT", "USD"):
            return float(self.cash)
        for sym, pos in self.positions.items():
            if clean_asset in sym:
                return float(pos.get("amount", 0.0))
        return 0.0

    def fetch_ticker(self, symbol: str, market_type: Optional[str] = None) -> Dict[str, Any]:
        """Fetch simulated ticker price."""
        p = self._last_prices.get(symbol, 77400.0)
        return {
            "price": p,
            "bid": p * (1.0 - self.slippage),
            "ask": p * (1.0 + self.slippage),
            "change_24h_pct": 1.5,
            "high_24h": p * 1.02,
            "low_24h": p * 0.98,
            "timestamp": int(time.time() * 1000),
            "source": "PAPER_SIMULATOR",
        }

    def set_mock_price(self, symbol: str, price: float):
        """Helper to inject price for simulation and testing."""
        self._last_prices[symbol] = price

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
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a simulated order conforming to BaseBrokerGateway."""
        side = side.upper()
        cur_p = price or self._last_prices.get(symbol, 77400.0)
        order_id = client_order_id or f"paper_{uuid.uuid4().hex[:12]}"

        if side == "BUY":
            slip_mult = 1.0 + self.slippage
            exec_price = cur_p * slip_mult
            gross_cost = size * exec_price
            margin_required = gross_cost / max(1, leverage)
            fee = gross_cost * self.fee_rate
            total_cash_needed = margin_required + fee

            if self.cash < total_cash_needed:
                return {
                    "result": False,
                    "msg": f"Insufficient funds: available ${self.cash:.2f} < needed ${total_cash_needed:.2f}",
                    "data": {},
                }

            self.cash -= total_cash_needed
            pos = self.positions.get(symbol, {"amount": 0.0, "avg_price": 0.0, "leverage": leverage})
            total_amt = pos.get("amount", 0.0) + size
            new_avg = (
                ((pos.get("amount", 0.0) * pos.get("avg_price", 0.0)) + (size * exec_price)) / total_amt
                if total_amt > 0 else exec_price
            )
            self.positions[symbol] = {
                "amount": total_amt,
                "avg_price": new_avg,
                "leverage": leverage,
                "side": position_side or "LONG",
            }

            trade_record = {
                "order_id": order_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "side": "BUY",
                "price": exec_price,
                "quantity": size,
                "notional": gross_cost,
                "fee": fee,
                "leverage": leverage,
                "market_type": market_type or MarketType.SPOT.value,
            }
            self.trade_history.append(trade_record)
            self.save_state()

            return {
                "result": True,
                "data": {
                    "orderId": order_id,
                    "symbol": symbol,
                    "side": "BUY",
                    "price": exec_price,
                    "origQty": size,
                    "executedQty": size,
                    "status": "FILLED",
                },
            }

        elif side == "SELL":
            slip_mult = 1.0 - self.slippage
            exec_price = cur_p * slip_mult
            pos = self.positions.get(symbol, {"amount": 0.0, "avg_price": 0.0, "leverage": leverage})
            avail_qty = pos.get("amount", 0.0)
            qty_to_sell = min(avail_qty, size)

            if qty_to_sell <= 0:
                return {
                    "result": False,
                    "msg": f"No open position in {symbol} to sell",
                    "data": {},
                }

            gross_value = qty_to_sell * exec_price
            fee = gross_value * self.fee_rate
            margin_returned = (qty_to_sell * pos.get("avg_price", exec_price)) / max(1, pos.get("leverage", leverage))
            pnl = (exec_price - pos.get("avg_price", exec_price)) * qty_to_sell
            net_returned = margin_returned + pnl - fee

            self.cash += max(0.0, net_returned)
            remaining_qty = avail_qty - qty_to_sell
            if remaining_qty < 1e-8:
                self.positions.pop(symbol, None)
            else:
                self.positions[symbol]["amount"] = remaining_qty

            trade_record = {
                "order_id": order_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "side": "SELL",
                "price": exec_price,
                "quantity": qty_to_sell,
                "notional": gross_value,
                "fee": fee,
                "realized_pnl": pnl,
                "market_type": market_type or MarketType.SPOT.value,
            }
            self.trade_history.append(trade_record)
            self.save_state()

            return {
                "result": True,
                "data": {
                    "orderId": order_id,
                    "symbol": symbol,
                    "side": "SELL",
                    "price": exec_price,
                    "origQty": qty_to_sell,
                    "executedQty": qty_to_sell,
                    "status": "FILLED",
                    "realizedPnl": pnl,
                },
            }

        return {"result": False, "msg": f"Unsupported side: {side}", "data": {}}

    def cancel_order(self, symbol: str, order_id: str, market_type: Optional[str] = None) -> bool:
        """Cancel an open order (simulated orders are immediate)."""
        return True

    def get_open_orders(self, symbol: str, market_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve list of active open orders (empty in instant fill simulator)."""
        return []

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve open contract / swap positions."""
        results = []
        for sym, pos in self.positions.items():
            if symbol and sym != symbol:
                continue
            amt = pos.get("amount", 0.0)
            if amt > 0:
                results.append({
                    "symbol": sym,
                    "positionSide": pos.get("side", "LONG"),
                    "positionAmt": amt,
                    "entryPrice": pos.get("avg_price", 0.0),
                    "leverage": pos.get("leverage", 1),
                    "unrealizedProfit": 0.0,
                })
        return results

    # ================= Backward-Compatible Methods =================
    def buy(self, symbol: str, current_price: float, usdt_amount: float) -> Optional[Dict]:
        """Execute a simulated Market Buy order (backward compatibility)."""
        if usdt_amount <= 0 or self.cash < usdt_amount:
            return None

        exec_price = current_price * (1.0 + self.slippage)
        fee = usdt_amount * self.fee_rate
        net_spend = usdt_amount - fee
        qty_bought = net_spend / exec_price

        self.cash -= usdt_amount

        pos = self.positions.get(symbol, {"amount": 0.0, "avg_price": 0.0})
        total_amount = pos["amount"] + qty_bought
        new_avg_price = (
            ((pos["amount"] * pos["avg_price"]) + (qty_bought * exec_price)) / total_amount
            if total_amount > 0 else exec_price
        )

        self.positions[symbol] = {
            "amount": total_amount,
            "avg_price": new_avg_price,
        }

        trade_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "side": "BUY",
            "price": exec_price,
            "quantity": qty_bought,
            "notional": usdt_amount,
            "fee": fee,
        }
        self.trade_history.append(trade_record)
        self.save_state()
        return trade_record

    def sell(self, symbol: str, current_price: float, pct_position: float = 1.0) -> Optional[Dict]:
        """Execute a simulated Market Sell order (backward compatibility)."""
        pos = self.positions.get(symbol, {"amount": 0.0, "avg_price": 0.0})
        qty_to_sell = pos["amount"] * max(0.0, min(1.0, pct_position))

        if qty_to_sell <= 0:
            return None

        exec_price = current_price * (1.0 - self.slippage)
        gross_value = qty_to_sell * exec_price
        fee = gross_value * self.fee_rate
        net_proceeds = gross_value - fee

        cost_basis = qty_to_sell * pos["avg_price"]
        pnl = net_proceeds - cost_basis

        self.cash += net_proceeds
        remaining_amount = pos["amount"] - qty_to_sell

        if remaining_amount < 1e-8:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol]["amount"] = remaining_amount

        trade_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "side": "SELL",
            "price": exec_price,
            "quantity": qty_to_sell,
            "notional": net_proceeds,
            "fee": fee,
            "realized_pnl": pnl,
        }
        self.trade_history.append(trade_record)
        self.save_state()
        return trade_record

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total account equity (Cash + Unrealized Asset Value)."""
        total = self.cash
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos["avg_price"])
            total += pos["amount"] * price
        return total

    def summary(self, current_prices: Dict[str, float]) -> Dict:
        """Return human-readable summary of paper account."""
        total_val = self.get_portfolio_value(current_prices)
        total_pnl = total_val - self.initial_balance
        pnl_pct = (total_pnl / self.initial_balance) * 100.0

        return {
            "cash_usdt": round(self.cash, 2),
            "portfolio_value_usdt": round(total_val, 2),
            "total_pnl_usdt": round(total_pnl, 2),
            "total_pnl_pct": f"{pnl_pct:+.2f}%",
            "open_positions": self.positions,
            "total_trades": len(self.trade_history),
        }
