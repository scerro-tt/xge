from __future__ import annotations

import pytest

from xge.trading.breakeven import calculate_breakeven


class TestBreakevenCalculator:
    def test_bitget_tier1_minimum_funding(self):
        """With 315 USDT on Bitget at 0.01% funding, should NOT be viable."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0001,  # 0.01%
            exchange="bitget",
        )
        # entry_cost = 315 * (0.001 + 0.0006) = 0.5040
        # exit_cost  = 315 * (0.001 + 0.0002) = 0.3780
        # total_cost = 0.882
        # funding/period = 315 * 0.0001 = 0.0315
        # breakeven = 0.882 / 0.0315 = 28 periods
        assert result["viable"] is False
        assert result["breakeven_periods"] == 28.0
        assert result["total_cost_usdt"] == 0.882
        assert result["funding_per_period"] == 0.0315

    def test_bitget_tier1_good_funding(self):
        """With 315 USDT on Bitget at 0.03% funding, should be viable."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0003,  # 0.03%
            exchange="bitget",
        )
        # funding/period = 315 * 0.0003 = 0.0945
        # breakeven = 0.882 / 0.0945 = 9.33 periods ≈ 3.1 days
        assert result["viable"] is False  # 9.33 > 9 threshold
        assert result["funding_per_period"] == 0.0945

    def test_bitget_tier1_high_funding(self):
        """With 315 USDT on Bitget at 0.05% funding, should be viable."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0005,  # 0.05%
            exchange="bitget",
        )
        # funding/period = 315 * 0.0005 = 0.1575
        # breakeven = 0.882 / 0.1575 = 5.6 periods < 9
        assert result["viable"] is True
        assert result["breakeven_periods"] < 9

    def test_okx_tier1(self):
        """OKX fee schedule: spot=0.1%, perp_taker=0.05%, perp_maker=0.02%."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0003,
            exchange="okx",
        )
        # entry_cost = 315 * (0.001 + 0.0005) = 0.4725
        # exit_cost  = 315 * (0.001 + 0.0002) = 0.378
        # total = 0.8505
        assert result["entry_cost_usdt"] == 0.4725
        assert result["exit_cost_usdt"] == 0.378
        assert result["total_cost_usdt"] == 0.8505

    def test_mexc_tier2(self):
        """MEXC has lowest fees — should be most viable."""
        result = calculate_breakeven(
            size_usdt=180,
            spot_entry_price=5.0,
            perp_entry_price=5.01,
            funding_rate=0.0003,
            exchange="mexc",
        )
        # entry_cost = 180 * (0.0002 + 0.0006) = 0.144
        # exit_cost  = 180 * (0.0002 + 0.0) = 0.036
        # total = 0.18
        # funding = 180 * 0.0003 = 0.054
        # breakeven = 0.18 / 0.054 = 3.33 periods
        assert result["viable"] is True
        assert result["total_cost_usdt"] == 0.18
        assert result["breakeven_periods"] == 3.33

    def test_zero_funding_rate(self):
        """Zero funding rate should result in infinite breakeven."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0,
            exchange="bitget",
        )
        assert result["breakeven_periods"] == float("inf")
        assert result["viable"] is False

    def test_custom_fee_override(self):
        """Custom fees should override the schedule."""
        result = calculate_breakeven(
            size_usdt=100,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0005,
            exchange="bitget",
            spot_fee=0.002,
            perp_fee=0.001,
        )
        # entry_cost = 100 * (0.002 + 0.001) = 0.3
        # exit_cost  = 100 * (0.002 + 0.001) = 0.3
        # total = 0.6
        assert result["entry_cost_usdt"] == 0.3
        assert result["exit_cost_usdt"] == 0.3
        assert result["total_cost_usdt"] == 0.6

    def test_unknown_exchange_uses_defaults(self):
        """Unknown exchange should use safe default fees."""
        result = calculate_breakeven(
            size_usdt=100,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0005,
            exchange="unknown_exchange",
        )
        # Should use defaults: spot=0.001, perp_taker=0.001, perp_maker=0.0005
        # entry_cost = 100 * (0.001 + 0.001) = 0.2
        # exit_cost  = 100 * (0.001 + 0.0005) = 0.15
        assert result["entry_cost_usdt"] == 0.2
        assert result["exit_cost_usdt"] == 0.15

    def test_breakeven_hours_correct(self):
        """Breakeven hours should be periods * 8."""
        result = calculate_breakeven(
            size_usdt=315,
            spot_entry_price=50000.0,
            perp_entry_price=50010.0,
            funding_rate=0.0005,
            exchange="bitget",
        )
        expected_hours = result["breakeven_periods"] * 8
        assert abs(result["breakeven_hours"] - expected_hours) < 0.1
