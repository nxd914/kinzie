"""Generic runtime environment helpers for the research daemon."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Environment:
    label: str
    data_dir: Path
    log_format: str = "text"


def resolve_environment() -> Environment:
    return Environment(
        label=os.environ.get("MICROSTRUCTURE_ENV", "research"),
        data_dir=Path(os.environ.get("MICROSTRUCTURE_DATA_DIR", "data")),
        log_format=os.environ.get("LOG_FORMAT", "text"),
    )


def log_environment_banner(env: Environment) -> None:
    logger.info(
        "[microstructure] Runtime environment: label=%s | data_dir=%s | log_format=%s",
        env.label,
        env.data_dir,
        env.log_format,
    )
