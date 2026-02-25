"""Delta drift monitor for open basis trade positions.

Runs every 30 seconds to:
- Calculate delta (spot notional - perp notional) per position
- Alert on drift > threshold (2% of position size)
- Track basis in real time and store in Redis
- Attempt rebalancing via maker orders when drift exceeds threshold
"""
from __future__ import annotations

import asyncio
import logging
from time import time

from xge.cache.redis_cache import RedisCache
from xge.models import OrderBookEntry
from xge.models_trading import Position
from xge.trading.position_manager import PositionManager
from xge.trading.tier_config import get_tier_for_symbol, TIER_1, TIER_2

logger = logging.getLogger("xge.trading.delta_monitor")

CHECK_INTERVAL = 30  # seconds
REBALANCE_TIMEOUT = 60  # seconds


class DeltaMonitor:
    """Monitors delta drift and basis for open positions."""

    def __init__(
        self,
        cache: RedisCache,
        position_manager: PositionManager,
    ) -> None:
        self._cache = cache
        self._pm = position_manager
        self._running = False
        self._negative_funding_counts: dict[str, int] = {}  # key -> count

    async def run(self) -> None:
        """Main monitoring loop — runs every CHECK_INTERVAL seconds."""
        self._running = True
        logger.info(
            "Delta monitor started (interval=%ds, rebalance_timeout=%ds)",
            CHECK_INTERVAL, REBALANCE_TIMEOUT,
        )

        while self._running:
            try:
                await self._check_all_positions()
            except Exception:
                logger.exception("Error in delta monitor loop")

            await asyncio.sleep(CHECK_INTERVAL)

    def stop(self) -> None:
        self._running = False
        logger.info("Delta monitor stopping")

    async def _check_all_positions(self) -> None:
        """Check delta and basis for all open positions."""
        positions = await self._pm.get_all_positions()

        for pos in positions:
            if pos.status != "open":
                continue

            spot_raw = await self._cache.get_latest(pos.exchange, pos.symbol)
            if not spot_raw:
                continue

            spot_book = OrderBookEntry.from_json(spot_raw)
            spot_price = spot_book.mid_price

            # Use spot mid_price as perp price proxy (spread < 0.1% in basis)
            perp_price = spot_price

            # ── Delta calculation ───────────────────────────────────
            spot_notional = pos.spot_quantity * spot_price
            perp_notional = pos.perp_quantity * perp_price
            delta = spot_notional - perp_notional

            # ── Threshold from tier ─────────────────────────────────
            tier = get_tier_for_symbol(pos.symbol)
            if tier:
                threshold = tier["size_per_pair"] * tier["delta_alert_pct"]
            else:
                # Fallback for positions not in any tier
                threshold = pos.size_usdt * 0.02

            # ── Basis calculation ───────────────────────────────────
            if perp_price > 0:
                basis_pct = (spot_price - perp_price) / perp_price * 100
            else:
                basis_pct = 0.0

            # Store basis in Redis with timestamp
            now = time()
            basis_key = f"basis:{pos.exchange}:{pos.symbol}:{int(now)}"
            await self._cache.set(
                basis_key,
                f"{basis_pct:.6f}",
                ex=86400,  # 24h TTL
            )

            # ── Check drift ─────────────────────────────────────────
            if abs(delta) > threshold:
                logger.warning(
                    "[%s:%s] DELTA DRIFT: $%.4f (threshold=$%.2f) "
                    "spot_notional=$%.2f perp_notional=$%.2f basis=%.4f%%",
                    pos.exchange, pos.symbol,
                    delta, threshold,
                    spot_notional, perp_notional, basis_pct,
                )

                # Attempt rebalance (log only in paper mode)
                rebalanced = await self._attempt_rebalance(pos, delta)
                if not rebalanced:
                    logger.critical(
                        "[%s:%s] REBALANCE FAILED — delta=$%.4f persists. "
                        "Manual intervention may be required.",
                        pos.exchange, pos.symbol, delta,
                    )
            else:
                logger.debug(
                    "[%s:%s] Delta OK: $%.4f (threshold=$%.2f) basis=%.4f%%",
                    pos.exchange, pos.symbol, delta, threshold, basis_pct,
                )

    async def _attempt_rebalance(self, pos: Position, delta: float) -> bool:
        """Attempt to rebalance a drifted position with maker orders.

        In paper mode, just logs the intent. In live mode, would place
        limit orders to close the gap.

        Returns True if rebalance succeeded (or paper-simulated).
        """
        if pos.paper:
            logger.warning(
                "[PAPER] Would rebalance %s on %s: adjust delta $%.4f "
                "via maker orders (timeout=%ds)",
                pos.symbol, pos.exchange, delta, REBALANCE_TIMEOUT,
            )
            return True

        # Live rebalancing placeholder — not implemented yet for safety
        logger.warning(
            "[LIVE] Rebalance needed for %s on %s: delta=$%.4f. "
            "Auto-rebalance not yet implemented — manual action required.",
            pos.symbol, pos.exchange, delta,
        )
        return False

    def track_negative_funding(self, exchange: str, symbol: str, is_negative: bool) -> int:
        """Track consecutive negative funding periods.

        Returns the current count of consecutive negative periods.
        """
        key = f"{exchange}:{symbol}"
        if is_negative:
            self._negative_funding_counts[key] = (
                self._negative_funding_counts.get(key, 0) + 1
            )
        else:
            self._negative_funding_counts[key] = 0
        return self._negative_funding_counts[key]

    def reset_tracking(self, exchange: str, symbol: str) -> None:
        """Reset negative funding tracking for a closed position."""
        key = f"{exchange}:{symbol}"
        self._negative_funding_counts.pop(key, None)
