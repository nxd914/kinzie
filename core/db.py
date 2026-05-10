"""SQLite connection helper with WAL mode and sane defaults."""

from __future__ import annotations

import sqlite3
from pathlib import Path

PathLike = str | Path


def connect(path: PathLike, **kwargs) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journaling enabled."""
    conn = sqlite3.connect(str(path), **kwargs)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
