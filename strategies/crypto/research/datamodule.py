"""PyTorch Lightning data scaffold for DeepLOB-style L2 research."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset, Subset

try:
    from lightning import LightningDataModule
except ImportError:  # pragma: no cover - keeps import errors focused when Lightning is absent.
    class LightningDataModule:  # type: ignore[no-redef]
        pass

from strategies.crypto.core.models import L2Snapshot
from strategies.crypto.research.targets import future_return


def load_snapshots(data_paths: Sequence[str | Path]) -> list[L2Snapshot]:
    snapshots: list[L2Snapshot] = []
    for path in data_paths:
        with Path(path).open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    snapshots.append(L2Snapshot.from_dict(json.loads(line)))
    snapshots.sort(key=lambda snapshot: (snapshot.symbol, snapshot.timestamp, snapshot.sequence))
    return snapshots


def snapshot_to_feature_vector(snapshot: L2Snapshot, depth: int = 10) -> list[float]:
    """Return raw `[bid_px, bid_vol, ask_px, ask_vol]` features for `depth` levels."""
    reference_price = snapshot.volume_weighted_mid
    if not math.isfinite(reference_price) or reference_price <= 0:
        reference_price = snapshot.mid
    if not math.isfinite(reference_price) or reference_price <= 0:
        raise ValueError("snapshot has no valid reference price")

    bids = list(snapshot.bids[:depth])
    asks = list(snapshot.asks[:depth])
    bid_prices = [(level.price / reference_price) - 1.0 for level in bids]
    ask_prices = [(level.price / reference_price) - 1.0 for level in asks]
    bid_volumes = [math.log1p(max(level.volume, 0.0)) for level in bids]
    ask_volumes = [math.log1p(max(level.volume, 0.0)) for level in asks]

    bid_prices.extend([0.0] * (depth - len(bid_prices)))
    ask_prices.extend([0.0] * (depth - len(ask_prices)))
    bid_volumes.extend([0.0] * (depth - len(bid_volumes)))
    ask_volumes.extend([0.0] * (depth - len(ask_volumes)))
    return bid_prices + bid_volumes + ask_prices + ask_volumes


class LOBSnapshotDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Rolling-window dataset over normalized L2 snapshot features."""

    def __init__(self, snapshots: Sequence[L2Snapshot], window_size: int = 100, horizon: int = 10) -> None:
        if window_size <= 1:
            raise ValueError("window_size must be greater than 1")
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        if len(snapshots) < window_size + horizon:
            raise ValueError("not enough snapshots for requested window and horizon")

        raw_features = torch.tensor(
            [snapshot_to_feature_vector(snapshot) for snapshot in snapshots],
            dtype=torch.float32,
        )
        means = raw_features.mean(dim=0)
        stds = raw_features.std(dim=0)
        stds = torch.where(stds > 1e-8, stds, torch.ones_like(stds))
        self.features = (raw_features - means) / stds
        self.features = torch.nan_to_num(self.features, nan=0.0, posinf=0.0, neginf=0.0)

        windows: list[torch.Tensor] = []
        targets: list[float] = []
        indices_by_symbol: dict[str, list[int]] = {}
        for index, snapshot in enumerate(snapshots):
            indices_by_symbol.setdefault(snapshot.symbol, []).append(index)

        for indices in indices_by_symbol.values():
            if len(indices) < window_size + horizon:
                continue
            weighted_mids = [snapshots[index].volume_weighted_mid for index in indices]
            last_start = len(indices) - window_size - horizon
            for start in range(last_start + 1):
                target_index = start + window_size - 1
                window_indices = indices[start : start + window_size]
                windows.append(self.features[window_indices])
                targets.append(future_return(weighted_mids, target_index, horizon))

        if not windows:
            raise ValueError("no per-symbol windows available for requested window and horizon")

        self.windows = torch.stack(windows)
        self.targets = torch.tensor(targets, dtype=torch.float32)
        self.targets = torch.nan_to_num(self.targets, nan=0.0, posinf=0.0, neginf=0.0)

    def __len__(self) -> int:
        return self.windows.shape[0]

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.windows[index], self.targets[index]


class LOBDataModule(LightningDataModule):
    """Lightning DataModule for JSONL L2 snapshots."""

    def __init__(
        self,
        data_paths: Sequence[str | Path],
        window_size: int = 100,
        horizon: int = 10,
        batch_size: int = 64,
        val_fraction: float = 0.2,
        test_fraction: float = 0.1,
    ) -> None:
        super().__init__()
        self.data_paths = list(data_paths)
        self.window_size = window_size
        self.horizon = horizon
        self.batch_size = batch_size
        self.val_fraction = val_fraction
        self.test_fraction = test_fraction
        self.train_dataset: Subset | None = None
        self.val_dataset: Subset | None = None
        self.test_dataset: Subset | None = None

    def setup(self, stage: str | None = None) -> None:
        dataset = LOBSnapshotDataset(load_snapshots(self.data_paths), self.window_size, self.horizon)
        n = len(dataset)
        n_test = int(n * self.test_fraction)
        n_val = int(n * self.val_fraction)
        n_train = n - n_val - n_test
        if n_train <= 0:
            raise ValueError("split fractions leave no training samples")

        indices = list(range(n))
        self.train_dataset = Subset(dataset, indices[:n_train])
        self.val_dataset = Subset(dataset, indices[n_train : n_train + n_val])
        self.test_dataset = Subset(dataset, indices[n_train + n_val :])

    def train_dataloader(self) -> DataLoader:
        return DataLoader(self._require(self.train_dataset), batch_size=self.batch_size, shuffle=True)

    def val_dataloader(self) -> DataLoader:
        return DataLoader(self._require(self.val_dataset), batch_size=self.batch_size, shuffle=False)

    def test_dataloader(self) -> DataLoader:
        return DataLoader(self._require(self.test_dataset), batch_size=self.batch_size, shuffle=False)

    def _require(self, dataset: Subset | None) -> Subset:
        if dataset is None:
            raise RuntimeError("call setup() before requesting dataloaders")
        return dataset
