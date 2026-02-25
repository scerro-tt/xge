from __future__ import annotations

import logging
from time import time

from xge.cache.redis_cache import RedisCache
from xge.models_trading import Position

logger = logging.getLogger("xge.trading.position_manager")


class PositionManager:
    """Manages trading positions stored in Redis."""

    def __init__(
        self,
        cache: RedisCache,
        max_positions_per_exchange: int = 3,
        max_total_positions: int = 10,
    ) -> None:
        self._cache = cache
        self._max_per_exchange = max_positions_per_exchange
        self._max_total = max_total_positions

    async def get_position(self, exchange: str, symbol: str) -> Position | None:
        """Get an open position for exchange/symbol, or None."""
        key = f"position:{exchange}:{symbol}"
        raw = await self._cache.get(key)
        if raw:
            return Position.from_json(raw)
        return None

    async def save_position(self, position: Position) -> None:
        """Save a position to Redis. Remove key if closed."""
        if position.status == "closed":
            await self._cache.delete(position.redis_key)
            await self._cache.rpush("trade_history", position.to_json())
            logger.info(
                "Removed closed position %s from Redis (persisted to trade_history)",
                position.redis_key,
            )
        else:
            await self._cache.set(position.redis_key, position.to_json(), ex=7 * 86400)
            logger.debug("Saved position %s (TTL=7d)", position.redis_key)

    async def get_all_positions(
        self, exchange: str | None = None,
    ) -> list[Position]:
        """Get all open positions, optionally filtered by exchange."""
        if exchange:
            pattern = f"position:{exchange}:*"
        else:
            pattern = "position:*"

        keys = await self._cache.scan_keys(pattern)
        positions: list[Position] = []
        for key in keys:
            raw = await self._cache.get(key)
            if raw:
                positions.append(Position.from_json(raw))
        return positions

    async def can_open(
        self, exchange: str, symbol: str,
    ) -> tuple[bool, str]:
        """Check if a new position can be opened.

        Returns (allowed, reason).
        """
        existing = await self.get_position(exchange, symbol)
        if existing:
            return False, f"Position already exists for {exchange}:{symbol}"

        exchange_positions = await self.get_all_positions(exchange=exchange)
        if len(exchange_positions) >= self._max_per_exchange:
            return False, (
                f"Max positions per exchange reached ({self._max_per_exchange}) "
                f"for {exchange}"
            )

        all_positions = await self.get_all_positions()
        if len(all_positions) >= self._max_total:
            return False, f"Max total positions reached ({self._max_total})"

        return True, "ok"

    async def reconcile_positions(
        self,
        max_age_seconds: float = 7 * 86400,
        valid_tier_symbols: list[str] | None = None,
    ) -> int:
        """Close stale positions that survived a deploy.

        Closes positions that are:
        - Older than max_age_seconds, OR
        - Have no tier assigned (legacy positions from previous code), OR
        - Not in the current valid tier symbols list

        Returns count of cleaned positions.
        """
        positions = await self.get_all_positions()
        now = time()
        cleaned = 0
        for pos in positions:
            should_close = False
            reason = ""

            if now - pos.opened_at > max_age_seconds:
                should_close = True
                reason = f"stale (age: {(now - pos.opened_at) / 3600:.1f}h)"

            elif not pos.tier:
                should_close = True
                reason = "no tier assigned (legacy position)"

            elif valid_tier_symbols and pos.symbol not in valid_tier_symbols:
                should_close = True
                reason = f"symbol {pos.symbol} not in current tier config"

            if should_close:
                pos.status = "stale_closed"
                pos.closed_at = now
                pos.realized_pnl = 0.0
                pos.exit_reason = "reconciled"
                await self._cache.delete(pos.redis_key)
                await self._cache.rpush("trade_history", pos.to_json())
                logger.warning(
                    "Reconciled position %s: %s",
                    pos.redis_key, reason,
                )
                cleaned += 1
        return cleaned

    async def get_trade_history(self) -> list[Position]:
        """Read all closed trades from the persistent trade_history list."""
        raw_list = await self._cache.lrange("trade_history", 0, -1)
        return [Position.from_json(raw) for raw in raw_list]
