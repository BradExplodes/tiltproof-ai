from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """PyInstaller extract dir (read-only bundled assets)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return _PKG_DIR.parent.parent


def _frozen_data_dir() -> Path:
    """Writable per-user data dir (install dir under Program Files is read-only)."""
    override = os.getenv("AICOACH_DATA_DIR", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Tiltproof AI" / "engine"


def app_dir() -> Path:
    """Directory for .env, screenshots, logs, and other writable/local files."""
    if is_frozen():
        return _frozen_data_dir()
    return _PKG_DIR.parent.parent


def prompts_dir() -> Path:
    if is_frozen():
        return bundle_dir() / "aicoach" / "prompts"
    return _PKG_DIR / "prompts"
