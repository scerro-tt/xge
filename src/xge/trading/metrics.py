"""Metrics and reporting for basis trade system.

Reads all trades from Redis and calculates performance metrics,
capital allocation, and generates formatted reports.
"""
from __future__ import annotations

import logging
from time import time

from xge.cache.redis_cache import RedisCache
from xge.models_trading import Position
from xge.trading.position_manager import PositionManager
from xge.trading.tier_config import CAPITAL_CONFIG, get_tier_for_symbol

logger = logging.getLogger("xge.trading.metrics")


async def calculate_metrics(
    position_manager: PositionManager,
    cache: RedisCache,
) -> dict:
    """Calculate all trading metrics from Redis data.

    Returns a dict with all performance and capital metrics.
    """
    history = await position_manager.get_trade_history()
    open_positions = await position_manager.get_all_positions()

    closed_trades = [t for t in history if t.status in ("closed", "stale_closed")]
    total_trades = len(closed_trades)

    # ── Trade performance ───────────────────────────────────────────
    total_realized_pnl = sum(t.realized_pnl for t in closed_trades)
    total_funding = sum(t.funding_collected for t in closed_trades)
    positive_trades = sum(1 for t in closed_trades if t.realized_pnl > 0)

    win_rate = (positive_trades / total_trades * 100) if total_trades > 0 else 0.0
    avg_pnl = total_realized_pnl / total_trades if total_trades > 0 else 0.0

    # ── Per-pair metrics ────────────────────────────────────────────
    pair_pnl: dict[str, float] = {}
    pair_funding: dict[str, float] = {}
    pair_size: dict[str, float] = {}
    for t in closed_trades:
        key = f"{t.exchange}:{t.symbol}"
        pair_pnl[key] = pair_pnl.get(key, 0) + t.realized_pnl
        pair_funding[key] = pair_funding.get(key, 0) + t.funding_collected
        pair_size[key] = pair_size.get(key, 0) + t.size_usdt

    # Net PnL ratio per pair
    pair_ratio = {}
    for key in pair_pnl:
        if pair_size[key] > 0:
            pair_ratio[key] = pair_pnl[key] / pair_size[key] * 100

    best_pair = max(pair_ratio, key=pair_ratio.get, default="N/A") if pair_ratio else "N/A"
    worst_pair = min(pair_ratio, key=pair_ratio.get, default="N/A") if pair_ratio else "N/A"

    # ── Funding yield ───────────────────────────────────────────────
    total_size = sum(t.size_usdt for t in closed_trades)
    funding_yield = (total_funding / total_size * 100) if total_size > 0 else 0.0

    # ── Basis cost average ──────────────────────────────────────────
    basis_costs = []
    for t in closed_trades:
        if t.perp_entry_price > 0:
            bc = abs(t.spot_entry_price - t.perp_entry_price) / t.perp_entry_price * 100
            basis_costs.append(bc)
    avg_basis_cost = sum(basis_costs) / len(basis_costs) if basis_costs else 0.0

    # ── Capital metrics ─────────────────────────────────────────────
    capital_deployed = sum(p.size_usdt for p in open_positions)
    capital_free = CAPITAL_CONFIG["operative"] - capital_deployed
    reserve_status = "OK" if capital_free + capital_deployed <= CAPITAL_CONFIG["operative"] else "ALERT"

    # If total balance estimation drops below operative threshold
    estimated_balance = CAPITAL_CONFIG["total"] + total_realized_pnl
    if estimated_balance < CAPITAL_CONFIG["operative"]:
        reserve_status = "ALERT"

    # ── Funding vs drift ────────────────────────────────────────────
    total_non_funding_pnl = total_realized_pnl - total_funding
    funding_vs_drift = (
        abs(total_funding / total_non_funding_pnl)
        if total_non_funding_pnl != 0 else float("inf")
    )

    # ── Projected monthly yield ─────────────────────────────────────
    if closed_trades:
        first_trade_time = min(t.opened_at for t in closed_trades)
        days_active = max((time() - first_trade_time) / 86400, 1)
        projected_monthly = (funding_yield / days_active) * 30
    else:
        days_active = 0
        projected_monthly = 0.0

    return {
        # Trade performance
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "avg_pnl_per_trade": round(avg_pnl, 6),
        "total_realized_pnl": round(total_realized_pnl, 6),
        "total_funding_collected": round(total_funding, 6),
        "funding_yield_real": round(funding_yield, 4),
        "avg_basis_cost": round(avg_basis_cost, 4),
        "net_pnl_ratio": round(
            (total_realized_pnl / total_size * 100) if total_size > 0 else 0, 4
        ),
        "funding_vs_drift": round(funding_vs_drift, 2),
        "projected_monthly_yield": round(projected_monthly, 4),
        # Best/worst
        "best_pair": best_pair,
        "best_pair_ratio": round(pair_ratio.get(best_pair, 0), 4),
        "worst_pair": worst_pair,
        "worst_pair_ratio": round(pair_ratio.get(worst_pair, 0), 4),
        # Capital
        "capital_total": CAPITAL_CONFIG["total"],
        "capital_deployed": round(capital_deployed, 2),
        "capital_free": round(capital_free, 2),
        "reserve_rebalance": CAPITAL_CONFIG["reserve_rebalance"],
        "reserve_status": reserve_status,
        "open_positions": len(open_positions),
        "days_active": round(days_active, 1),
    }


def format_report(metrics: dict) -> str:
    """Format metrics into a readable text report."""
    lines = [
        "",
        "=" * 55,
        "  XGE BASIS TRADE REPORT",
        "=" * 55,
        "",
        "  CAPITAL OVERVIEW",
        f"  Total:       {metrics['capital_total']:>10,} USDT",
        f"  Deployed:    {metrics['capital_deployed']:>10,.2f} USDT "
        f"({metrics['capital_deployed'] / max(metrics['capital_total'], 1) * 100:.0f}%)",
        f"  Free:        {metrics['capital_free']:>10,.2f} USDT",
        f"  Reserve:     {metrics['reserve_rebalance']:>10,} USDT "
        f"[{metrics['reserve_status']}]",
        "",
        "-" * 55,
        "",
        "  PERFORMANCE",
        f"  Total trades:       {metrics['total_trades']:>8}",
        f"  Win rate:           {metrics['win_rate']:>7.1f}%",
        f"  Avg PnL/trade:     ${metrics['avg_pnl_per_trade']:>10.4f}",
        f"  Total realized:    ${metrics['total_realized_pnl']:>10.4f}",
        f"  Total funding:     ${metrics['total_funding_collected']:>10.4f}",
        f"  Funding yield:      {metrics['funding_yield_real']:>7.2f}%",
        f"  Avg basis cost:     {metrics['avg_basis_cost']:>7.4f}%",
        f"  Funding/drift:      {metrics['funding_vs_drift']:>7.1f}x",
        f"  Projected monthly:  {metrics['projected_monthly_yield']:>7.2f}%",
        "",
        f"  Best pair:   {metrics['best_pair']} ({metrics['best_pair_ratio']:.2f}%)",
        f"  Worst pair:  {metrics['worst_pair']} ({metrics['worst_pair_ratio']:.2f}%)",
        "",
        f"  Open positions: {metrics['open_positions']}",
        f"  Days active:    {metrics['days_active']:.1f}",
        "",
        "=" * 55,
    ]
    return "\n".join(lines)


async def log_metrics_report(
    position_manager: PositionManager,
    cache: RedisCache,
) -> None:
    """Calculate metrics and log the formatted report."""
    try:
        metrics = await calculate_metrics(position_manager, cache)
        report = format_report(metrics)
        logger.info(report)
    except Exception:
        logger.exception("Error generating metrics report")


async def log_capital_status(position_manager: PositionManager) -> None:
    """Log a one-line capital status summary."""
    open_positions = await position_manager.get_all_positions()
    deployed = sum(p.size_usdt for p in open_positions)
    free = CAPITAL_CONFIG["operative"] - deployed
    reserve = CAPITAL_CONFIG["reserve_rebalance"]

    logger.info(
        "[CAPITAL] Deployed: $%.2f | Free: $%.2f | Reserve: $%d",
        deployed, free, reserve,
    )
