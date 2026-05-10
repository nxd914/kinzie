"""Target construction helpers for LOB research."""

from __future__ import annotations

from collections.abc import Sequence

from strategies.crypto.core.models import L2Snapshot


def future_return(weighted_mids: Sequence[float], index: int, horizon: int) -> float:
    """Compute `weighted_mid[t + k] / weighted_mid[t] - 1`."""
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    if index < 0 or index + horizon >= len(weighted_mids):
        raise IndexError("index + horizon is outside the weighted_mid series")
    current = float(weighted_mids[index])
    future = float(weighted_mids[index + horizon])
    if current == 0:
        raise ValueError("current weighted mid must be non-zero")
    return future / current - 1.0


def snapshot_weighted_mids(snapshots: Sequence[L2Snapshot]) -> list[float]:
    return [snapshot.volume_weighted_mid for snapshot in snapshots]
