from __future__ import annotations

import asyncio
import logging
from time import time

import ccxt
import ccxt.pro as ccxtpro

from xge.collector.base import BasePriceCollector
from xge.models import OrderBookEntry
from xge.cache.redis_cache import RedisCache

logger = logging.getLogger("xge.collector")


class WSPriceCollector(BasePriceCollector):
    """WebSocket-based price collector using ccxt.pro."""

    def __init__(
        self,
        exchange_id: str,
        symbols: list[str],
        cache: RedisCache,
    ) -> None:
        super().__init__(exchange_id, symbols)
        self.cache = cache
        self._exchange: ccxtpro.Exchange | None = None
        self._running = False

    async def connect(self) -> None:
        exchange_class = getattr(ccxtpro, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Exchange {self.exchange_id} not supported by ccxt.pro")

        self._exchange = exchange_class({
            "enableRateLimit": True,
        })
        logger.info("Connected to %s", self.exchange_id)

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            logger.info("Disconnected from %s", self.exchange_id)
            self._exchange = None
        self._running = False

    async def subscribe(self) -> None:
        """Watch order books for all symbols, publishing updates to Redis."""
        if not self._exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        self._running = True
        tasks = [self._watch_symbol(symbol) for symbol in self.symbols]
        await asyncio.gather(*tasks)

    async def _watch_symbol(self, symbol: str) -> None:
        """Continuously watch a single symbol's order book."""
        while self._running:
            try:
                ob = await self._exchange.watch_order_book(symbol)

                if not ob["bids"] or not ob["asks"]:
                    continue

                entry = OrderBookEntry(
                    exchange=self.exchange_id,
                    symbol=symbol,
                    bid=float(ob["bids"][0][0]),
                    ask=float(ob["asks"][0][0]),
                    bid_volume=float(ob["bids"][0][1]),
                    ask_volume=float(ob["asks"][0][1]),
                    timestamp=time(),
                )

                channel = f"prices:{self.exchange_id}:{symbol}"
                await self.cache.publish(channel, entry.to_json())
                await self.cache.set_latest(self.exchange_id, symbol, entry.to_json())

            except ccxt.BadSymbol:
                logger.warning(
                    "Symbol %s not available on %s, skipping permanently",
                    symbol, self.exchange_id,
                )
                return
            except Exception as e:
                if not self._running:
                    break
                logger.error(
                    "Error watching %s on %s: %s. Reconnecting...",
                    symbol, self.exchange_id, e,
                )
                await asyncio.sleep(1)
