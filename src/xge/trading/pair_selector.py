"""Pair validation before opening any basis trade position.

Checks funding history, spot-perp spread, volume, and open interest
to ensure a pair meets quality thresholds.
"""
from __future__ import annotations

import logging
from time import time

import ccxt.pro as ccxtpro

from xge.trading.tier_config import get_tier_for_symbol, BLACKLIST

logger = logging.getLogger("xge.trading.pair_selector")

# ── Thresholds ──────────────────────────────────────────────────────
MIN_FUNDING_RATE = 0.0001          # 0.01% per period
MIN_CONSECUTIVE_POSITIVE_DAYS = 7
MAX_SPREAD = 0.0005                # 0.05%
MIN_VOLUME_24H = 5_000_000        # USDT
MAX_OI_DROP_PCT = 0.10             # 10% max drop allowed


async def validate_pair(
    exchange: ccxtpro.Exchange,
    exchange_id: str,
    symbol: str,
    perp_symbol: str,
) -> dict:
    """Validate a pair before opening a position.

    Returns:
        {
            "approved": bool,
            "reasons": list[str],
            "funding_7d_avg": float,
            "spread": float,
            "volume_24h": float,
            "open_interest_change": float,
        }
    """
    result = {
        "approved": True,
        "reasons": [],
        "funding_7d_avg": 0.0,
        "spread": 0.0,
        "volume_24h": 0.0,
        "open_interest_change": 0.0,
    }

    # ── Blacklist check ─────────────────────────────────────────────
    if symbol in BLACKLIST:
        result["approved"] = False
        result["reasons"].append(f"{symbol} is blacklisted")
        return result

    # ── Tier check ──────────────────────────────────────────────────
    tier = get_tier_for_symbol(symbol)
    if tier is None:
        result["approved"] = False
        result["reasons"].append(f"{symbol} not assigned to any tier")
        return result

    # ── 1. Current funding rate ─────────────────────────────────────
    try:
        funding = await exchange.fetch_funding_rate(perp_symbol)
        current_rate = float(funding.get("fundingRate", 0))
        if current_rate <= MIN_FUNDING_RATE:
            result["approved"] = False
            result["reasons"].append(
                f"Current funding {current_rate:.6f} <= {MIN_FUNDING_RATE}"
            )
    except Exception as e:
        result["approved"] = False
        result["reasons"].append(f"Failed to fetch funding rate: {e}")
        return result

    # ── 2. 7-day funding history ────────────────────────────────────
    try:
        since_ms = int((time() - 7 * 86400) * 1000)
        history = await exchange.fetch_funding_rate_history(
            perp_symbol, since=since_ms, limit=100,
        )
        if history:
            rates = [float(h.get("fundingRate", 0)) for h in history]
            result["funding_7d_avg"] = sum(rates) / len(rates)

            # Check all positive in last 7 days
            # Each day has ~3 funding periods, so 7 days = ~21 entries
            if len(rates) >= 21:
                last_21 = rates[-21:]
            else:
                last_21 = rates

            all_positive = all(r > 0 for r in last_21)
            if not all_positive:
                result["approved"] = False
                negative_count = sum(1 for r in last_21 if r <= 0)
                result["reasons"].append(
                    f"Funding not positive for 7 consecutive days "
                    f"({negative_count}/{len(last_21)} non-positive)"
                )
        else:
            result["approved"] = False
            result["reasons"].append("No funding history available")
    except Exception as e:
        logger.warning(
            "Could not fetch funding history for %s on %s: %s",
            perp_symbol, exchange_id, e,
        )
        # Don't block on history fetch failure — some exchanges don't support it
        result["reasons"].append(f"Funding history unavailable: {e}")

    # ── 3. Spot-perp spread ─────────────────────────────────────────
    try:
        spot_ticker = await exchange.fetch_ticker(symbol)
        perp_ticker = await exchange.fetch_ticker(perp_symbol)

        spot_price = float(spot_ticker.get("last", 0))
        perp_price = float(perp_ticker.get("last", 0))

        if perp_price > 0:
            spread = abs(spot_price - perp_price) / perp_price
            result["spread"] = spread
            if spread > MAX_SPREAD:
                result["approved"] = False
                result["reasons"].append(
                    f"Spread {spread:.6f} > {MAX_SPREAD} ({spread*100:.4f}%)"
                )
    except Exception as e:
        result["approved"] = False
        result["reasons"].append(f"Failed to fetch prices: {e}")

    # ── 4. 24h perp volume ──────────────────────────────────────────
    try:
        perp_ticker = await exchange.fetch_ticker(perp_symbol)
        quote_volume = float(perp_ticker.get("quoteVolume", 0) or 0)
        result["volume_24h"] = quote_volume
        if quote_volume < MIN_VOLUME_24H:
            result["approved"] = False
            result["reasons"].append(
                f"24h volume ${quote_volume:,.0f} < ${MIN_VOLUME_24H:,.0f}"
            )
    except Exception as e:
        result["approved"] = False
        result["reasons"].append(f"Failed to fetch volume: {e}")

    # ── 5. Open Interest stability ──────────────────────────────────
    try:
        oi_data = await exchange.fetch_open_interest(perp_symbol)
        current_oi = float(oi_data.get("openInterestValue", 0) or 0)

        # Try to get historical OI (24h ago) — not all exchanges support this
        oi_change = 0.0
        try:
            since_24h = int((time() - 86400) * 1000)
            oi_history = await exchange.fetch_open_interest_history(
                perp_symbol, timeframe="1d", since=since_24h, limit=2,
            )
            if oi_history and len(oi_history) >= 2:
                prev_oi = float(
                    oi_history[0].get("openInterestValue", 0)
                    or oi_history[0].get("openInterestAmount", 0)
                    or 0
                )
                if prev_oi > 0:
                    oi_change = (current_oi - prev_oi) / prev_oi
                    result["open_interest_change"] = oi_change
                    if oi_change < -MAX_OI_DROP_PCT:
                        result["approved"] = False
                        result["reasons"].append(
                            f"OI dropped {oi_change*100:.1f}% > "
                            f"-{MAX_OI_DROP_PCT*100:.0f}% threshold"
                        )
        except Exception:
            # OI history not available on all exchanges — non-blocking
            logger.debug(
                "OI history not available for %s on %s", perp_symbol, exchange_id,
            )
    except Exception as e:
        logger.debug(
            "Could not fetch OI for %s on %s: %s", perp_symbol, exchange_id, e,
        )
        # OI check is non-blocking for exchanges that don't support it

    level = logging.INFO if result["approved"] else logging.DEBUG
    logger.log(
        level,
        "[%s:%s] Pair validation: approved=%s reasons=%s "
        "funding_7d=%.6f spread=%.6f vol=$%.0f oi_change=%.2f%%",
        exchange_id, symbol,
        result["approved"],
        result["reasons"] or "all checks passed",
        result["funding_7d_avg"],
        result["spread"],
        result["volume_24h"],
        result["open_interest_change"] * 100,
    )

    return result
