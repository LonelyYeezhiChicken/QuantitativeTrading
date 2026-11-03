"""Paper Broker: Simulates an exchange account for risk-free paper trading."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

class PaperBroker:
    """Simulated exchange broker managing cash, holdings, and order logs."""

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
        self.trade_history: List[Dict] = []
        
        self.load_state()

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

    def buy(self, symbol: str, current_price: float, usdt_amount: float) -> Optional[Dict]:
        """Execute a simulated Market Buy order."""
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
        """Execute a simulated Market Sell order."""
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
