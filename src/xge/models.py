from __future__ import annotations

from dataclasses import dataclass, asdict
from time import time
import json


@dataclass
class OrderBookEntry:
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> OrderBookEntry:
        return cls(**json.loads(data))

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        if self.bid == 0:
            return 0.0
        return ((self.ask - self.bid) / self.bid) * 100


@dataclass
class SpreadInfo:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float   # ask on buy exchange
    sell_price: float   # bid on sell exchange
    spread_abs: float
    spread_pct: float
    net_spread: float   # after estimated fees
    timestamp: float

    buy_volume: float = 0.0   # ask volume on buy exchange
    sell_volume: float = 0.0  # bid volume on sell exchange

    @classmethod
    def calculate(
        cls,
        symbol: str,
        entry_a: OrderBookEntry,
        entry_b: OrderBookEntry,
        fee_a_pct: float = 0.1,
        fee_b_pct: float = 0.1,
    ) -> SpreadInfo | None:
        """Calculate the best spread between two exchange entries.

        Checks both directions and returns the profitable one, or None
        if no positive spread exists.
        """
        # Direction 1: buy on A (ask), sell on B (bid)
        spread_1 = entry_b.bid - entry_a.ask
        # Direction 2: buy on B (ask), sell on A (bid)
        spread_2 = entry_a.bid - entry_b.ask

        if spread_1 >= spread_2:
            buy_exchange, sell_exchange = entry_a.exchange, entry_b.exchange
            buy_price, sell_price = entry_a.ask, entry_b.bid
            buy_volume, sell_volume = entry_a.ask_volume, entry_b.bid_volume
            spread_abs = spread_1
        else:
            buy_exchange, sell_exchange = entry_b.exchange, entry_a.exchange
            buy_price, sell_price = entry_b.ask, entry_a.bid
            buy_volume, sell_volume = entry_b.ask_volume, entry_a.bid_volume
            spread_abs = spread_2

        if buy_price == 0:
            return None

        spread_pct = (spread_abs / buy_price) * 100
        total_fee_pct = fee_a_pct + fee_b_pct
        net_spread = spread_pct - total_fee_pct

        return cls(
            symbol=symbol,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_abs=spread_abs,
            spread_pct=spread_pct,
            net_spread=net_spread,
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            timestamp=time(),
        )
