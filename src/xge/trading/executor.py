from __future__ import annotations

import logging
import os
from time import time

import ccxt.pro as ccxtpro

from xge.models_trading import TradeSignal, LegFill

logger = logging.getLogger("xge.trading.executor")


class TradeExecutor:
    """Executes trades on exchanges, either paper or live."""

    def __init__(self, paper: bool = True) -> None:
        self._paper = paper
        self._exchanges: dict[str, ccxtpro.Exchange] = {}

    @property
    def paper(self) -> bool:
        return self._paper

    async def connect_exchange(self, exchange_id: str) -> None:
        """Connect to an exchange via ccxt.pro."""
        if exchange_id in self._exchanges:
            return

        exchange_class = getattr(ccxtpro, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")

        upper = exchange_id.upper()
        api_key = os.environ.get(f"{upper}_API_KEY", "")
        secret = os.environ.get(f"{upper}_SECRET", "")
        password = os.environ.get(f"{upper}_PASSWORD", "")

        config: dict = {"enableRateLimit": True}

        if api_key and secret:
            config["apiKey"] = api_key
            config["secret"] = secret
            if password:
                config["password"] = password
            logger.info("Connecting to %s with API credentials", exchange_id)
        elif not self._paper:
            raise ValueError(
                f"Live trading requires API keys for {exchange_id}. "
                f"Set {upper}_API_KEY and {upper}_SECRET environment variables."
            )
        else:
            logger.info(
                "Connecting to %s without credentials (paper mode)", exchange_id,
            )

        exchange = exchange_class(config)
        self._exchanges[exchange_id] = exchange
        logger.info("Connected to %s", exchange_id)

    async def execute_open(
        self, signal: TradeSignal,
    ) -> tuple[LegFill, LegFill]:
        """Execute an open trade (buy spot + short perp).

        In paper mode, simulates fills using current ticker prices.
        """
        exchange = self._exchanges.get(signal.exchange)
        if not exchange:
            raise RuntimeError(f"Exchange {signal.exchange} not connected")

        if self._paper:
            return await self._paper_open(exchange, signal)
        return await self._live_open(exchange, signal)

    async def execute_close(
        self, signal: TradeSignal, spot_quantity: float, perp_quantity: float,
    ) -> tuple[LegFill, LegFill]:
        """Execute a close trade (sell spot + buy/close perp).

        In paper mode, simulates fills using current ticker prices.
        """
        exchange = self._exchanges.get(signal.exchange)
        if not exchange:
            raise RuntimeError(f"Exchange {signal.exchange} not connected")

        if self._paper:
            return await self._paper_close(exchange, signal, spot_quantity, perp_quantity)
        return await self._live_close(exchange, signal, spot_quantity, perp_quantity)

    async def _paper_open(
        self, exchange: ccxtpro.Exchange, signal: TradeSignal,
    ) -> tuple[LegFill, LegFill]:
        """Simulate open using ticker prices."""
        spot_ticker = await exchange.fetch_ticker(signal.symbol)
        perp_ticker = await exchange.fetch_ticker(signal.perp_symbol)

        spot_price = float(spot_ticker["ask"] or spot_ticker["last"])
        perp_price = float(perp_ticker["bid"] or perp_ticker["last"])

        spot_quantity = signal.size_usdt / spot_price
        perp_quantity = signal.size_usdt / perp_price

        now = time()
        spot_fill = LegFill(
            side="buy",
            market_type="spot",
            symbol=signal.symbol,
            price=spot_price,
            quantity=spot_quantity,
            fee=signal.size_usdt * 0.001,  # 0.1% estimated
            timestamp=now,
        )
        perp_fill = LegFill(
            side="sell",
            market_type="perp",
            symbol=signal.perp_symbol,
            price=perp_price,
            quantity=perp_quantity,
            fee=signal.size_usdt * 0.001,
            timestamp=now,
        )

        logger.info(
            "[PAPER] OPEN %s on %s: spot buy %.6f @ %.2f, perp sell %.6f @ %.2f",
            signal.symbol, signal.exchange,
            spot_quantity, spot_price, perp_quantity, perp_price,
        )
        return spot_fill, perp_fill

    async def _paper_close(
        self,
        exchange: ccxtpro.Exchange,
        signal: TradeSignal,
        spot_quantity: float,
        perp_quantity: float,
    ) -> tuple[LegFill, LegFill]:
        """Simulate close using ticker prices."""
        spot_ticker = await exchange.fetch_ticker(signal.symbol)
        perp_ticker = await exchange.fetch_ticker(signal.perp_symbol)

        spot_price = float(spot_ticker["bid"] or spot_ticker["last"])
        perp_price = float(perp_ticker["ask"] or perp_ticker["last"])

        now = time()
        notional = spot_price * spot_quantity
        spot_fill = LegFill(
            side="sell",
            market_type="spot",
            symbol=signal.symbol,
            price=spot_price,
            quantity=spot_quantity,
            fee=notional * 0.001,
            timestamp=now,
        )
        perp_fill = LegFill(
            side="buy",
            market_type="perp",
            symbol=signal.perp_symbol,
            price=perp_price,
            quantity=perp_quantity,
            fee=perp_price * perp_quantity * 0.001,
            timestamp=now,
        )

        logger.info(
            "[PAPER] CLOSE %s on %s: spot sell %.6f @ %.2f, perp buy %.6f @ %.2f",
            signal.symbol, signal.exchange,
            spot_quantity, spot_price, perp_quantity, perp_price,
        )
        return spot_fill, perp_fill

    async def _live_open(
        self, exchange: ccxtpro.Exchange, signal: TradeSignal,
    ) -> tuple[LegFill, LegFill]:
        """Execute real open orders."""
        spot_ticker = await exchange.fetch_ticker(signal.symbol)
        spot_price = float(spot_ticker["ask"] or spot_ticker["last"])
        spot_quantity = signal.size_usdt / spot_price

        perp_ticker = await exchange.fetch_ticker(signal.perp_symbol)
        perp_price = float(perp_ticker["bid"] or perp_ticker["last"])
        perp_quantity = signal.size_usdt / perp_price

        spot_order = await exchange.create_market_buy_order(
            signal.symbol, spot_quantity,
        )
        perp_order = await exchange.create_market_sell_order(
            signal.perp_symbol, perp_quantity,
        )

        now = time()
        spot_fill = LegFill(
            side="buy",
            market_type="spot",
            symbol=signal.symbol,
            price=float(spot_order.get("average", spot_price)),
            quantity=float(spot_order.get("filled", spot_quantity)),
            fee=float(spot_order.get("fee", {}).get("cost", 0.0)),
            timestamp=now,
        )
        perp_fill = LegFill(
            side="sell",
            market_type="perp",
            symbol=signal.perp_symbol,
            price=float(perp_order.get("average", perp_price)),
            quantity=float(perp_order.get("filled", perp_quantity)),
            fee=float(perp_order.get("fee", {}).get("cost", 0.0)),
            timestamp=now,
        )

        logger.warning(
            "[LIVE] OPEN %s on %s: spot buy %.6f @ %.2f, perp sell %.6f @ %.2f",
            signal.symbol, signal.exchange,
            spot_fill.quantity, spot_fill.price,
            perp_fill.quantity, perp_fill.price,
        )
        return spot_fill, perp_fill

    async def _live_close(
        self,
        exchange: ccxtpro.Exchange,
        signal: TradeSignal,
        spot_quantity: float,
        perp_quantity: float,
    ) -> tuple[LegFill, LegFill]:
        """Execute real close orders."""
        spot_order = await exchange.create_market_sell_order(
            signal.symbol, spot_quantity,
        )
        perp_order = await exchange.create_market_buy_order(
            signal.perp_symbol, perp_quantity,
        )

        now = time()
        spot_fill = LegFill(
            side="sell",
            market_type="spot",
            symbol=signal.symbol,
            price=float(spot_order.get("average", 0)),
            quantity=float(spot_order.get("filled", spot_quantity)),
            fee=float(spot_order.get("fee", {}).get("cost", 0.0)),
            timestamp=now,
        )
        perp_fill = LegFill(
            side="buy",
            market_type="perp",
            symbol=signal.perp_symbol,
            price=float(perp_order.get("average", 0)),
            quantity=float(perp_order.get("filled", perp_quantity)),
            fee=float(perp_order.get("fee", {}).get("cost", 0.0)),
            timestamp=now,
        )

        logger.warning(
            "[LIVE] CLOSE %s on %s: spot sell %.6f @ %.2f, perp buy %.6f @ %.2f",
            signal.symbol, signal.exchange,
            spot_fill.quantity, spot_fill.price,
            perp_fill.quantity, perp_fill.price,
        )
        return spot_fill, perp_fill

    async def disconnect(self) -> None:
        """Close all exchange connections."""
        for exchange_id, exchange in self._exchanges.items():
            try:
                await exchange.close()
                logger.info("Disconnected from %s", exchange_id)
            except Exception:
                logger.exception("Error disconnecting from %s", exchange_id)
        self._exchanges.clear()
