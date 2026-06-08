"""
Long-term memory for the coach.

A small, durable JSON store of facts the coach has chosen to remember about the
player across sessions (play style, recurring mistakes, goals, preferences,
in-jokes). The coach writes to it via an optional `MEMORY:` line in its response;
the stored notes are fed back into the coach's system prompt on every turn so it
genuinely "remembers" between sessions. The desktop app can read and clear it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aicoach.paths import app_dir

logger = logging.getLogger(__name__)

# Keep the store small so it always fits in the prompt and stays cheap to read.
MAX_ENTRIES = 60
MAX_ENTRY_CHARS = 300
_PROMPT_LIMIT = 40


@dataclass(frozen=True)
class MemoryEntry:
    text: str
    ts: str
    game_id: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return " ".join(text.strip().split())


class LongTermMemory:
    """Thread-safe JSON-backed list of remembered notes (newest last)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def _read_raw(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            logger.warning("Long-term memory file unreadable; starting empty", exc_info=True)
            return []
        entries = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return []
        out: list[dict[str, Any]] = []
        for item in entries:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(
                    {
                        "text": item["text"],
                        "ts": item.get("ts") or _now_iso(),
                        "game_id": item.get("game_id"),
                    }
                )
        return out

    def _write_raw(self, entries: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"updated_at": _now_iso(), "entries": entries}
        # Atomic replace so a crash mid-write never corrupts the store.
        fd, tmp_name = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self._path)
        except Exception:
            with suppress_os_error():
                os.unlink(tmp_name)
            raise

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_raw()

    def add(self, text: str, *, game_id: str | None = None) -> bool:
        """Append a note. Returns True if stored, False if empty/duplicate."""
        note = _normalize(text)
        if not note or note.upper() in ("NONE", "N/A", "NA", "-"):
            return False
        note = note[:MAX_ENTRY_CHARS]
        with self._lock:
            entries = self._read_raw()
            # Skip near-duplicates of any recent note (case-insensitive).
            recent = {e["text"].strip().lower() for e in entries[-12:]}
            if note.lower() in recent:
                return False
            entries.append({"text": note, "ts": _now_iso(), "game_id": game_id})
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            self._write_raw(entries)
        logger.info("Long-term memory updated (%s entries)", len(entries))
        return True

    def clear(self) -> None:
        with self._lock:
            self._write_raw([])

    def format_for_prompt(self, *, limit: int = _PROMPT_LIMIT) -> str:
        """Bulleted notes block for the coach system prompt, or '' if empty."""
        with self._lock:
            entries = self._read_raw()
        if not entries:
            return ""
        recent = entries[-limit:]
        lines = "\n".join(f"- {e['text']}" for e in recent)
        return (
            "LONG-TERM MEMORY (things you've chosen to remember about this player "
            "across sessions — use these to personalize coaching and callbacks):\n"
            f"{lines}"
        )


class suppress_os_error:
    """Tiny context manager: ignore OSError during best-effort cleanup."""

    def __enter__(self) -> "suppress_os_error":
        return self

    def __exit__(self, exc_type: object, *_: object) -> bool:
        return exc_type is not None and issubclass(exc_type, OSError)  # type: ignore[arg-type]


_default: LongTermMemory | None = None
_default_lock = threading.Lock()


def default_memory() -> LongTermMemory:
    """Process-wide singleton backed by the app data dir."""
    global _default
    if _default is None:
        with _default_lock:
            if _default is None:
                _default = LongTermMemory(app_dir() / "memory.json")
    return _default


def serialize_entry(entry: MemoryEntry) -> dict[str, Any]:
    return asdict(entry)
