from __future__ import annotations

import asyncio
import logging
from time import time
from typing import TYPE_CHECKING

from xge.cache.redis_cache import RedisCache
from xge.config import TradingConfig
from xge.models import OrderBookEntry
from xge.models_funding import FundingRateEntry, SpotFundingArb, spot_to_perp
from xge.models_trading import TradeSignal, Position
from xge.trading.executor import TradeExecutor
from xge.trading.position_manager import PositionManager

if TYPE_CHECKING:
    from xge.notifications.email import EmailNotifier

logger = logging.getLogger("xge.trading.strategy")


class BasisTradeStrategy:
    """Automated basis trade strategy: long spot + short perp when funding is high."""

    def __init__(
        self,
        cache: RedisCache,
        executor: TradeExecutor,
        position_manager: PositionManager,
        config: TradingConfig,
        exchanges: list[str],
        symbols: list[str],
        funding_poll_interval: int = 300,
        notifier: EmailNotifier | None = None,
    ) -> None:
        self._cache = cache
        self._executor = executor
        self._pm = position_manager
        self._config = config
        self._exchanges = exchanges
        self._symbols = symbols
        self._funding_poll_interval = funding_poll_interval
        self._notifier = notifier
        self._running = False
        self._cycle_count = 0

    async def run(self) -> None:
        """Main strategy loop."""
        self._running = True
        mode = "PAPER" if self._executor.paper else "LIVE"
        logger.info(
            "Basis trade strategy started [%s] — check every %ds, "
            "entry >= %.1f%%, exit <= %.1f%%",
            mode,
            self._config.check_interval,
            self._config.min_entry_annualized_pct,
            self._config.min_exit_annualized_pct,
        )

        while self._running:
            try:
                await self._check_entries()
                await self._check_exits()
                self._cycle_count += 1
                if self._cycle_count % 10 == 0:
                    await self._log_pnl_summary()
            except Exception:
                logger.exception("Error in strategy loop")

            await asyncio.sleep(self._config.check_interval)

    def stop(self) -> None:
        """Signal the strategy to stop."""
        self._running = False
        logger.info("Basis trade strategy stopping")

    async def _check_entries(self) -> None:
        """Check for new entry opportunities across all exchanges/symbols."""
        for exchange_id in self._exchanges:
            for symbol in self._symbols:
                await self._evaluate_entry(exchange_id, symbol)

    async def _evaluate_entry(self, exchange_id: str, symbol: str) -> None:
        """Evaluate a single exchange/symbol for entry."""
        raw = await self._cache.get_funding(exchange_id, symbol)
        if not raw:
            return

        entry = FundingRateEntry.from_json(raw)

        # Skip stale data (> 2x poll interval)
        age = time() - entry.timestamp
        if age > self._funding_poll_interval * 2:
            return

        # Only positive funding (long spot + short perp)
        if entry.funding_rate <= 0:
            return

        arb = SpotFundingArb.calculate(
            entry, self._config.min_entry_annualized_pct,
        )
        if not arb or arb.direction != "long_spot_short_perp":
            return

        allowed, reason = await self._pm.can_open(exchange_id, symbol)
        if not allowed:
            logger.debug(
                "Cannot open %s on %s: %s", symbol, exchange_id, reason,
            )
            return

        perp_symbol = spot_to_perp(symbol)
        signal = TradeSignal(
            action="open",
            exchange=exchange_id,
            symbol=symbol,
            perp_symbol=perp_symbol,
            direction="long_spot_short_perp",
            size_usdt=self._config.position_size_usdt,
            funding_rate=entry.funding_rate,
            annualized_rate=arb.annualized_rate,
            reason=f"Funding annualized {arb.annualized_rate:.1f}% >= {self._config.min_entry_annualized_pct}%",
        )

        try:
            spot_fill, perp_fill = await self._executor.execute_open(signal)
        except Exception:
            logger.exception(
                "Failed to execute open for %s on %s", symbol, exchange_id,
            )
            return

        position = Position(
            exchange=exchange_id,
            symbol=symbol,
            perp_symbol=perp_symbol,
            direction="long_spot_short_perp",
            status="open",
            size_usdt=self._config.position_size_usdt,
            spot_entry_price=spot_fill.price,
            spot_quantity=spot_fill.quantity,
            perp_entry_price=perp_fill.price,
            perp_quantity=perp_fill.quantity,
            entry_funding_rate=entry.funding_rate,
            entry_annualized_rate=arb.annualized_rate,
            paper=self._executor.paper,
        )
        await self._pm.save_position(position)

        mode = "PAPER" if self._executor.paper else "LIVE"
        logger.warning(
            "[%s] OPENED %s on %s: size=$%.0f, funding=%.4f%% (%.1f%% ann)",
            mode, symbol, exchange_id,
            self._config.position_size_usdt,
            entry.funding_rate * 100,
            arb.annualized_rate,
        )

        if self._notifier:
            try:
                await asyncio.to_thread(self._notifier.send_trade_opened, position)
            except Exception:
                logger.exception("Failed to send trade opened notification")

    async def _check_exits(self) -> None:
        """Check all open positions for exit conditions."""
        positions = await self._pm.get_all_positions()
        for position in positions:
            if position.status != "open":
                continue
            await self._evaluate_exit(position)

    async def _evaluate_exit(self, position: Position) -> None:
        """Evaluate a single position for exit."""
        raw = await self._cache.get_funding(position.exchange, position.symbol)
        if not raw:
            return

        entry = FundingRateEntry.from_json(raw)

        # Skip stale data
        age = time() - entry.timestamp
        if age > self._funding_poll_interval * 2:
            return

        annualized = entry.funding_rate * 3 * 365 * 100

        # Exit conditions: funding dropped below threshold OR turned negative
        should_exit = False
        reason = ""

        if entry.funding_rate < 0:
            should_exit = True
            reason = f"Funding turned negative ({annualized:.1f}% ann)"
        elif annualized < self._config.min_exit_annualized_pct:
            should_exit = True
            reason = (
                f"Funding annualized {annualized:.1f}% < "
                f"{self._config.min_exit_annualized_pct}%"
            )

        if not should_exit:
            return

        signal = TradeSignal(
            action="close",
            exchange=position.exchange,
            symbol=position.symbol,
            perp_symbol=position.perp_symbol,
            direction=position.direction,
            size_usdt=position.size_usdt,
            funding_rate=entry.funding_rate,
            annualized_rate=annualized,
            reason=reason,
        )

        try:
            spot_fill, perp_fill = await self._executor.execute_close(
                signal, position.spot_quantity, position.perp_quantity,
            )
        except Exception:
            logger.exception(
                "Failed to execute close for %s on %s",
                position.symbol, position.exchange,
            )
            return

        position.spot_exit_price = spot_fill.price
        position.perp_exit_price = perp_fill.price
        position.status = "closed"
        position.closed_at = time()
        position.realized_pnl = position.calculate_pnl()

        await self._pm.save_position(position)

        mode = "PAPER" if self._executor.paper else "LIVE"
        logger.warning(
            "[%s] CLOSED %s on %s: PnL=$%.4f, reason=%s",
            mode, position.symbol, position.exchange,
            position.realized_pnl, reason,
        )

        if self._notifier:
            try:
                await asyncio.to_thread(self._notifier.send_trade_closed, position)
            except Exception:
                logger.exception("Failed to send trade closed notification")

    async def _log_pnl_summary(self) -> None:
        """Log a periodic P&L summary (realized + unrealized)."""
        try:
            # Realized P&L from trade history
            history = await self._pm.get_trade_history()
            realized_pnl = sum(t.realized_pnl for t in history)

            # Unrealized P&L from open positions
            open_positions = await self._pm.get_all_positions()
            unrealized_pnl = 0.0
            for pos in open_positions:
                spot_raw = await self._cache.get_latest(pos.exchange, pos.symbol)
                if spot_raw:
                    spot_book = OrderBookEntry.from_json(spot_raw)
                    # Use spot price as proxy for perp price (spread < 0.1% in basis trades)
                    unrealized_pnl += pos.estimate_unrealized_pnl(
                        spot_book.mid_price, spot_book.mid_price,
                    )

            total_pnl = realized_pnl + unrealized_pnl
            mode = "PAPER" if self._executor.paper else "LIVE"
            logger.warning(
                "[P&L SUMMARY] [%s] realized=$%.4f (%d trades) | "
                "unrealized=$%.4f (%d open) | total=$%.4f",
                mode, realized_pnl, len(history),
                unrealized_pnl, len(open_positions), total_pnl,
            )
        except Exception:
            logger.exception("Error computing P&L summary")
