from __future__ import annotations

import logging

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
            logger.info(
                "Removed closed position %s from Redis", position.redis_key,
            )
        else:
            await self._cache.set(position.redis_key, position.to_json())
            logger.info("Saved position %s", position.redis_key)

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
