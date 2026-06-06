"""
Performance profiling for lag diagnosis.

Set PERF_LOG=1 to write structured timing lines to the engine log file and emit
`perf` WebSocket events the desktop UI can display.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aicoach.paths import app_dir

logger = logging.getLogger(__name__)

_PERF_ENABLED = os.getenv("PERF_LOG", "1").strip().lower() in ("1", "true", "yes", "on")
_LOG_PATH: Path | None = None


def perf_enabled() -> bool:
    return _PERF_ENABLED


def log_file_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        log_dir = app_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        _LOG_PATH = log_dir / "engine.log"
    return _LOG_PATH


def configure_file_logging() -> None:
    """Attach a rotating-friendly file handler once (desktop sidecar diagnostics)."""
    try:
        path = log_file_path()
    except OSError as exc:
        logger.warning("Engine file logging disabled: %s", exc)
        return
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "baseFilename", None) == str(path):
            return
    try:
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError as exc:
        logger.warning("Engine file logging disabled: %s", exc)
        return
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    logger.info("Engine log file: %s", path)


def apply_low_priority() -> None:
    """Let the game win CPU scheduling contests on Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
        logger.info("Engine process priority set to Below Normal")
    except Exception:
        logger.debug("Could not lower process priority", exc_info=True)


@dataclass
class CaptureBreakdown:
    grab_s: float = 0.0
    encode_s: float = 0.0

    @property
    def total_s(self) -> float:
        return self.grab_s + self.encode_s


@dataclass
class PerfSpan:
    phase: str
    state: str
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def finish(self, **extra: Any) -> float:
        self.ended = time.monotonic()
        self.extra.update(extra)
        return self.duration_ms

    @property
    def duration_ms(self) -> float:
        end = self.ended if self.ended is not None else time.monotonic()
        return (end - self.started) * 1000.0


def perf_event(
    phase: str,
    *,
    state: str,
    duration_ms: float,
    **extra: Any,
) -> dict[str, Any]:
    from aicoach import events as ev

    payload = {
        "phase": phase,
        "state": state,
        "duration_ms": round(duration_ms, 1),
        **extra,
    }
    line = " ".join(
        f"{k}={v}" for k, v in payload.items() if v is not None and v != ""
    )
    if _PERF_ENABLED:
        logger.info("PERF %s", line)
    return ev._envelope("perf", **payload)  # noqa: SLF001 — shared envelope helper
