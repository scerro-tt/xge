from __future__ import annotations

from abc import ABC, abstractmethod


class BasePriceCollector(ABC):
    """Abstract base class for price collectors."""

    def __init__(self, exchange_id: str, symbols: list[str]) -> None:
        self.exchange_id = exchange_id
        self.symbols = symbols

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the exchange."""

    @abstractmethod
    async def subscribe(self) -> None:
        """Subscribe to order book updates and stream prices."""
