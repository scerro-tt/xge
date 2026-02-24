from xge.models_trading import TradeSignal, LegFill, Position


class TestTradeSignal:
    def test_serialization(self):
        signal = TradeSignal(
            action="open",
            exchange="binance",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            size_usdt=100.0,
            funding_rate=0.0003,
            annualized_rate=32.85,
            reason="funding above threshold",
            timestamp=1000000.0,
        )
        json_str = signal.to_json()
        restored = TradeSignal.from_json(json_str)
        assert restored.action == "open"
        assert restored.exchange == "binance"
        assert restored.symbol == "BTC/USDT"
        assert restored.size_usdt == 100.0
        assert restored.funding_rate == 0.0003

    def test_auto_timestamp(self):
        signal = TradeSignal(
            action="close",
            exchange="bybit",
            symbol="ETH/USDT",
            perp_symbol="ETH/USDT:USDT",
            direction="long_spot_short_perp",
            size_usdt=100.0,
            funding_rate=0.0001,
            annualized_rate=10.95,
            reason="funding below threshold",
        )
        assert signal.timestamp > 0


class TestLegFill:
    def test_serialization(self):
        fill = LegFill(
            side="buy",
            market_type="spot",
            symbol="BTC/USDT",
            price=50000.0,
            quantity=0.002,
            fee=0.1,
            timestamp=1000000.0,
        )
        json_str = fill.to_json()
        restored = LegFill.from_json(json_str)
        assert restored.side == "buy"
        assert restored.market_type == "spot"
        assert restored.price == 50000.0
        assert restored.quantity == 0.002


class TestPosition:
    def test_redis_key(self):
        pos = Position(
            exchange="binance",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=100.0,
        )
        assert pos.redis_key == "position:binance:BTC/USDT"

    def test_serialization(self):
        pos = Position(
            exchange="binance",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=100.0,
            spot_entry_price=50000.0,
            spot_quantity=0.002,
            perp_entry_price=50010.0,
            perp_quantity=0.002,
            entry_funding_rate=0.0003,
            entry_annualized_rate=32.85,
            opened_at=1000000.0,
        )
        json_str = pos.to_json()
        restored = Position.from_json(json_str)
        assert restored.exchange == "binance"
        assert restored.status == "open"
        assert restored.spot_entry_price == 50000.0
        assert restored.paper is True

    def test_calculate_pnl_closed(self):
        pos = Position(
            exchange="binance",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="closed",
            size_usdt=100.0,
            spot_entry_price=50000.0,
            spot_quantity=0.002,
            spot_exit_price=50100.0,
            perp_entry_price=50010.0,
            perp_quantity=0.002,
            perp_exit_price=50110.0,
            funding_collected=0.5,
            opened_at=1000000.0,
            closed_at=1000100.0,
        )
        pnl = pos.calculate_pnl()
        # spot: (50100 - 50000) * 0.002 = 0.2
        # perp: (50010 - 50110) * 0.002 = -0.2
        # funding: 0.5
        # total: 0.5
        assert abs(pnl - 0.5) < 0.0001

    def test_calculate_pnl_open_returns_zero(self):
        pos = Position(
            exchange="binance",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=100.0,
        )
        assert pos.calculate_pnl() == 0.0
