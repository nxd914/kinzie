import json
from datetime import UTC, datetime, timedelta

import pytest

torch = pytest.importorskip("torch")

from strategies.crypto.core.models import BookLevel, L2Snapshot
from strategies.crypto.research.datamodule import LOBDataModule
from strategies.crypto.research.targets import future_return


def _snapshot(index: int) -> L2Snapshot:
    mid = 100.0 + index
    bids = tuple(BookLevel(price=mid - 0.1 - level * 0.1, volume=1.0 + level) for level in range(10))
    asks = tuple(BookLevel(price=mid + 0.1 + level * 0.1, volume=1.5 + level) for level in range(10))
    return L2Snapshot(
        exchange="kraken",
        symbol="BTC",
        timestamp=datetime(2026, 5, 10, tzinfo=UTC) + timedelta(seconds=index),
        bids=bids,
        asks=asks,
        sequence=index,
    )


def _write_jsonl(path, count: int = 40) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for index in range(count):
            fh.write(json.dumps(_snapshot(index).to_dict()) + "\n")


def test_future_return_uses_horizon_index():
    weighted_mids = [100.0, 101.0, 102.0, 105.0]

    assert future_return(weighted_mids, 1, 2) == pytest.approx(105.0 / 101.0 - 1.0)


def test_lob_datamodule_batch_shapes_and_finite_values(tmp_path):
    path = tmp_path / "snapshots.jsonl"
    _write_jsonl(path, count=50)
    dm = LOBDataModule(
        [path],
        window_size=12,
        horizon=3,
        batch_size=8,
        val_fraction=0.2,
        test_fraction=0.1,
    )

    dm.setup()
    x, y = next(iter(dm.train_dataloader()))

    assert x.shape == (8, 12, 40)
    assert y.shape == (8,)
    assert torch.isfinite(x).all()
    assert torch.isfinite(y).all()
