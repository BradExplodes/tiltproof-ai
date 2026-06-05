from __future__ import annotations

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


def app_dir() -> Path:
    """Directory for .env, screenshots, and other writable/local files."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _PKG_DIR.parent.parent


def prompts_dir() -> Path:
    if is_frozen():
        return bundle_dir() / "aicoach" / "prompts"
    return _PKG_DIR / "prompts"
