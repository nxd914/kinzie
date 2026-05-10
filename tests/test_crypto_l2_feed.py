import asyncio
import json
from datetime import UTC, datetime

from strategies.crypto.agents.crypto_feed_agent import CryptoFeedAgent
from strategies.crypto.core.l2_store import L2JsonlWriter
from strategies.crypto.core.models import L2Snapshot


def _book_snapshot(pair: str = "XBT/USD") -> str:
    return json.dumps(
        [
            42,
            {
                "as": [
                    ["100.50", "1.25", "1700000000.0"],
                    ["101.00", "2.00", "1700000000.0"],
                ],
                "bs": [
                    ["100.00", "1.50", "1700000000.0"],
                    ["99.50", "2.50", "1700000000.0"],
                ],
            },
            "book-10",
            pair,
        ]
    )


def test_kraken_book_snapshot_emits_l2_snapshot():
    agent = CryptoFeedAgent(asyncio.Queue(), symbols=["BTC"], depth=10)

    snapshot = agent._parse_kraken(_book_snapshot())

    assert snapshot is not None
    assert snapshot.exchange == "kraken"
    assert snapshot.symbol == "BTC"
    assert snapshot.best_bid.price == 100.00
    assert snapshot.best_ask.price == 100.50
    assert snapshot.spread == 0.50
    assert snapshot.mid == 100.25
    assert snapshot.sequence == 1


def test_incremental_update_and_zero_volume_removal():
    agent = CryptoFeedAgent(asyncio.Queue(), symbols=["BTC"], depth=10)
    agent._parse_kraken(_book_snapshot())

    update = json.dumps(
        [
            42,
            {"a": [["100.50", "0.0", "1700000001.0"]], "b": [["99.75", "3.00", "1700000001.0"]]},
            "book-10",
            "XBT/USD",
        ]
    )
    snapshot = agent._parse_kraken(update)

    assert snapshot is not None
    assert [level.price for level in snapshot.asks] == [101.00]
    assert [level.price for level in snapshot.bids] == [100.00, 99.75, 99.50]
    assert snapshot.sequence == 2


def test_non_book_and_malformed_messages_are_ignored():
    agent = CryptoFeedAgent(asyncio.Queue(), symbols=["BTC"], depth=10)

    assert agent._parse_kraken("not json") is None
    assert agent._parse_kraken(json.dumps({"event": "heartbeat"})) is None
    assert agent._parse_kraken(json.dumps([42, {}, "ticker", "XBT/USD"])) is None


def test_l2_jsonl_writer_appends_snapshot(tmp_path):
    queue: asyncio.Queue[L2Snapshot] = asyncio.Queue()
    writer = L2JsonlWriter(queue, tmp_path)
    snapshot = L2Snapshot(
        exchange="kraken",
        symbol="BTC",
        timestamp=datetime(2026, 5, 10, tzinfo=UTC),
        bids=(),
        asks=(),
        sequence=7,
    )

    path = writer.write(snapshot)

    assert path.exists()
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["exchange"] == "kraken"
    assert row["symbol"] == "BTC"
    assert row["sequence"] == 7
