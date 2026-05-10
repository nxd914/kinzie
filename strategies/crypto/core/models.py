"""Core research data structures for normalized L2 order-book snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class BookLevel:
    """One price level in a limit order book."""

    price: float
    volume: float

    def to_dict(self) -> dict[str, float]:
        return {"price": self.price, "volume": self.volume}

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | list[Any] | tuple[Any, ...]) -> BookLevel:
        if isinstance(raw, dict):
            return cls(price=float(raw["price"]), volume=float(raw["volume"]))
        return cls(price=float(raw[0]), volume=float(raw[1]))


@dataclass(frozen=True)
class L2Snapshot:
    """Normalized top-N L2 order-book snapshot."""

    exchange: str
    symbol: str
    timestamp: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    sequence: int

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> float:
        if self.best_bid is None or self.best_ask is None:
            return float("nan")
        return self.best_ask.price - self.best_bid.price

    @property
    def mid(self) -> float:
        if self.best_bid is None or self.best_ask is None:
            return float("nan")
        return (self.best_bid.price + self.best_ask.price) / 2.0

    @property
    def volume_weighted_mid(self) -> float:
        levels = self.bids + self.asks
        total_volume = sum(level.volume for level in levels)
        if total_volume <= 0:
            return self.mid
        return sum(level.price * level.volume for level in levels) / total_volume

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "bids": [level.to_dict() for level in self.bids],
            "asks": [level.to_dict() for level in self.asks],
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> L2Snapshot:
        timestamp = raw["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return cls(
            exchange=str(raw["exchange"]),
            symbol=str(raw["symbol"]),
            timestamp=timestamp,
            bids=tuple(BookLevel.from_raw(level) for level in raw["bids"]),
            asks=tuple(BookLevel.from_raw(level) for level in raw["asks"]),
            sequence=int(raw.get("sequence", 0)),
        )
