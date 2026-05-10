"""Configuration for Kraken L2 ingestion and research scaffolding."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _symbols(raw: str) -> tuple[str, ...]:
    return tuple(symbol.strip().upper() for symbol in raw.split(",") if symbol.strip())


@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...] = ("BTC", "ETH")
    book_depth: int = 10
    snapshot_queue_size: int = 5000
    persist_jsonl: bool = True
    jsonl_output_dir: Path = Path("data/l2")
    reconnect_initial_delay_seconds: float = 1.0
    reconnect_max_delay_seconds: float = 60.0

    window_size: int = 100
    target_horizon: int = 10
    batch_size: int = 64
    val_fraction: float = 0.2
    test_fraction: float = 0.1

    @classmethod
    def from_env(cls) -> Config:
        base = cls()

        def _int(key: str, default: int) -> int:
            value = os.environ.get(key)
            return int(value) if value is not None else default

        def _float(key: str, default: float) -> float:
            value = os.environ.get(key)
            return float(value) if value is not None else default

        def _bool(key: str, default: bool) -> bool:
            value = os.environ.get(key)
            return default if value is None else value.lower() in {"1", "true", "yes", "on"}

        return cls(
            symbols=_symbols(os.environ.get("KRAKEN_SYMBOLS", ",".join(base.symbols))),
            book_depth=_int("KRAKEN_BOOK_DEPTH", base.book_depth),
            snapshot_queue_size=_int("SNAPSHOT_QUEUE_SIZE", base.snapshot_queue_size),
            persist_jsonl=_bool("L2_PERSIST_JSONL", base.persist_jsonl),
            jsonl_output_dir=Path(os.environ.get("L2_JSONL_OUTPUT_DIR", str(base.jsonl_output_dir))),
            reconnect_initial_delay_seconds=_float(
                "RECONNECT_INITIAL_DELAY_SECONDS",
                base.reconnect_initial_delay_seconds,
            ),
            reconnect_max_delay_seconds=_float(
                "RECONNECT_MAX_DELAY_SECONDS",
                base.reconnect_max_delay_seconds,
            ),
            window_size=_int("LOB_WINDOW_SIZE", base.window_size),
            target_horizon=_int("LOB_TARGET_HORIZON", base.target_horizon),
            batch_size=_int("LOB_BATCH_SIZE", base.batch_size),
            val_fraction=_float("LOB_VAL_FRACTION", base.val_fraction),
            test_fraction=_float("LOB_TEST_FRACTION", base.test_fraction),
        )

    def validate(self) -> None:
        if not self.symbols:
            raise ValueError("At least one Kraken symbol is required")
        if self.book_depth <= 0:
            raise ValueError("KRAKEN_BOOK_DEPTH must be positive")
        if self.snapshot_queue_size <= 0:
            raise ValueError("SNAPSHOT_QUEUE_SIZE must be positive")
        if self.window_size <= 1:
            raise ValueError("LOB_WINDOW_SIZE must be greater than 1")
        if self.target_horizon <= 0:
            raise ValueError("LOB_TARGET_HORIZON must be positive")
        if self.batch_size <= 0:
            raise ValueError("LOB_BATCH_SIZE must be positive")
        if not 0 <= self.val_fraction < 1:
            raise ValueError("LOB_VAL_FRACTION must be in [0, 1)")
        if not 0 <= self.test_fraction < 1:
            raise ValueError("LOB_TEST_FRACTION must be in [0, 1)")
        if self.val_fraction + self.test_fraction >= 1:
            raise ValueError("Validation and test fractions must leave training data")


DEFAULT_CONFIG = Config()
