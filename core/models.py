"""Shared generic data models.

Strategy-specific L2 structures live in `strategies.crypto.core.models`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class ArtifactMetadata:
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
