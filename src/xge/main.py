from __future__ import annotations

import asyncio
import logging
import signal
from itertools import combinations

from xge.config import load_settings
from xge.models import OrderBookEntry, SpreadInfo
from xge.models_funding import FundingRateEntry, FundingRateSpread, SpotFundingArb
from xge.collector.ws_collector import WSPriceCollector
from xge.collector.funding_collector import FundingRateCollector
from xge.cache.redis_cache import RedisCache
from xge.utils.logger import setup_logging

logger = logging.getLogger("xge.main")


def _fmt_price(price: float) -> str:
    """Format price with adaptive precision based on magnitude."""
    if price < 1:
        return f"{price:.6f}"
    if price < 100:
        return f"{price:.4f}"
    return f"{price:.2f}"


async def log_spreads(
    cache: RedisCache,
    exchanges: list[str],
    symbols: list[str],
    interval: int,
    fee_map: dict[str, float],
    min_net_spread: float,
) -> None:
    """Periodically log latest prices and spreads between exchanges."""
    while True:
        await asyncio.sleep(interval)

        for symbol in symbols:
            entries: dict[str, OrderBookEntry] = {}
            for exchange_id in exchanges:
                raw = await cache.get_latest(exchange_id, symbol)
                if raw:
                    entries[exchange_id] = OrderBookEntry.from_json(raw)

            if len(entries) < 2:
                continue

            # Log latest prices at DEBUG level (too noisy with many exchanges/pairs)
            prices_str = " | ".join(
                f"{eid}: bid={_fmt_price(e.bid)} ask={_fmt_price(e.ask)}"
                for eid, e in entries.items()
            )
            logger.debug("[%s] %s", symbol, prices_str)

            # Calculate and log spreads for each pair of exchanges
            for ex_a, ex_b in combinations(entries.keys(), 2):
                spread = SpreadInfo.calculate(
                    symbol, entries[ex_a], entries[ex_b],
                    fee_a_pct=fee_map[ex_a], fee_b_pct=fee_map[ex_b],
                )
                if not spread:
                    continue

                if spread.net_spread < min_net_spread:
                    continue

                buy_p = _fmt_price(spread.buy_price)
                sell_p = _fmt_price(spread.sell_price)
                depth = (
                    f"ask_vol={spread.buy_volume:.4f} "
                    f"bid_vol={spread.sell_volume:.4f}"
                )

                if spread.net_spread > 0:
                    logger.debug(
                        "*** OPPORTUNITY *** %s %s -> %s: spread=%.4f%% net=%.4f%% "
                        "(buy@%s sell@%s) [%s]",
                        spread.symbol,
                        spread.buy_exchange,
                        spread.sell_exchange,
                        spread.spread_pct,
                        spread.net_spread,
                        buy_p,
                        sell_p,
                        depth,
                    )
                else:
                    logger.debug(
                        "  %s -> %s: spread=%.4f%% net=%.4f%% "
                        "(buy@%s sell@%s) [%s]",
                        spread.buy_exchange,
                        spread.sell_exchange,
                        spread.spread_pct,
                        spread.net_spread,
                        buy_p,
                        sell_p,
                        depth,
                    )


async def log_funding_spreads(
    cache: RedisCache,
    exchanges: list[str],
    symbols: list[str],
    interval: int,
    min_annualized_pct: float,
    min_cross_spread_pct: float,
) -> None:
    """Periodically log funding rate opportunities."""
    while True:
        await asyncio.sleep(interval)

        for symbol in symbols:
            entries: dict[str, FundingRateEntry] = {}
            for exchange_id in exchanges:
                raw = await cache.get_funding(exchange_id, symbol)
                if raw:
                    entries[exchange_id] = FundingRateEntry.from_json(raw)

            # Spot + Perps basis trade per exchange
            for exchange_id, entry in entries.items():
                arb = SpotFundingArb.calculate(entry, min_annualized_pct)
                if arb:
                    logger.debug(
                        "*** FUNDING ARB *** %s on %s: %s rate=%.4f%% "
                        "annualized=%.2f%% (%s)",
                        arb.symbol,
                        arb.exchange,
                        arb.direction,
                        entry.funding_rate_pct,
                        arb.annualized_rate,
                        arb.direction.replace("_", " "),
                    )

            # Cross-exchange funding spread
            if len(entries) < 2:
                continue

            for ex_a, ex_b in combinations(entries.keys(), 2):
                spread = FundingRateSpread.calculate(entries[ex_a], entries[ex_b])
                if abs(spread.spread) < min_cross_spread_pct:
                    continue

                logger.debug(
                    "*** FUNDING SPREAD *** %s: %s(%.4f%%) -> %s(%.4f%%) "
                    "spread=%.6f annualized=%.2f%%",
                    spread.symbol,
                    spread.high_exchange,
                    spread.high_rate * 100,
                    spread.low_exchange,
                    spread.low_rate * 100,
                    spread.spread,
                    spread.annualized_spread,
                )


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.logging.level)

    logger.info("Starting XGE - Crypto Arbitrage Monitor")
    logger.info("Exchanges: %s", [e.id for e in settings.enabled_exchanges])
    logger.info("Symbols: %s", settings.symbols)

    fee_map = {e.id: e.taker_fee_pct for e in settings.enabled_exchanges}

    cache = RedisCache(
        host=settings.redis.host,
        port=settings.redis.port,
        url=settings.redis.url,
    )
    await cache.connect()

    collectors: list[WSPriceCollector] = []
    for exchange_cfg in settings.enabled_exchanges:
        collector = WSPriceCollector(
            exchange_id=exchange_cfg.id,
            symbols=settings.symbols,
            cache=cache,
        )
        try:
            await collector.connect()
            collectors.append(collector)
        except Exception as e:
            logger.warning(
                "Failed to connect price collector for %s: %s (skipping)",
                exchange_cfg.id, e,
            )

    # Funding rate collectors
    funding_collectors: list[FundingRateCollector] = []
    if settings.funding.enabled:
        funding_exchanges = [
            e for e in settings.enabled_exchanges
            if e.id not in settings.funding.excluded_exchanges
        ]
        logger.info(
            "Funding monitoring enabled for exchanges: %s",
            [e.id for e in funding_exchanges],
        )
        for exchange_cfg in funding_exchanges:
            fc = FundingRateCollector(
                exchange_id=exchange_cfg.id,
                symbols=settings.symbols,
                cache=cache,
                poll_interval=settings.funding.poll_interval,
            )
            try:
                await fc.connect()
                funding_collectors.append(fc)
            except Exception as e:
                logger.warning(
                    "Failed to connect funding collector for %s: %s (skipping)",
                    exchange_cfg.id, e,
                )

    # Basis trade strategy
    trading_strategy = None
    trading_executor = None
    if settings.trading.enabled:
        from xge.trading import TradeExecutor, PositionManager, BasisTradeStrategy

        trading_executor = TradeExecutor(paper=settings.trading.paper_trading)
        position_manager = PositionManager(
            cache=cache,
            max_positions_per_exchange=settings.trading.max_positions_per_exchange,
            max_total_positions=settings.trading.max_total_positions,
        )

        # Determine which exchanges to trade on
        if settings.trading.exchanges:
            trading_exchange_ids = settings.trading.exchanges
        else:
            trading_exchange_ids = [
                e.id for e in settings.enabled_exchanges
                if e.id not in settings.funding.excluded_exchanges
            ]

        for eid in trading_exchange_ids:
            await trading_executor.connect_exchange(eid)

        trading_strategy = BasisTradeStrategy(
            cache=cache,
            executor=trading_executor,
            position_manager=position_manager,
            config=settings.trading,
            exchanges=trading_exchange_ids,
            symbols=settings.symbols,
            funding_poll_interval=settings.funding.poll_interval,
        )

        mode = "PAPER" if settings.trading.paper_trading else "LIVE"
        logger.info(
            "Trading enabled [%s] on exchanges: %s",
            mode, trading_exchange_ids,
        )

    # Set up graceful shutdown
    stop_event = asyncio.Event()

    def handle_signal() -> None:
        logger.info("Shutdown signal received, stopping...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Run all collectors + spread logger concurrently
    exchange_ids = [e.id for e in settings.enabled_exchanges]
    tasks = [
        asyncio.create_task(c.subscribe()) for c in collectors
    ]
    tasks.append(
        asyncio.create_task(
            log_spreads(
                cache, exchange_ids, settings.symbols,
                settings.logging.heartbeat_interval,
                fee_map, settings.logging.min_net_spread,
            )
        )
    )

    # Funding tasks
    if settings.funding.enabled:
        for fc in funding_collectors:
            tasks.append(asyncio.create_task(fc.subscribe()))

        funding_exchange_ids = [
            e.id for e in settings.enabled_exchanges
            if e.id not in settings.funding.excluded_exchanges
        ]
        tasks.append(
            asyncio.create_task(
                log_funding_spreads(
                    cache,
                    funding_exchange_ids,
                    settings.symbols,
                    settings.funding.log_interval,
                    settings.funding.min_annualized_pct,
                    settings.funding.min_cross_spread_pct,
                )
            )
        )

    # Trading strategy task
    if trading_strategy:
        tasks.append(asyncio.create_task(trading_strategy.run()))

    # Wait for stop signal, then cancel everything
    await stop_event.wait()

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Cleanup
    if trading_strategy:
        trading_strategy.stop()
    if trading_executor:
        await trading_executor.disconnect()
    for collector in collectors:
        await collector.disconnect()
    for fc in funding_collectors:
        await fc.disconnect()
    await cache.close()

    logger.info("XGE stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
