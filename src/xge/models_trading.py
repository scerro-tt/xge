from __future__ import annotations

from dataclasses import dataclass, asdict, field
from time import time
import json


@dataclass
class TradeSignal:
    action: str  # "open" or "close"
    exchange: str
    symbol: str  # spot symbol, e.g. BTC/USDT
    perp_symbol: str  # e.g. BTC/USDT:USDT
    direction: str  # "long_spot_short_perp"
    size_usdt: float
    funding_rate: float
    annualized_rate: float
    reason: str
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> TradeSignal:
        return cls(**json.loads(data))


@dataclass
class LegFill:
    side: str  # "buy" or "sell"
    market_type: str  # "spot" or "perp"
    symbol: str
    price: float
    quantity: float
    fee: float
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> LegFill:
        return cls(**json.loads(data))


@dataclass
class Position:
    exchange: str
    symbol: str  # spot symbol
    perp_symbol: str
    direction: str  # "long_spot_short_perp"
    status: str  # "open" or "closed"
    size_usdt: float
    spot_entry_price: float = 0.0
    spot_quantity: float = 0.0
    spot_exit_price: float = 0.0
    perp_entry_price: float = 0.0
    perp_quantity: float = 0.0
    perp_exit_price: float = 0.0
    entry_funding_rate: float = 0.0
    entry_annualized_rate: float = 0.0
    funding_collected: float = 0.0
    last_funding_update: float = 0.0
    opened_at: float = 0.0
    closed_at: float = 0.0
    realized_pnl: float = 0.0
    paper: bool = True

    def __post_init__(self) -> None:
        if self.opened_at == 0.0:
            self.opened_at = time()
        if self.last_funding_update == 0.0:
            self.last_funding_update = self.opened_at

    @property
    def redis_key(self) -> str:
        return f"position:{self.exchange}:{self.symbol}"

    def calculate_pnl(self) -> float:
        """Calculate realized PnL for a closed position.

        For long_spot_short_perp:
        - Spot PnL: (exit - entry) * quantity
        - Perp PnL: (entry - exit) * quantity (short)
        - Plus funding collected
        """
        if self.status != "closed":
            return 0.0

        spot_pnl = (self.spot_exit_price - self.spot_entry_price) * self.spot_quantity
        perp_pnl = (self.perp_entry_price - self.perp_exit_price) * self.perp_quantity
        return spot_pnl + perp_pnl + self.funding_collected

    def estimate_unrealized_pnl(self, spot_price: float, perp_price: float) -> float:
        """Estimate unrealized PnL for an open position given current prices."""
        spot_pnl = (spot_price - self.spot_entry_price) * self.spot_quantity
        perp_pnl = (self.perp_entry_price - perp_price) * self.perp_quantity
        return spot_pnl + perp_pnl + self.funding_collected

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> Position:
        return cls(**json.loads(data))
