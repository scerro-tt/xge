"""Basis trade strategy with tier-based capital allocation.

Integrates pair selection, breakeven validation, tier-based sizing,
advanced exit criteria, and capital protection.
"""
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
from xge.trading.breakeven import calculate_breakeven
from xge.trading.executor import TradeExecutor
from xge.trading.pair_selector import validate_pair
from xge.trading.position_manager import PositionManager
from xge.trading.tier_config import (
    BLACKLIST,
    CAPITAL_CONFIG,
    get_all_tier_symbols,
    get_tier_for_symbol,
)

if TYPE_CHECKING:
    from xge.notifications.email import EmailNotifier
    from xge.trading.delta_monitor import DeltaMonitor

logger = logging.getLogger("xge.trading.strategy")

# Minimum time before closing (1 funding period = 8 hours)
MIN_HOLD_SECONDS = 8 * 3600


class BasisTradeStrategy:
    """Automated basis trade strategy with tier-based capital allocation."""

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
        delta_monitor: DeltaMonitor | None = None,
    ) -> None:
        self._cache = cache
        self._executor = executor
        self._pm = position_manager
        self._config = config
        self._exchanges = exchanges
        self._symbols = symbols
        self._funding_poll_interval = funding_poll_interval
        self._notifier = notifier
        self._delta_monitor = delta_monitor
        self._running = False
        self._cycle_count = 0

    async def run(self) -> None:
        """Main strategy loop."""
        self._running = True
        mode = "PAPER" if self._executor.paper else "LIVE"

        # Filter symbols to only tier-eligible ones
        tier_symbols = get_all_tier_symbols()
        active_symbols = [s for s in self._symbols if s in tier_symbols]

        logger.info(
            "Basis trade strategy started [%s] — check every %ds, "
            "tier symbols: %s, blacklisted: %s",
            mode,
            self._config.check_interval,
            active_symbols,
            [s for s in self._symbols if s in BLACKLIST],
        )

        while self._running:
            try:
                await self._check_entries()
                await self._check_exits()
                self._cycle_count += 1

                # Log capital status every cycle
                await self._log_capital_status()

                if self._cycle_count % 10 == 0:
                    await self._log_pnl_summary()
            except Exception:
                logger.exception("Error in strategy loop")

            await asyncio.sleep(self._config.check_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("Basis trade strategy stopping")

    # ── Entry logic ─────────────────────────────────────────────────

    async def _check_entries(self) -> None:
        """Check for new entry opportunities across all exchanges/symbols."""
        for exchange_id in self._exchanges:
            for symbol in self._symbols:
                await self._evaluate_entry(exchange_id, symbol)

    async def _evaluate_entry(self, exchange_id: str, symbol: str) -> None:
        """Evaluate a single exchange/symbol for entry with all filters."""

        # ── Blacklist check ─────────────────────────────────────────
        if symbol in BLACKLIST:
            return

        # ── Tier check ──────────────────────────────────────────────
        tier = get_tier_for_symbol(symbol)
        if tier is None:
            return

        # ── Funding data ────────────────────────────────────────────
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

        # ── Tier-specific minimum funding rate ──────────────────────
        if entry.funding_rate < tier["min_funding_rate"]:
            return

        arb = SpotFundingArb.calculate(
            entry, self._config.min_entry_annualized_pct,
        )
        if not arb or arb.direction != "long_spot_short_perp":
            return

        # ── Capital validation ──────────────────────────────────────
        capital_check = await self._check_capital_available(tier, exchange_id)
        if not capital_check["can_open"]:
            logger.debug(
                "Cannot open %s on %s: %s",
                symbol, exchange_id, capital_check["reason"],
            )
            return

        # ── Position manager check ──────────────────────────────────
        allowed, reason = await self._pm.can_open(exchange_id, symbol)
        if not allowed:
            logger.debug(
                "Cannot open %s on %s: %s", symbol, exchange_id, reason,
            )
            return

        perp_symbol = spot_to_perp(symbol)
        size_usdt = tier["size_per_pair"]

        # ── Breakeven validation ────────────────────────────────────
        spot_raw = await self._cache.get_latest(exchange_id, symbol)
        if not spot_raw:
            return
        spot_book = OrderBookEntry.from_json(spot_raw)

        be = calculate_breakeven(
            size_usdt=size_usdt,
            spot_entry_price=spot_book.ask,
            perp_entry_price=spot_book.bid,  # proxy
            funding_rate=entry.funding_rate,
            exchange=exchange_id,
        )

        if not be["viable"]:
            logger.debug(
                "[%s:%s] Breakeven not viable: %.1f periods (%.1f hours), "
                "need < 9 periods. Funding=%.4f%%",
                exchange_id, symbol,
                be["breakeven_periods"], be["breakeven_hours"],
                entry.funding_rate * 100,
            )
            return

        # ── Pair validation (funding history, spread, volume, OI) ───
        exchange_obj = self._executor._exchanges.get(exchange_id)
        if exchange_obj:
            try:
                pair_check = await validate_pair(
                    exchange_obj, exchange_id, symbol, perp_symbol,
                )
                if not pair_check["approved"]:
                    logger.debug(
                        "[%s:%s] Pair validation failed: %s",
                        exchange_id, symbol, pair_check["reasons"],
                    )
                    return
            except Exception:
                logger.exception(
                    "Pair validation error for %s on %s", symbol, exchange_id,
                )
                return

        # ── Execute entry ───────────────────────────────────────────
        signal = TradeSignal(
            action="open",
            exchange=exchange_id,
            symbol=symbol,
            perp_symbol=perp_symbol,
            direction="long_spot_short_perp",
            size_usdt=size_usdt,
            funding_rate=entry.funding_rate,
            annualized_rate=arb.annualized_rate,
            reason=(
                f"Funding {arb.annualized_rate:.1f}% ann, "
                f"breakeven {be['breakeven_periods']:.1f} periods, "
                f"tier={tier['name']}"
            ),
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
            size_usdt=size_usdt,
            spot_entry_price=spot_fill.price,
            spot_quantity=spot_fill.quantity,
            perp_entry_price=perp_fill.price,
            perp_quantity=perp_fill.quantity,
            entry_funding_rate=entry.funding_rate,
            entry_annualized_rate=arb.annualized_rate,
            paper=self._executor.paper,
            tier=tier["name"],
        )
        await self._pm.save_position(position)

        mode = "PAPER" if self._executor.paper else "LIVE"
        logger.warning(
            "[%s] OPENED %s on %s: size=$%.0f tier=%s, "
            "funding=%.4f%% (%.1f%% ann), breakeven=%.1f periods",
            mode, symbol, exchange_id,
            size_usdt, tier["name"],
            entry.funding_rate * 100, arb.annualized_rate,
            be["breakeven_periods"],
        )

        if self._notifier:
            try:
                await asyncio.to_thread(self._notifier.send_trade_opened, position)
            except Exception:
                logger.exception("Failed to send trade opened notification")

    # ── Exit logic ──────────────────────────────────────────────────

    async def _check_exits(self) -> None:
        """Check all open positions for exit conditions."""
        positions = await self._pm.get_all_positions()

        # ── Reserve protection check ────────────────────────────────
        await self._check_reserve_protection(positions)

        for position in positions:
            if position.status != "open":
                continue
            await self._accumulate_funding(position)
            await self._evaluate_exit(position)

    async def _accumulate_funding(self, position: Position) -> None:
        """Accumulate funding payments for an open position."""
        raw = await self._cache.get_funding(position.exchange, position.symbol)
        if not raw:
            return

        entry = FundingRateEntry.from_json(raw)

        # Skip stale data
        age = time() - entry.timestamp
        if age > self._funding_poll_interval * 2:
            return

        # Get current price as mark price proxy
        spot_raw = await self._cache.get_latest(position.exchange, position.symbol)
        if not spot_raw:
            return
        spot_book = OrderBookEntry.from_json(spot_raw)
        mark_price = spot_book.mid_price

        now = time()
        elapsed = now - position.last_funding_update

        funding_payment = (
            position.perp_quantity * mark_price * entry.funding_rate * (elapsed / 28800)
        )

        position.funding_collected += funding_payment
        position.last_funding_update = now
        await self._pm.save_position(position)

        logger.debug(
            "Funding accrual %s on %s: +$%.6f (rate=%.4f%%, total=$%.6f)",
            position.symbol, position.exchange,
            funding_payment, entry.funding_rate * 100,
            position.funding_collected,
        )

    async def _evaluate_exit(self, position: Position) -> None:
        """Evaluate a single position for exit with advanced criteria."""
        raw = await self._cache.get_funding(position.exchange, position.symbol)
        if not raw:
            return

        entry = FundingRateEntry.from_json(raw)

        # Skip stale data
        age = time() - entry.timestamp
        if age > self._funding_poll_interval * 2:
            return

        annualized = entry.funding_rate * 3 * 365 * 100
        now = time()
        hold_time = now - position.opened_at

        should_exit = False
        exit_reason = ""

        # ── a) FUNDING DROP: < 70% of entry rate ───────────────────
        if (
            entry.funding_rate > 0
            and position.entry_funding_rate > 0
            and entry.funding_rate < position.entry_funding_rate * 0.70
        ):
            # Only exit if past minimum hold time
            if hold_time >= MIN_HOLD_SECONDS:
                should_exit = True
                exit_reason = "funding_drop"
                logger.warning(
                    "[%s:%s] FUNDING DROP: current=%.6f < 70%% of entry=%.6f",
                    position.exchange, position.symbol,
                    entry.funding_rate, position.entry_funding_rate,
                )

        # ── b) FUNDING NEGATIVE: 2 consecutive periods ─────────────
        if entry.funding_rate < 0 and self._delta_monitor:
            neg_count = self._delta_monitor.track_negative_funding(
                position.exchange, position.symbol, True,
            )
            if neg_count >= 2:
                should_exit = True
                exit_reason = "funding_negative"
                logger.critical(
                    "[%s:%s] FUNDING NEGATIVE x%d: rate=%.6f — immediate close",
                    position.exchange, position.symbol,
                    neg_count, entry.funding_rate,
                )
        elif entry.funding_rate >= 0 and self._delta_monitor:
            self._delta_monitor.track_negative_funding(
                position.exchange, position.symbol, False,
            )

        # ── c) STOP LOSS per tier ──────────────────────────────────
        if not should_exit:
            tier = get_tier_for_symbol(position.symbol)
            if tier:
                stop_loss_limit = -(tier["size_per_pair"] * tier["stop_loss_pct"])

                # Estimate current unrealized PnL
                spot_raw = await self._cache.get_latest(
                    position.exchange, position.symbol,
                )
                if spot_raw:
                    spot_book = OrderBookEntry.from_json(spot_raw)
                    unrealized = position.estimate_unrealized_pnl(
                        spot_book.mid_price, spot_book.mid_price,
                    )

                    # Only trigger if funding doesn't cover the loss
                    if unrealized < stop_loss_limit and position.funding_collected < abs(unrealized):
                        should_exit = True
                        exit_reason = "stop_loss"
                        logger.critical(
                            "[%s:%s] STOP LOSS: unrealized=$%.4f < limit=$%.4f, "
                            "funding=$%.4f doesn't cover",
                            position.exchange, position.symbol,
                            unrealized, stop_loss_limit,
                            position.funding_collected,
                        )

        # ── d) Original exit: funding below min_exit threshold ──────
        if not should_exit:
            if entry.funding_rate < 0:
                # Single negative period (below 2 threshold) — still evaluate
                if hold_time >= MIN_HOLD_SECONDS:
                    should_exit = True
                    exit_reason = "funding_negative"
            elif annualized < self._config.min_exit_annualized_pct:
                if hold_time >= MIN_HOLD_SECONDS:
                    should_exit = True
                    exit_reason = "funding_drop"

        # ── d) MINIMUM HOLD: skip exit if too early (except stop loss) ──
        if should_exit and exit_reason not in ("stop_loss", "funding_negative", "reserve_protection"):
            if hold_time < MIN_HOLD_SECONDS:
                logger.debug(
                    "[%s:%s] Minimum hold not met: %.1fh < 8h, skipping exit",
                    position.exchange, position.symbol,
                    hold_time / 3600,
                )
                should_exit = False

        if not should_exit:
            return

        await self._execute_exit(position, exit_reason, entry.funding_rate, annualized)

    async def _execute_exit(
        self,
        position: Position,
        exit_reason: str,
        current_funding_rate: float,
        annualized: float,
    ) -> None:
        """Execute position exit."""
        reason_text = (
            f"{exit_reason}: funding={current_funding_rate:.6f} "
            f"({annualized:.1f}% ann)"
        )

        signal = TradeSignal(
            action="close",
            exchange=position.exchange,
            symbol=position.symbol,
            perp_symbol=position.perp_symbol,
            direction=position.direction,
            size_usdt=position.size_usdt,
            funding_rate=current_funding_rate,
            annualized_rate=annualized,
            reason=reason_text,
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
        position.exit_reason = exit_reason

        await self._pm.save_position(position)

        # Reset tracking
        if self._delta_monitor:
            self._delta_monitor.reset_tracking(position.exchange, position.symbol)

        mode = "PAPER" if self._executor.paper else "LIVE"
        logger.warning(
            "[%s] CLOSED %s on %s: PnL=$%.4f, funding=$%.4f, reason=%s, "
            "held %.1fh",
            mode, position.symbol, position.exchange,
            position.realized_pnl, position.funding_collected,
            exit_reason,
            (position.closed_at - position.opened_at) / 3600,
        )

        if self._notifier:
            try:
                await asyncio.to_thread(self._notifier.send_trade_closed, position)
            except Exception:
                logger.exception("Failed to send trade closed notification")

    # ── Reserve protection ──────────────────────────────────────────

    async def _check_reserve_protection(self, positions: list[Position]) -> None:
        """Close Tier 2 positions first if total balance drops below operative threshold."""
        if not positions:
            return

        # Estimate total balance
        history = await self._pm.get_trade_history()
        total_realized = sum(t.realized_pnl for t in history)
        estimated_balance = CAPITAL_CONFIG["total"] + total_realized

        if estimated_balance >= CAPITAL_CONFIG["operative"]:
            return

        logger.critical(
            "[RESERVE PROTECTION] Balance $%.2f < operative $%d — "
            "closing Tier 2 positions first",
            estimated_balance, CAPITAL_CONFIG["operative"],
        )

        # Close Tier 2 first, then evaluate Tier 1
        for tier_name in ("tier_2", "tier_1"):
            tier_positions = [
                p for p in positions
                if p.status == "open" and p.tier == tier_name
            ]
            for pos in tier_positions:
                raw = await self._cache.get_funding(pos.exchange, pos.symbol)
                rate = 0.0
                if raw:
                    fe = FundingRateEntry.from_json(raw)
                    rate = fe.funding_rate

                await self._execute_exit(
                    pos, "reserve_protection", rate, rate * 3 * 365 * 100,
                )

            # Re-check after closing tier
            history = await self._pm.get_trade_history()
            total_realized = sum(t.realized_pnl for t in history)
            estimated_balance = CAPITAL_CONFIG["total"] + total_realized
            if estimated_balance >= CAPITAL_CONFIG["operative"]:
                logger.info(
                    "[RESERVE PROTECTION] Balance restored to $%.2f after closing %s",
                    estimated_balance, tier_name,
                )
                break

    # ── Capital validation ──────────────────────────────────────────

    async def _check_capital_available(
        self, tier: dict, exchange_id: str,
    ) -> dict:
        """Verify capital is available for a new position in the given tier.

        Returns:
            {
                "can_open": bool,
                "capital_deployed": float,
                "capital_free": float,
                "reserve_intact": bool,
                "pairs_open_in_tier": int,
                "reason": str,
            }
        """
        all_positions = await self._pm.get_all_positions()
        open_positions = [p for p in all_positions if p.status == "open"]

        capital_deployed = sum(p.size_usdt for p in open_positions)
        capital_free = CAPITAL_CONFIG["operative"] - capital_deployed

        # Positions in this tier
        tier_positions = [
            p for p in open_positions if p.tier == tier["name"]
        ]
        pairs_open = len(tier_positions)

        # Check reserve
        history = await self._pm.get_trade_history()
        total_realized = sum(t.realized_pnl for t in history)
        estimated_balance = CAPITAL_CONFIG["total"] + total_realized
        reserve_intact = estimated_balance >= CAPITAL_CONFIG["operative"]

        result = {
            "can_open": True,
            "capital_deployed": capital_deployed,
            "capital_free": capital_free,
            "reserve_intact": reserve_intact,
            "pairs_open_in_tier": pairs_open,
            "reason": "",
        }

        if capital_free < tier["size_per_pair"]:
            result["can_open"] = False
            result["reason"] = (
                f"Insufficient capital: free=${capital_free:.2f} < "
                f"required=${tier['size_per_pair']}"
            )
            return result

        if pairs_open >= tier["max_pairs_open"]:
            result["can_open"] = False
            result["reason"] = (
                f"Max pairs for {tier['name']}: "
                f"{pairs_open}/{tier['max_pairs_open']}"
            )
            return result

        if not reserve_intact:
            result["can_open"] = False
            result["reason"] = (
                f"Reserve compromised: balance=${estimated_balance:.2f} < "
                f"operative=${CAPITAL_CONFIG['operative']}"
            )
            return result

        return result

    # ── Logging ─────────────────────────────────────────────────────

    async def _log_capital_status(self) -> None:
        """Log capital status every cycle."""
        try:
            all_positions = await self._pm.get_all_positions()
            deployed = sum(p.size_usdt for p in all_positions if p.status == "open")
            free = CAPITAL_CONFIG["operative"] - deployed
            reserve = CAPITAL_CONFIG["reserve_rebalance"]
            logger.info(
                "[CAPITAL] Deployed: $%.2f | Free: $%.2f | Reserve: $%d",
                deployed, free, reserve,
            )
        except Exception:
            pass

    async def _log_pnl_summary(self) -> None:
        """Log a periodic P&L summary (realized + unrealized)."""
        try:
            history = await self._pm.get_trade_history()
            realized_pnl = sum(t.realized_pnl for t in history)

            open_positions = await self._pm.get_all_positions()
            unrealized_pnl = 0.0
            for pos in open_positions:
                spot_raw = await self._cache.get_latest(pos.exchange, pos.symbol)
                if spot_raw:
                    spot_book = OrderBookEntry.from_json(spot_raw)
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
