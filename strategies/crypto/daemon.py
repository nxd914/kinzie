"""Daemon entry point for Kraken L2 ingestion."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Awaitable
from pathlib import Path

from .agents import CryptoFeedAgent
from .core.config import Config
from .core.l2_store import L2JsonlWriter
from .core.logging import configure_logging
from .core.models import L2Snapshot

configure_logging()
logger = logging.getLogger(__name__)

_PID_PATH = Path("data/microstructure.pid")
_SHUTDOWN_TIMEOUT_SECONDS = 10.0


def _load_project_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    load_dotenv(override=False)


async def _guarded(coro: Awaitable[None], name: str) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Agent %s crashed: %s", name, exc, exc_info=True)
        raise


async def _drain_snapshots(snapshot_queue: asyncio.Queue[L2Snapshot]) -> None:
    count = 0
    while True:
        snapshot = await snapshot_queue.get()
        count += 1
        if count % 1000 == 0:
            logger.info(
                "Ingested %d L2 snapshots without persistence; latest=%s seq=%d",
                count,
                snapshot.symbol,
                snapshot.sequence,
            )
        snapshot_queue.task_done()


async def main() -> None:
    _load_project_dotenv()
    config = Config.from_env()
    config.validate()

    _PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    snapshot_queue: asyncio.Queue[L2Snapshot] = asyncio.Queue(maxsize=config.snapshot_queue_size)
    feed = CryptoFeedAgent(snapshot_queue=snapshot_queue, symbols=config.symbols, depth=config.book_depth)

    tasks = [
        asyncio.create_task(_guarded(feed.run(), "crypto_feed"), name="crypto_feed"),
    ]
    if config.persist_jsonl:
        writer = L2JsonlWriter(snapshot_queue=snapshot_queue, output_dir=config.jsonl_output_dir)
        tasks.append(asyncio.create_task(_guarded(writer.run(), "l2_jsonl_writer"), name="l2_jsonl_writer"))
    else:
        tasks.append(asyncio.create_task(_guarded(_drain_snapshots(snapshot_queue), "snapshot_drain"), name="snapshot_drain"))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [task.cancel() for task in tasks])

    logger.info(
        "Microstructure L2 ingestion running | symbols=%s | depth=%d | jsonl=%s",
        ",".join(config.symbols),
        config.book_depth,
        config.jsonl_output_dir if config.persist_jsonl else "disabled",
    )
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Shutdown signal received; stopping ingestion.")
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            still_running = [task.get_name() for task in tasks if not task.done()]
            logger.warning("Shutdown timed out; tasks still running: %s", still_running)
    finally:
        _PID_PATH.unlink(missing_ok=True)
        logger.info("[microstructure] L2 ingestion stopped")


if __name__ == "__main__":
    asyncio.run(main())
