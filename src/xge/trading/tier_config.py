"""Tier-based capital allocation and fee configuration for basis trading."""
from __future__ import annotations


# ── Capital allocation ──────────────────────────────────────────────
CAPITAL_CONFIG = {
    "total": 2000,
    "operative": 1800,
    "reserve_rebalance": 200,   # never touched except emergency
    "stable_buffer": 180,       # for position rebalancing
}

# ── Tier definitions ────────────────────────────────────────────────
TIER_1 = {
    "name": "tier_1",
    "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"],
    "capital_total": 1260,
    "size_per_pair": 315,       # 1260 / 4
    "max_pairs_open": 4,
    "min_funding_rate": 0.00008,
    "stop_loss_pct": 0.005,     # 0.5% of size_per_pair
    "delta_alert_pct": 0.02,    # 2% drift threshold
}

TIER_2 = {
    "name": "tier_2",
    "symbols": ["WLD/USDT", "NEAR/USDT", "AVAX/USDT"],
    "capital_total": 360,
    "size_per_pair": 180,       # max 2 open simultaneously
    "max_pairs_open": 2,
    "min_funding_rate": 0.00015,
    "stop_loss_pct": 0.005,
    "delta_alert_pct": 0.02,
}

TIERS = [TIER_1, TIER_2]

BLACKLIST = ["ATOM/USDT", "DOT/USDT", "OP/USDT", "AAVE/USDT"]

# ── Real fee schedules (no VIP tier, standard) ──────────────────────
FEE_SCHEDULE: dict[str, dict[str, float]] = {
    "bitget": {
        "spot": 0.001,
        "perp_maker": 0.0002,
        "perp_taker": 0.0006,
    },
    "okx": {
        "spot": 0.001,
        "perp_maker": 0.0002,
        "perp_taker": 0.0005,
    },
    "mexc": {
        "spot": 0.0002,
        "perp_maker": 0.0,
        "perp_taker": 0.0006,
    },
}


def get_tier_for_symbol(symbol: str) -> dict | None:
    """Return the tier config for a symbol, or None if not in any tier."""
    if symbol in BLACKLIST:
        return None
    for tier in TIERS:
        if symbol in tier["symbols"]:
            return tier
    return None


def get_fees(exchange: str) -> dict[str, float]:
    """Return fee schedule for an exchange, with safe defaults."""
    return FEE_SCHEDULE.get(exchange, {
        "spot": 0.001,
        "perp_maker": 0.0005,
        "perp_taker": 0.001,
    })


def get_all_tier_symbols() -> list[str]:
    """Return all symbols across all tiers (excluding blacklist)."""
    symbols: list[str] = []
    for tier in TIERS:
        symbols.extend(tier["symbols"])
    return symbols
