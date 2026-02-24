from __future__ import annotations

import logging
from typing import AsyncIterator

import redis.asyncio as aioredis

logger = logging.getLogger("xge.cache")


class RedisCache:
    """Async Redis cache for price data with pub/sub support."""

    def __init__(self, host: str = "localhost", port: int = 6379) -> None:
        self._host = host
        self._port = port
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = aioredis.Redis(
            host=self._host,
            port=self._port,
            decode_responses=True,
        )
        await self._redis.ping()
        logger.info("Connected to Redis at %s:%d", self._host, self._port)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    async def publish(self, channel: str, data: str) -> None:
        """Publish price data to a Redis pub/sub channel."""
        if self._redis:
            await self._redis.publish(channel, data)

    async def set_latest(self, exchange: str, symbol: str, data: str) -> None:
        """Store the latest price entry for an exchange/symbol pair."""
        key = f"latest:{exchange}:{symbol}"
        if self._redis:
            await self._redis.set(key, data)

    async def get_latest(self, exchange: str, symbol: str) -> str | None:
        """Retrieve the latest price entry for an exchange/symbol pair."""
        key = f"latest:{exchange}:{symbol}"
        if self._redis:
            return await self._redis.get(key)
        return None

    async def set_funding(self, exchange: str, symbol: str, data: str) -> None:
        """Store the latest funding rate for an exchange/symbol pair."""
        key = f"funding:{exchange}:{symbol}"
        if self._redis:
            await self._redis.set(key, data)

    async def get_funding(self, exchange: str, symbol: str) -> str | None:
        """Retrieve the latest funding rate for an exchange/symbol pair."""
        key = f"funding:{exchange}:{symbol}"
        if self._redis:
            return await self._redis.get(key)
        return None

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        if self._redis:
            return await self._redis.get(key)
        return None

    async def set(self, key: str, data: str, ex: int | None = None) -> None:
        """Set a value by key with optional expiration in seconds."""
        if self._redis:
            await self._redis.set(key, data, ex=ex)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        if self._redis:
            await self._redis.delete(key)

    async def scan_keys(self, pattern: str) -> list[str]:
        """Scan for keys matching a pattern."""
        keys: list[str] = []
        if self._redis:
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
        return keys

    async def subscribe(self, pattern: str) -> AsyncIterator[dict]:
        """Subscribe to channels matching a pattern and yield messages."""
        if not self._redis:
            raise RuntimeError("Not connected to Redis")

        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(pattern)
        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    yield message
        finally:
            await pubsub.unsubscribe(pattern)
            await pubsub.close()
