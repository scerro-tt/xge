from __future__ import annotations

import json
from dataclasses import asdict
from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from xge.config import TradingConfig
from xge.models import OrderBookEntry
from xge.models_funding import FundingRateEntry
from xge.models_trading import Position, TradeSignal, LegFill
from xge.trading.strategy import BasisTradeStrategy
from xge.trading.executor import TradeExecutor
from xge.trading.position_manager import PositionManager
from xge.trading.delta_monitor import DeltaMonitor


def _make_funding_entry(
    exchange: str = "bitget",
    symbol: str = "BTC/USDT:USDT",
    spot_symbol: str = "BTC/USDT",
    funding_rate: float = 0.0005,
) -> FundingRateEntry:
    return FundingRateEntry(
        exchange=exchange,
        symbol=symbol,
        spot_symbol=spot_symbol,
        funding_rate=funding_rate,
        funding_timestamp=time(),
        timestamp=time(),
    )


def _make_order_book(
    exchange: str = "bitget",
    symbol: str = "BTC/USDT",
    bid: float = 50000.0,
    ask: float = 50010.0,
) -> OrderBookEntry:
    return OrderBookEntry(
        exchange=exchange,
        symbol=symbol,
        bid=bid,
        ask=ask,
        bid_volume=1.0,
        ask_volume=1.0,
        timestamp=time(),
    )


def _make_config(**overrides) -> TradingConfig:
    defaults = {
        "enabled": True,
        "paper_trading": True,
        "position_size_usdt": 315.0,
        "min_entry_annualized_pct": 10.0,
        "min_exit_annualized_pct": 3.0,
        "max_positions_per_exchange": 4,
        "max_total_positions": 6,
        "check_interval": 60,
        "exchanges": [],
    }
    defaults.update(overrides)
    return TradingConfig(**defaults)


def _make_strategy(
    cache: AsyncMock,
    executor: MagicMock | None = None,
    pm: MagicMock | None = None,
    config: TradingConfig | None = None,
    delta_monitor: DeltaMonitor | None = None,
) -> BasisTradeStrategy:
    if executor is None:
        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor._exchanges = {"bitget": MagicMock()}
        executor.execute_open = AsyncMock(
            return_value=(
                LegFill("buy", "spot", "BTC/USDT", 50000.0, 0.0063, 0.315, time()),
                LegFill("sell", "perp", "BTC/USDT:USDT", 50010.0, 0.0063, 0.315, time()),
            )
        )
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.0063, 0.315, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.0063, 0.315, time()),
            )
        )

    if pm is None:
        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(return_value=(True, "ok"))
        pm.save_position = AsyncMock()
        pm.get_all_positions = AsyncMock(return_value=[])
        pm.get_trade_history = AsyncMock(return_value=[])

    if config is None:
        config = _make_config()

    return BasisTradeStrategy(
        cache=cache,
        executor=executor,
        position_manager=pm,
        config=config,
        exchanges=["bitget"],
        symbols=["BTC/USDT"],
        funding_poll_interval=300,
        delta_monitor=delta_monitor,
    )


@pytest.mark.asyncio
class TestBasisTradeEntries:
    async def test_opens_when_funding_above_threshold(self):
        """Should open a position when funding rate exceeds entry threshold."""
        # funding_rate=0.0005 -> annualized = 0.0005 * 3 * 365 * 100 = 54.75%
        entry = _make_funding_entry(funding_rate=0.0005)
        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor._exchanges = {"bitget": MagicMock()}
        executor.execute_open = AsyncMock(
            return_value=(
                LegFill("buy", "spot", "BTC/USDT", 50000.0, 0.0063, 0.315, time()),
                LegFill("sell", "perp", "BTC/USDT:USDT", 50010.0, 0.0063, 0.315, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(return_value=(True, "ok"))
        pm.save_position = AsyncMock()
        pm.get_all_positions = AsyncMock(return_value=[])
        pm.get_trade_history = AsyncMock(return_value=[])

        # Patch validate_pair to always approve
        with patch("xge.trading.strategy.validate_pair", new_callable=AsyncMock) as mock_vp:
            mock_vp.return_value = {"approved": True, "reasons": []}
            strategy = _make_strategy(cache, executor, pm)
            await strategy._check_entries()

        executor.execute_open.assert_called_once()
        pm.save_position.assert_called_once()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "open"
        assert saved_pos.exchange == "bitget"
        assert saved_pos.symbol == "BTC/USDT"
        assert saved_pos.tier == "tier_1"

    async def test_no_entry_when_funding_below_threshold(self):
        """Should not open when funding rate is below entry threshold."""
        # funding_rate=0.00005 -> annualized = 5.475% < 10%
        entry = _make_funding_entry(funding_rate=0.00005)
        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(return_value=(True, "ok"))
        pm.get_all_positions = AsyncMock(return_value=[])
        pm.get_trade_history = AsyncMock(return_value=[])

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_entries()

        executor.execute_open.assert_not_called()

    async def test_no_entry_when_position_exists(self):
        """Should not open when a position already exists."""
        entry = _make_funding_entry(funding_rate=0.0005)
        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor._exchanges = {"bitget": MagicMock()}
        executor.execute_open = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(
            return_value=(False, "Position already exists"),
        )
        pm.get_all_positions = AsyncMock(return_value=[])
        pm.get_trade_history = AsyncMock(return_value=[])

        with patch("xge.trading.strategy.validate_pair", new_callable=AsyncMock) as mock_vp:
            mock_vp.return_value = {"approved": True, "reasons": []}
            strategy = _make_strategy(cache, executor, pm)
            await strategy._check_entries()

        executor.execute_open.assert_not_called()

    async def test_no_entry_when_negative_funding(self):
        """Should not open when funding rate is negative (only positive strategy)."""
        entry = _make_funding_entry(funding_rate=-0.0005)
        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock()

        pm = MagicMock(spec=PositionManager)

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_entries()

        executor.execute_open.assert_not_called()

    async def test_no_entry_when_blacklisted(self):
        """Should not open for blacklisted symbols."""
        entry = _make_funding_entry(
            funding_rate=0.0005, spot_symbol="OP/USDT", symbol="OP/USDT:USDT",
        )
        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock()

        pm = MagicMock(spec=PositionManager)

        strategy = BasisTradeStrategy(
            cache=cache,
            executor=executor,
            position_manager=pm,
            config=_make_config(),
            exchanges=["bitget"],
            symbols=["OP/USDT"],
            funding_poll_interval=300,
        )
        await strategy._check_entries()

        executor.execute_open.assert_not_called()


@pytest.mark.asyncio
class TestBasisTradeExits:
    async def test_closes_when_funding_drops(self):
        """Should close when funding drops below exit threshold."""
        # funding_rate=0.00002 -> annualized = 2.19% < 3%
        entry = _make_funding_entry(funding_rate=0.00002)

        position = Position(
            exchange="bitget",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=315.0,
            spot_entry_price=50000.0,
            spot_quantity=0.0063,
            perp_entry_price=50010.0,
            perp_quantity=0.0063,
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
            tier="tier_1",
            opened_at=time() - 10 * 3600,  # 10h ago — past min hold
        )

        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.0063, 0.315, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.0063, 0.315, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.save_position = AsyncMock()
        pm.get_trade_history = AsyncMock(return_value=[])

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_called_once()
        pm.save_position.assert_called()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "closed"
        assert saved_pos.exit_reason in ("funding_drop",)

    async def test_closes_when_funding_negative_2_periods(self):
        """Should close when funding is negative for 2 consecutive periods."""
        entry = _make_funding_entry(funding_rate=-0.0001)

        position = Position(
            exchange="bitget",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=315.0,
            spot_entry_price=50000.0,
            spot_quantity=0.0063,
            perp_entry_price=50010.0,
            perp_quantity=0.0063,
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
            tier="tier_1",
            opened_at=time() - 3600,  # 1h — under min hold, but stop/negative overrides
        )

        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.0063, 0.315, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.0063, 0.315, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.save_position = AsyncMock()
        pm.get_trade_history = AsyncMock(return_value=[])

        delta_monitor = DeltaMonitor(cache=cache, position_manager=pm)
        # Simulate 2nd negative period
        delta_monitor.track_negative_funding("bitget", "BTC/USDT", True)

        strategy = _make_strategy(cache, executor, pm, delta_monitor=delta_monitor)
        await strategy._check_exits()

        executor.execute_close.assert_called_once()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "closed"
        assert saved_pos.exit_reason == "funding_negative"

    async def test_no_exit_when_funding_still_high(self):
        """Should not close when funding is still above exit threshold."""
        # funding_rate=0.0003 -> annualized = 32.85% > 3%
        entry = _make_funding_entry(funding_rate=0.0003)

        position = Position(
            exchange="bitget",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=315.0,
            spot_entry_price=50000.0,
            spot_quantity=0.0063,
            perp_entry_price=50010.0,
            perp_quantity=0.0063,
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
            tier="tier_1",
        )

        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.get_trade_history = AsyncMock(return_value=[])

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_not_called()

    async def test_no_exit_before_min_hold_unless_stop(self):
        """Should not close before minimum hold period unless stop loss."""
        # funding rate dropped but position is too new
        entry = _make_funding_entry(funding_rate=0.00002)  # below threshold

        position = Position(
            exchange="bitget",
            symbol="BTC/USDT",
            perp_symbol="BTC/USDT:USDT",
            direction="long_spot_short_perp",
            status="open",
            size_usdt=315.0,
            spot_entry_price=50000.0,
            spot_quantity=0.0063,
            perp_entry_price=50010.0,
            perp_quantity=0.0063,
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
            tier="tier_1",
            opened_at=time() - 3600,  # Only 1h ago — under 8h minimum
        )

        book = _make_order_book()

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())
        cache.get_latest = AsyncMock(return_value=book.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.get_trade_history = AsyncMock(return_value=[])

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_not_called()
