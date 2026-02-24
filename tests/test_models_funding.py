from time import time

from xge.models_funding import (
    FundingRateEntry,
    FundingRateSpread,
    SpotFundingArb,
    spot_to_perp,
)


def test_spot_to_perp():
    assert spot_to_perp("BTC/USDT") == "BTC/USDT:USDT"
    assert spot_to_perp("ETH/USDC") == "ETH/USDC:USDC"
    # Already a perp symbol
    assert spot_to_perp("BTC/USDT:USDT") == "BTC/USDT:USDT"


def test_funding_rate_entry_creation():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
    )
    assert entry.exchange == "binance"
    assert entry.funding_rate == 0.0001
    assert entry.timestamp > 0


def test_funding_rate_entry_annualized():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
    )
    # 0.0001 * 3 * 365 * 100 = 10.95%
    assert abs(entry.annualized_rate - 10.95) < 0.01


def test_funding_rate_entry_pct():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
    )
    assert abs(entry.funding_rate_pct - 0.01) < 1e-6


def test_funding_rate_entry_serialization():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
        next_funding_timestamp=1700028800.0,
        next_funding_rate=0.00015,
        timestamp=1700000000.0,
    )
    json_str = entry.to_json()
    restored = FundingRateEntry.from_json(json_str)
    assert restored.exchange == entry.exchange
    assert restored.funding_rate == entry.funding_rate
    assert restored.next_funding_rate == entry.next_funding_rate
    assert restored.timestamp == entry.timestamp


def test_funding_rate_spread():
    entry_a = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0003,
        funding_timestamp=1700000000.0,
    )
    entry_b = FundingRateEntry(
        exchange="bybit",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
    )
    spread = FundingRateSpread.calculate(entry_a, entry_b)
    assert spread.high_exchange == "binance"
    assert spread.low_exchange == "bybit"
    assert abs(spread.spread - 0.0002) < 1e-8
    # 0.0002 * 3 * 365 * 100 = 21.9%
    assert abs(spread.annualized_spread - 21.9) < 0.01


def test_funding_rate_spread_reversed():
    """Ensure spread always identifies high/low correctly."""
    entry_a = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0001,
        funding_timestamp=1700000000.0,
    )
    entry_b = FundingRateEntry(
        exchange="bybit",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0003,
        funding_timestamp=1700000000.0,
    )
    spread = FundingRateSpread.calculate(entry_a, entry_b)
    assert spread.high_exchange == "bybit"
    assert spread.low_exchange == "binance"


def test_spot_funding_arb_positive_rate():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.0002,
        funding_timestamp=1700000000.0,
    )
    arb = SpotFundingArb.calculate(entry, min_annualized_pct=5.0)
    assert arb is not None
    assert arb.direction == "long_spot_short_perp"
    # 0.0002 * 3 * 365 * 100 = 21.9%
    assert arb.annualized_rate > 5.0


def test_spot_funding_arb_negative_rate():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=-0.0002,
        funding_timestamp=1700000000.0,
    )
    arb = SpotFundingArb.calculate(entry, min_annualized_pct=5.0)
    assert arb is not None
    assert arb.direction == "short_spot_long_perp"


def test_spot_funding_arb_below_threshold():
    entry = FundingRateEntry(
        exchange="binance",
        symbol="BTC/USDT:USDT",
        spot_symbol="BTC/USDT",
        funding_rate=0.00001,  # ~1.095% annualized
        funding_timestamp=1700000000.0,
    )
    arb = SpotFundingArb.calculate(entry, min_annualized_pct=5.0)
    assert arb is None
