from time import time

from xge.models import OrderBookEntry, SpreadInfo


def test_order_book_entry_creation():
    entry = OrderBookEntry(
        exchange="binance",
        symbol="BTC/USDT",
        bid=50000.0,
        ask=50010.0,
        bid_volume=1.5,
        ask_volume=2.0,
        timestamp=time(),
    )
    assert entry.exchange == "binance"
    assert entry.symbol == "BTC/USDT"
    assert entry.mid_price == 50005.0
    assert entry.spread_pct > 0


def test_order_book_entry_serialization():
    entry = OrderBookEntry(
        exchange="kraken",
        symbol="ETH/USDT",
        bid=3000.0,
        ask=3001.0,
        bid_volume=10.0,
        ask_volume=5.0,
        timestamp=1700000000.0,
    )
    json_str = entry.to_json()
    restored = OrderBookEntry.from_json(json_str)
    assert restored.exchange == entry.exchange
    assert restored.bid == entry.bid
    assert restored.ask == entry.ask


def test_spread_calculation():
    entry_a = OrderBookEntry(
        exchange="binance",
        symbol="BTC/USDT",
        bid=50000.0,
        ask=50010.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )
    entry_b = OrderBookEntry(
        exchange="kraken",
        symbol="BTC/USDT",
        bid=50050.0,
        ask=50060.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )

    spread = SpreadInfo.calculate(
        "BTC/USDT", entry_a, entry_b,
        fee_a_pct=0.1, fee_b_pct=0.1,
    )
    assert spread is not None
    # Buy on binance (ask=50010), sell on kraken (bid=50050)
    assert spread.buy_exchange == "binance"
    assert spread.sell_exchange == "kraken"
    assert spread.spread_abs == 40.0  # 50050 - 50010
    assert spread.spread_pct > 0
    # Net spread = spread_pct - 0.2% (0.1% fee each side)
    assert spread.net_spread < spread.spread_pct


def test_spread_no_opportunity():
    # Same prices, no meaningful spread
    entry_a = OrderBookEntry(
        exchange="binance",
        symbol="BTC/USDT",
        bid=50000.0,
        ask=50010.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )
    entry_b = OrderBookEntry(
        exchange="kraken",
        symbol="BTC/USDT",
        bid=50000.0,
        ask=50010.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )

    spread = SpreadInfo.calculate(
        "BTC/USDT", entry_a, entry_b,
        fee_a_pct=0.1, fee_b_pct=0.1,
    )
    assert spread is not None
    # With identical prices, net spread should be negative (fees eat it)
    assert spread.net_spread < 0


def test_spread_asymmetric_fees():
    """Binance 0.1% + Kraken 0.26% = 0.36% total fee."""
    entry_a = OrderBookEntry(
        exchange="binance",
        symbol="BTC/USDT",
        bid=50000.0,
        ask=50010.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )
    entry_b = OrderBookEntry(
        exchange="kraken",
        symbol="BTC/USDT",
        bid=50050.0,
        ask=50060.0,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )

    spread = SpreadInfo.calculate(
        "BTC/USDT", entry_a, entry_b,
        fee_a_pct=0.1, fee_b_pct=0.26,
    )
    assert spread is not None
    assert spread.buy_exchange == "binance"
    assert spread.sell_exchange == "kraken"
    # spread_pct = (40 / 50010) * 100 ~= 0.07998%
    expected_spread_pct = (40.0 / 50010.0) * 100
    assert abs(spread.spread_pct - expected_spread_pct) < 1e-6
    # net_spread = spread_pct - (0.1 + 0.26) = spread_pct - 0.36
    expected_net = expected_spread_pct - 0.36
    assert abs(spread.net_spread - expected_net) < 1e-6
