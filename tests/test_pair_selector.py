from __future__ import annotations

from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from xge.trading.pair_selector import validate_pair


def _make_exchange(
    funding_rate: float = 0.0003,
    funding_history: list[dict] | None = None,
    spot_price: float = 50000.0,
    perp_price: float = 50010.0,
    quote_volume: float = 10_000_000,
    oi_value: float = 50_000_000,
    oi_history: list[dict] | None = None,
) -> AsyncMock:
    """Build a mock exchange with configurable responses."""
    exchange = AsyncMock()

    exchange.fetch_funding_rate = AsyncMock(return_value={
        "fundingRate": funding_rate,
    })

    if funding_history is None:
        # 21 positive entries (7 days * 3 periods)
        funding_history = [
            {"fundingRate": 0.0002, "timestamp": int((time() - i * 28800) * 1000)}
            for i in range(21)
        ]
    exchange.fetch_funding_rate_history = AsyncMock(return_value=funding_history)

    exchange.fetch_ticker = AsyncMock(side_effect=lambda sym: {
        "last": spot_price if ":" not in sym else perp_price,
        "quoteVolume": quote_volume if ":" in sym else 0,
    })

    exchange.fetch_open_interest = AsyncMock(return_value={
        "openInterestValue": oi_value,
    })

    if oi_history is None:
        oi_history = [
            {"openInterestValue": oi_value * 0.95},
            {"openInterestValue": oi_value},
        ]
    exchange.fetch_open_interest_history = AsyncMock(return_value=oi_history)

    return exchange


@pytest.mark.asyncio
class TestPairSelector:
    async def test_approved_when_all_checks_pass(self):
        """Pair should be approved when all conditions are met."""
        exchange = _make_exchange(funding_rate=0.0003)
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is True
        assert result["reasons"] == []
        assert result["funding_7d_avg"] > 0

    async def test_rejected_when_blacklisted(self):
        """Blacklisted pairs should be immediately rejected."""
        exchange = _make_exchange()
        result = await validate_pair(
            exchange, "bitget", "OP/USDT", "OP/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("blacklisted" in r for r in result["reasons"])

    async def test_rejected_when_no_tier(self):
        """Pairs not in any tier should be rejected."""
        exchange = _make_exchange()
        result = await validate_pair(
            exchange, "bitget", "DOGE/USDT", "DOGE/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("not assigned" in r for r in result["reasons"])

    async def test_rejected_when_funding_too_low(self):
        """Should reject when current funding rate is below threshold."""
        exchange = _make_exchange(funding_rate=0.00005)
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("Current funding" in r for r in result["reasons"])

    async def test_rejected_when_funding_history_has_negatives(self):
        """Should reject when 7-day funding history has negative entries."""
        # Mix of positive and negative rates
        history = [
            {"fundingRate": 0.0002, "timestamp": int((time() - i * 28800) * 1000)}
            for i in range(18)
        ] + [
            {"fundingRate": -0.0001, "timestamp": int((time() - i * 28800) * 1000)}
            for i in range(18, 21)
        ]
        exchange = _make_exchange(
            funding_rate=0.0003,
            funding_history=history,
        )
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("not positive" in r for r in result["reasons"])

    async def test_rejected_when_spread_too_wide(self):
        """Should reject when spot-perp spread exceeds threshold."""
        exchange = _make_exchange(
            funding_rate=0.0003,
            spot_price=50000.0,
            perp_price=50100.0,  # 0.2% spread > 0.05% threshold
        )
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("Spread" in r for r in result["reasons"])

    async def test_rejected_when_volume_too_low(self):
        """Should reject when 24h volume is below threshold."""
        exchange = _make_exchange(
            funding_rate=0.0003,
            quote_volume=1_000_000,  # < 5M threshold
        )
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("volume" in r.lower() for r in result["reasons"])

    async def test_rejected_when_oi_drops_too_much(self):
        """Should reject when OI drops more than 10%."""
        oi_history = [
            {"openInterestValue": 100_000_000},  # 24h ago
            {"openInterestValue": 80_000_000},    # now (20% drop)
        ]
        exchange = _make_exchange(
            funding_rate=0.0003,
            oi_value=80_000_000,
            oi_history=oi_history,
        )
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        assert result["approved"] is False
        assert any("OI dropped" in r for r in result["reasons"])

    async def test_oi_check_non_blocking_on_error(self):
        """OI check failure should not block approval."""
        exchange = _make_exchange(funding_rate=0.0003)
        exchange.fetch_open_interest = AsyncMock(side_effect=Exception("not supported"))
        result = await validate_pair(
            exchange, "bitget", "BTC/USDT", "BTC/USDT:USDT",
        )
        # Should still pass (OI is non-blocking)
        assert result["approved"] is True
