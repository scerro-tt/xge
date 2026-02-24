from __future__ import annotations

from dataclasses import dataclass, asdict
from time import time
import json


def spot_to_perp(symbol: str) -> str:
    """Convert spot symbol to perpetual symbol. e.g. BTC/USDT -> BTC/USDT:USDT"""
    if ":" in symbol:
        return symbol
    quote = symbol.split("/")[1] if "/" in symbol else "USDT"
    return f"{symbol}:{quote}"


@dataclass
class FundingRateEntry:
    exchange: str
    symbol: str  # perp symbol, e.g. BTC/USDT:USDT
    spot_symbol: str  # e.g. BTC/USDT
    funding_rate: float
    funding_timestamp: float
    next_funding_timestamp: float | None = None
    next_funding_rate: float | None = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time()

    @property
    def annualized_rate(self) -> float:
        """Annualized funding rate assuming 3 payments/day (8h intervals)."""
        return self.funding_rate * 3 * 365 * 100

    @property
    def funding_rate_pct(self) -> float:
        """Funding rate as percentage."""
        return self.funding_rate * 100

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> FundingRateEntry:
        return cls(**json.loads(data))


@dataclass
class FundingRateSpread:
    symbol: str
    high_exchange: str
    low_exchange: str
    high_rate: float
    low_rate: float
    spread: float
    annualized_spread: float
    timestamp: float

    @classmethod
    def calculate(
        cls,
        entry_a: FundingRateEntry,
        entry_b: FundingRateEntry,
    ) -> FundingRateSpread:
        """Calculate funding rate spread between two exchanges.

        The strategy: short perps on the high-rate exchange,
        long perps on the low-rate exchange.
        """
        if entry_a.funding_rate >= entry_b.funding_rate:
            high, low = entry_a, entry_b
        else:
            high, low = entry_b, entry_a

        spread = high.funding_rate - low.funding_rate
        annualized = spread * 3 * 365 * 100

        return cls(
            symbol=entry_a.spot_symbol,
            high_exchange=high.exchange,
            low_exchange=low.exchange,
            high_rate=high.funding_rate,
            low_rate=low.funding_rate,
            spread=spread,
            annualized_spread=annualized,
            timestamp=time(),
        )


@dataclass
class SpotFundingArb:
    symbol: str
    exchange: str
    funding_rate: float
    annualized_rate: float
    direction: str  # "long_spot_short_perp" or "short_spot_long_perp"
    timestamp: float

    @classmethod
    def calculate(
        cls,
        entry: FundingRateEntry,
        min_annualized_pct: float = 5.0,
    ) -> SpotFundingArb | None:
        """Evaluate spot+perps basis trade opportunity.

        Positive funding: longs pay shorts -> go long spot, short perp.
        Negative funding: shorts pay longs -> go short spot, long perp.

        Returns None if annualized rate is below threshold.
        """
        annualized = entry.funding_rate * 3 * 365 * 100

        if abs(annualized) < min_annualized_pct:
            return None

        if entry.funding_rate > 0:
            direction = "long_spot_short_perp"
        else:
            direction = "short_spot_long_perp"

        return cls(
            symbol=entry.spot_symbol,
            exchange=entry.exchange,
            funding_rate=entry.funding_rate,
            annualized_rate=annualized,
            direction=direction,
            timestamp=time(),
        )
