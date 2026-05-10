"""JSONL persistence for normalized L2 snapshots."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .models import L2Snapshot


class L2JsonlWriter:
    """Append one JSON object per L2 snapshot."""

    def __init__(
        self,
        snapshot_queue: asyncio.Queue[L2Snapshot],
        output_dir: str | Path,
    ) -> None:
        self._snapshot_queue = snapshot_queue
        self._output_dir = Path(output_dir)

    async def run(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        while True:
            snapshot = await self._snapshot_queue.get()
            self.write(snapshot)
            self._snapshot_queue.task_done()

    def write(self, snapshot: L2Snapshot) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(snapshot)
        with path.open("a", encoding="utf-8") as fh:
            json.dump(snapshot.to_dict(), fh, separators=(",", ":"))
            fh.write("\n")
        return path

    def _path_for(self, snapshot: L2Snapshot) -> Path:
        date = snapshot.timestamp.strftime("%Y%m%d")
        symbol = snapshot.symbol.lower().replace("/", "-")
        return self._output_dir / f"{snapshot.exchange}_{symbol}_l2_{date}.jsonl"
