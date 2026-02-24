from __future__ import annotations

import asyncio
import logging
from time import time

import ccxt
import ccxt.pro as ccxtpro

from xge.cache.redis_cache import RedisCache
from xge.models_funding import FundingRateEntry, spot_to_perp

logger = logging.getLogger("xge.collector.funding")


class FundingRateCollector:
    """Collects funding rates from a single exchange via WS or REST polling."""

    def __init__(
        self,
        exchange_id: str,
        symbols: list[str],
        cache: RedisCache,
        poll_interval: int = 300,
    ) -> None:
        self.exchange_id = exchange_id
        self.symbols = symbols  # spot symbols, e.g. ["BTC/USDT", "ETH/USDT"]
        self.cache = cache
        self.poll_interval = poll_interval
        self._exchange: ccxtpro.Exchange | None = None
        self._running = False
        self._perp_symbols: list[str] = []
        self._perp_to_spot: dict[str, str] = {}
        self._skip_symbols: set[str] = set()

    async def connect(self) -> None:
        exchange_class = getattr(ccxtpro, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Exchange {self.exchange_id} not supported by ccxt.pro")

        self._exchange = exchange_class({"enableRateLimit": True})
        await self._exchange.load_markets()

        # Build perp symbol map, only keeping symbols that exist on this exchange
        for spot_sym in self.symbols:
            perp_sym = spot_to_perp(spot_sym)
            if perp_sym in self._exchange.markets:
                self._perp_symbols.append(perp_sym)
                self._perp_to_spot[perp_sym] = spot_sym

        logger.info(
            "Funding collector connected to %s (%d/%d perp symbols available)",
            self.exchange_id,
            len(self._perp_symbols),
            len(self.symbols),
        )

    async def disconnect(self) -> None:
        self._running = False
        if self._exchange:
            await self._exchange.close()
            logger.info("Funding collector disconnected from %s", self.exchange_id)
            self._exchange = None

    async def subscribe(self) -> None:
        """Start collecting funding rates for all available perp symbols."""
        if not self._exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        self._running = True

        if not self._perp_symbols:
            logger.warning(
                "No perp symbols available on %s, funding collector idle",
                self.exchange_id,
            )
            return

        tasks = [self._collect_symbol(symbol) for symbol in self._perp_symbols]
        await asyncio.gather(*tasks)

    async def _collect_symbol(self, perp_symbol: str) -> None:
        """Collect funding rate for a single symbol, trying WS then REST."""
        # Try WebSocket first
        try:
            await self._watch_funding(perp_symbol)
            return
        except (ccxt.NotSupported, AttributeError):
            logger.debug(
                "WS funding not supported on %s, falling back to REST for %s",
                self.exchange_id, perp_symbol,
            )
        except ccxt.BadSymbol:
            logger.warning(
                "Symbol %s not available on %s for funding, skipping",
                perp_symbol, self.exchange_id,
            )
            return

        # Fallback to REST polling
        await self._poll_funding(perp_symbol)

    async def _watch_funding(self, perp_symbol: str) -> None:
        """Watch funding rate via WebSocket."""
        backoff = 1
        while self._running:
            try:
                result = await self._exchange.watch_funding_rate(perp_symbol)
                await self._process_funding(perp_symbol, result)
                backoff = 1
            except ccxt.BadSymbol:
                logger.warning(
                    "Symbol %s not available on %s, skipping permanently",
                    perp_symbol, self.exchange_id,
                )
                return
            except (ccxt.NotSupported, AttributeError):
                raise
            except Exception as e:
                if not self._running:
                    break
                logger.error(
                    "Error watching funding %s on %s: %s. Retrying in %ds...",
                    perp_symbol, self.exchange_id, e, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _poll_funding(self, perp_symbol: str) -> None:
        """Poll funding rate via REST API."""
        backoff = 1
        while self._running:
            try:
                result = await self._exchange.fetch_funding_rate(perp_symbol)
                await self._process_funding(perp_symbol, result)
                backoff = 1
                await asyncio.sleep(self.poll_interval)
            except ccxt.BadSymbol:
                logger.warning(
                    "Symbol %s not available on %s, skipping permanently",
                    perp_symbol, self.exchange_id,
                )
                return
            except Exception as e:
                if not self._running:
                    break
                logger.error(
                    "Error polling funding %s on %s: %s. Retrying in %ds...",
                    perp_symbol, self.exchange_id, e, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _process_funding(self, perp_symbol: str, result: dict) -> None:
        """Process and store a funding rate result."""
        funding_rate = result.get("fundingRate")
        if funding_rate is None:
            return

        spot_symbol = self._perp_to_spot.get(perp_symbol, perp_symbol)
        funding_ts = result.get("fundingTimestamp") or result.get("timestamp") or 0
        next_ts = result.get("nextFundingTimestamp")
        next_rate = result.get("nextFundingRate")

        entry = FundingRateEntry(
            exchange=self.exchange_id,
            symbol=perp_symbol,
            spot_symbol=spot_symbol,
            funding_rate=float(funding_rate),
            funding_timestamp=float(funding_ts) / 1000 if funding_ts > 1e12 else float(funding_ts),
            next_funding_timestamp=float(next_ts) / 1000 if next_ts and next_ts > 1e12 else (float(next_ts) if next_ts else None),
            next_funding_rate=float(next_rate) if next_rate is not None else None,
            timestamp=time(),
        )

        channel = f"funding:{self.exchange_id}:{spot_symbol}"
        await self.cache.set_funding(self.exchange_id, spot_symbol, entry.to_json())
        await self.cache.publish(channel, entry.to_json())
