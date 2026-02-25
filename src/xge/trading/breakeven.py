"""Breakeven calculator for basis trade positions.

Calculates total entry/exit costs and determines how many funding
periods are needed to reach breakeven, using real exchange fee schedules.
"""
from __future__ import annotations

from xge.trading.tier_config import get_fees

# Funding periods per day (8h intervals)
PERIODS_PER_DAY = 3
# Maximum acceptable breakeven in funding periods (24h = 3 periods)
MAX_BREAKEVEN_PERIODS = 3 * PERIODS_PER_DAY  # 9 periods = 3 days


def calculate_breakeven(
    size_usdt: float,
    spot_entry_price: float,
    perp_entry_price: float,
    funding_rate: float,
    exchange: str,
    spot_fee: float | None = None,
    perp_fee: float | None = None,
) -> dict:
    """Calculate breakeven for a basis trade.

    Uses taker fees for entry (market orders) and maker fees for exit
    (limit orders target). If spot_fee/perp_fee are provided, they
    override the fee schedule.

    Args:
        size_usdt: Position size in USDT.
        spot_entry_price: Spot entry price.
        perp_entry_price: Perp entry price.
        funding_rate: Current funding rate per period (e.g., 0.0001 = 0.01%).
        exchange: Exchange ID (bitget, okx, mexc).
        spot_fee: Override spot fee rate.
        perp_fee: Override perp fee rate.

    Returns:
        {
            "entry_cost_usdt": float,
            "exit_cost_usdt": float,
            "total_cost_usdt": float,
            "funding_per_period": float,
            "breakeven_periods": float,
            "breakeven_hours": float,
            "viable": bool,  # True if breakeven < MAX_BREAKEVEN_PERIODS
        }
    """
    fees = get_fees(exchange)

    # Use provided fees or defaults from schedule
    # Entry: market orders → taker fees
    # Exit: can target maker orders
    s_fee = spot_fee if spot_fee is not None else fees["spot"]
    p_fee_entry = perp_fee if perp_fee is not None else fees["perp_taker"]
    p_fee_exit = perp_fee if perp_fee is not None else fees["perp_maker"]

    # Entry cost: spot taker + perp taker
    entry_cost = size_usdt * (s_fee + p_fee_entry)

    # Exit cost: spot taker + perp maker (target limit orders on exit)
    exit_cost = size_usdt * (s_fee + p_fee_exit)

    total_cost = entry_cost + exit_cost

    # Funding collected per period
    funding_per_period = size_usdt * funding_rate

    # Breakeven calculation
    if funding_per_period > 0:
        breakeven_periods = total_cost / funding_per_period
    else:
        breakeven_periods = float("inf")

    breakeven_hours = breakeven_periods * 8  # 8 hours per period

    return {
        "entry_cost_usdt": round(entry_cost, 6),
        "exit_cost_usdt": round(exit_cost, 6),
        "total_cost_usdt": round(total_cost, 6),
        "funding_per_period": round(funding_per_period, 6),
        "breakeven_periods": round(breakeven_periods, 2),
        "breakeven_hours": round(breakeven_hours, 2),
        "viable": breakeven_periods < MAX_BREAKEVEN_PERIODS,
    }
