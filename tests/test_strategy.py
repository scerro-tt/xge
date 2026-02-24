from __future__ import annotations

import json
from dataclasses import asdict
from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from xge.config import TradingConfig
from xge.models_funding import FundingRateEntry
from xge.models_trading import Position, TradeSignal, LegFill
from xge.trading.strategy import BasisTradeStrategy
from xge.trading.executor import TradeExecutor
from xge.trading.position_manager import PositionManager


def _make_funding_entry(
    exchange: str = "binance",
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


def _make_config(**overrides) -> TradingConfig:
    defaults = {
        "enabled": True,
        "paper_trading": True,
        "position_size_usdt": 100.0,
        "min_entry_annualized_pct": 10.0,
        "min_exit_annualized_pct": 3.0,
        "max_positions_per_exchange": 3,
        "max_total_positions": 10,
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
) -> BasisTradeStrategy:
    if executor is None:
        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock(
            return_value=(
                LegFill("buy", "spot", "BTC/USDT", 50000.0, 0.002, 0.1, time()),
                LegFill("sell", "perp", "BTC/USDT:USDT", 50010.0, 0.002, 0.1, time()),
            )
        )
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.002, 0.1, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.002, 0.1, time()),
            )
        )

    if pm is None:
        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(return_value=(True, "ok"))
        pm.save_position = AsyncMock()
        pm.get_all_positions = AsyncMock(return_value=[])

    if config is None:
        config = _make_config()

    return BasisTradeStrategy(
        cache=cache,
        executor=executor,
        position_manager=pm,
        config=config,
        exchanges=["binance"],
        symbols=["BTC/USDT"],
        funding_poll_interval=300,
    )


@pytest.mark.asyncio
class TestBasisTradeEntries:
    async def test_opens_when_funding_above_threshold(self):
        """Should open a position when funding rate exceeds entry threshold."""
        # funding_rate=0.0005 -> annualized = 0.0005 * 3 * 365 * 100 = 54.75%
        entry = _make_funding_entry(funding_rate=0.0005)
        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock(
            return_value=(
                LegFill("buy", "spot", "BTC/USDT", 50000.0, 0.002, 0.1, time()),
                LegFill("sell", "perp", "BTC/USDT:USDT", 50010.0, 0.002, 0.1, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(return_value=(True, "ok"))
        pm.save_position = AsyncMock()

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_entries()

        executor.execute_open.assert_called_once()
        pm.save_position.assert_called_once()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "open"
        assert saved_pos.exchange == "binance"
        assert saved_pos.symbol == "BTC/USDT"

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

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_entries()

        executor.execute_open.assert_not_called()

    async def test_no_entry_when_position_exists(self):
        """Should not open when a position already exists."""
        entry = _make_funding_entry(funding_rate=0.0005)
        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_open = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.can_open = AsyncMock(
            return_value=(False, "Position already exists"),
        )

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


@pytest.mark.asyncio
class TestBasisTradeExits:
    async def test_closes_when_funding_drops(self):
        """Should close when funding drops below exit threshold."""
        # funding_rate=0.00002 -> annualized = 2.19% < 3%
        entry = _make_funding_entry(funding_rate=0.00002)

        position = Position(
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
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
        )

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.002, 0.1, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.002, 0.1, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.save_position = AsyncMock()

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_called_once()
        pm.save_position.assert_called_once()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "closed"

    async def test_closes_when_funding_negative(self):
        """Should close when funding turns negative."""
        entry = _make_funding_entry(funding_rate=-0.0001)

        position = Position(
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
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
        )

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock(
            return_value=(
                LegFill("sell", "spot", "BTC/USDT", 50100.0, 0.002, 0.1, time()),
                LegFill("buy", "perp", "BTC/USDT:USDT", 50110.0, 0.002, 0.1, time()),
            )
        )

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])
        pm.save_position = AsyncMock()

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_called_once()
        saved_pos = pm.save_position.call_args[0][0]
        assert saved_pos.status == "closed"

    async def test_no_exit_when_funding_still_high(self):
        """Should not close when funding is still above exit threshold."""
        # funding_rate=0.0003 -> annualized = 32.85% > 3%
        entry = _make_funding_entry(funding_rate=0.0003)

        position = Position(
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
            entry_funding_rate=0.0005,
            entry_annualized_rate=54.75,
        )

        cache = AsyncMock()
        cache.get_funding = AsyncMock(return_value=entry.to_json())

        executor = MagicMock(spec=TradeExecutor)
        executor.paper = True
        executor.execute_close = AsyncMock()

        pm = MagicMock(spec=PositionManager)
        pm.get_all_positions = AsyncMock(return_value=[position])

        strategy = _make_strategy(cache, executor, pm)
        await strategy._check_exits()

        executor.execute_close.assert_not_called()
