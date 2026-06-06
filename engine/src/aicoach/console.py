"""Safe console output on Windows (cp1252 consoles cannot print all Unicode)."""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    """Force UTF-8 stdout/stderr when the stream supports reconfigure (Python 3.7+)."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def safe_print(
    *args: object,
    sep: str = " ",
    end: str = "\n",
    file: object | None = None,
    flush: bool = False,
) -> None:
    """Print without crashing when the console encoding rejects Unicode."""
    out = file if file is not None else sys.stdout
    text = sep.join(str(a) for a in args) + end
    try:
        out.write(text)  # type: ignore[union-attr]
    except UnicodeEncodeError:
        enc = getattr(out, "encoding", None) or "utf-8"
        buffer = getattr(out, "buffer", None)
        if buffer is not None:
            buffer.write(text.encode(enc, errors="replace"))
        else:
            out.write(text.encode(enc, errors="replace").decode(enc, errors="replace"))  # type: ignore[union-attr]
    if flush:
        flush_fn = getattr(out, "flush", None)
        if callable(flush_fn):
            flush_fn()
