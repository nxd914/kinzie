import asyncio
import json
from datetime import datetime, timezone
import pytest

from strategies.crypto.agents.crypto_feed_agent import CryptoFeedAgent


@pytest.fixture
def agent():
    return CryptoFeedAgent(asyncio.Queue())


def _kraken_ticker(pair: str, price: str) -> str:
    """Create a mock Kraken ticker message."""
    return json.dumps([
        119930888,
        {
            "a": ["79300.10000", 2, "2.79261056"],
            "b": ["79300.00000", 0, "0.32492162"],
            "c": [price, "0.00150667"],
            "v": ["0.00000000", "1609.53129086"],
            "p": ["0.00000", "80315.07912"],
            "t": [0, 55257],
            "l": ["0.00000", "79300.00000"],
            "h": ["0.00000", "81705.00000"],
            "o": ["0.00000", "81068.60000"]
        },
        "ticker",
        pair
    ])


def test_kraken_parse_btc(agent):
    tick = agent._parse_kraken(_kraken_ticker("XBT/USD", "67000.50"))
    assert tick is not None
    assert tick.exchange == "kraken"
    assert tick.symbol == "BTC"
    assert tick.price == 67000.50


def test_kraken_parse_eth(agent):
    tick = agent._parse_kraken(_kraken_ticker("ETH/USD", "3500.25"))
    assert tick is not None
    assert tick.exchange == "kraken"
    assert tick.symbol == "ETH"
    assert tick.price == 3500.25


def test_kraken_parse_unknown_symbol(agent):
    tick = agent._parse_kraken(_kraken_ticker("DOGE/USD", "0.15"))
    assert tick is None


def test_kraken_parse_non_ticker_ignored(agent):
    tick = agent._parse_kraken(json.dumps([123, {"a": "b"}, "trade", "XBT/USD"]))
    assert tick is None


def test_kraken_parse_malformed(agent):
    assert agent._parse_kraken("not json") is None
    assert agent._parse_kraken('{"not": "a list"}') is None
    assert agent._parse_kraken('[123]') is None
