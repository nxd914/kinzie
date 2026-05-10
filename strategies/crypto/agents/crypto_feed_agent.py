"""Kraken L2 book ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from ..core.models import BookLevel, L2Snapshot

logger = logging.getLogger(__name__)

KRAKEN_WS_URL = "wss://ws.kraken.com"
INITIAL_RECONNECT_DELAY = 1.0
MAX_RECONNECT_DELAY = 60.0

_SYMBOL_TO_KRAKEN = {
    "BTC": "XBT/USD",
    "XBT": "XBT/USD",
    "ETH": "ETH/USD",
    "SOL": "SOL/USD",
    "XRP": "XRP/USD",
}
_KRAKEN_TO_SYMBOL = {
    "XBT/USD": "BTC",
    "BTC/USD": "BTC",
    "ETH/USD": "ETH",
    "SOL/USD": "SOL",
    "XRP/USD": "XRP",
}


class CryptoFeedAgent:
    """Subscribe to Kraken `book` and emit normalized top-N L2 snapshots."""

    def __init__(
        self,
        snapshot_queue: asyncio.Queue[L2Snapshot],
        symbols: list[str] | tuple[str, ...] | None = None,
        depth: int = 10,
    ) -> None:
        self._snapshot_queue = snapshot_queue
        self._symbols = tuple(symbol.upper() for symbol in (symbols or ("BTC", "ETH")))
        self._depth = depth
        self._books: dict[str, dict[str, dict[float, float]]] = {}
        self._sequences: dict[str, int] = {}

    async def run(self) -> None:
        logger.info("CryptoFeedAgent: starting Kraken book feeds for %s", self._symbols)
        await self._kraken_feed()

    async def _kraken_feed(self) -> None:
        import websockets

        pairs = [self._to_kraken_pair(symbol) for symbol in self._symbols]
        pairs = [pair for pair in pairs if pair is not None]
        if not pairs:
            logger.warning("CryptoFeedAgent: no Kraken pairs configured")
            return

        subscribe_msg = json.dumps(
            {
                "event": "subscribe",
                "pair": pairs,
                "subscription": {"name": "book", "depth": self._depth},
            }
        )
        retry_delay = INITIAL_RECONNECT_DELAY

        while True:
            try:
                async with websockets.connect(KRAKEN_WS_URL) as ws:
                    await ws.send(subscribe_msg)
                    logger.info("CryptoFeedAgent: connected to Kraken book channel (%s)", pairs)
                    retry_delay = INITIAL_RECONNECT_DELAY

                    async for raw in ws:
                        snapshot = self._parse_kraken(raw)
                        if snapshot is not None:
                            await self._snapshot_queue.put(snapshot)
            except Exception as exc:
                logger.warning(
                    "CryptoFeedAgent Kraken error: %s. Reconnecting in %.1fs",
                    exc,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(MAX_RECONNECT_DELAY, retry_delay * 2)

    def _parse_kraken(self, raw: str) -> L2Snapshot | None:
        """Apply one Kraken book message and return a normalized snapshot if possible."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(msg, list) or len(msg) < 4:
            return None

        channel_name = msg[-2]
        pair = msg[-1]
        if not isinstance(channel_name, str) or not channel_name.startswith("book-"):
            return None
        if not isinstance(pair, str):
            return None

        payloads = [part for part in msg[1:-2] if isinstance(part, dict)]
        if not payloads:
            return None

        symbol = _KRAKEN_TO_SYMBOL.get(pair, pair)
        timestamp: datetime | None = None
        for payload in payloads:
            payload_ts = self._apply_payload(pair, payload)
            if payload_ts is not None:
                timestamp = payload_ts if timestamp is None else max(timestamp, payload_ts)

        book = self._books.get(pair)
        if book is None or not book["bids"] or not book["asks"]:
            return None

        self._sequences[pair] = self._sequences.get(pair, 0) + 1
        return L2Snapshot(
            exchange="kraken",
            symbol=symbol,
            timestamp=timestamp or datetime.now(tz=UTC),
            bids=self._sorted_levels(book["bids"], reverse=True),
            asks=self._sorted_levels(book["asks"], reverse=False),
            sequence=self._sequences[pair],
        )

    def _apply_payload(self, pair: str, payload: dict[str, Any]) -> datetime | None:
        book = self._books.setdefault(pair, {"bids": {}, "asks": {}})
        if "bs" in payload or "as" in payload:
            book["bids"] = {}
            book["asks"] = {}

        latest_ts = self._apply_side(book["bids"], payload.get("bs") or payload.get("b") or [])
        ask_ts = self._apply_side(book["asks"], payload.get("as") or payload.get("a") or [])
        if ask_ts is not None:
            latest_ts = ask_ts if latest_ts is None else max(latest_ts, ask_ts)
        return latest_ts

    def _apply_side(self, side: dict[float, float], levels: list[Any]) -> datetime | None:
        latest_ts: datetime | None = None
        for raw_level in levels:
            if not isinstance(raw_level, list | tuple) or len(raw_level) < 2:
                continue
            price = float(raw_level[0])
            volume = float(raw_level[1])
            if len(raw_level) >= 3:
                level_ts = datetime.fromtimestamp(float(raw_level[2]), tz=UTC)
                latest_ts = level_ts if latest_ts is None else max(latest_ts, level_ts)
            if volume == 0:
                side.pop(price, None)
            else:
                side[price] = volume
        return latest_ts

    def _sorted_levels(self, levels: dict[float, float], *, reverse: bool) -> tuple[BookLevel, ...]:
        return tuple(
            BookLevel(price=price, volume=volume)
            for price, volume in sorted(levels.items(), reverse=reverse)[: self._depth]
        )

    def _to_kraken_pair(self, symbol: str) -> str | None:
        if "/" in symbol:
            return symbol
        return _SYMBOL_TO_KRAKEN.get(symbol.upper())
