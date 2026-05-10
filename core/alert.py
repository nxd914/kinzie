"""
Alert stub — Telegram removed. Crashes and watchdog events are logged to
journalctl (ERROR level) and visible via `journalctl -u microstructure`.
"""

from __future__ import annotations


async def send_alert(text: str) -> None:  # noqa: ARG001
    pass
