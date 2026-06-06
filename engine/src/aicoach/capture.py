from __future__ import annotations

import io
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import mss
from PIL import Image

from aicoach.perf import CaptureBreakdown


@dataclass(frozen=True)
class Screenshot:
    """A captured desktop frame (JPEG or PNG bytes for vision API)."""

    png_bytes: bytes
    captured_at: datetime
    monitor_index: int
    width: int = 0
    height: int = 0
    mime_type: str = "image/png"

    @property
    def size_kb(self) -> float:
        return len(self.png_bytes) / 1024

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = self.captured_at.strftime("%Y%m%d_%H%M%S_%f")
        ext = "jpg" if self.mime_type == "image/jpeg" else "png"
        path = directory / f"screen_{stamp}.{ext}"
        path.write_bytes(self.png_bytes)
        return path

    def save_for_ocr(self, directory: Path, *, tag: str = "read") -> Path:
        """Persist the capture frame for OCR debugging (native size when captured full_quality)."""
        directory.mkdir(parents=True, exist_ok=True)
        stamp = self.captured_at.strftime("%Y%m%d_%H%M%S_%f")
        safe_tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)
        path = directory / f"ocr_{safe_tag}_{stamp}.png"
        if self.mime_type == "image/png":
            path.write_bytes(self.png_bytes)
            return path
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(self.png_bytes))
        img.save(path, format="PNG", optimize=True)
        return path


def list_monitors() -> list[dict[str, int | str]]:
    """
    Return mss monitor entries for CLI / logging.

    Index 0 = virtual full desktop (all monitors).
    Index 1 = usually the primary monitor; 2+ = additional displays.
    """
    with mss.mss() as sct:
        result: list[dict[str, int | str]] = []
        for i, mon in enumerate(sct.monitors):
            label = "all monitors (combined)" if i == 0 else (
                "primary display" if i == 1 else f"display {i}"
            )
            result.append(
                {
                    "index": i,
                    "label": label,
                    "left": mon["left"],
                    "top": mon["top"],
                    "width": mon["width"],
                    "height": mon["height"],
                }
            )
        return result


_PROBE_MAX_WIDTH = 720
_PROBE_JPEG_QUALITY = 70


class ScreenCapturer:
    """Captures one monitor (default: primary) as PNG bytes."""

    def __init__(
        self,
        monitor_index: int = 1,
        max_width: int = 1280,
        jpeg_quality: int = 82,
    ) -> None:
        self._monitor_index = monitor_index
        self._max_width = max_width
        self._jpeg_quality = jpeg_quality
        self._sct = mss.mss()

    @property
    def monitor_index(self) -> int:
        return self._monitor_index

    def monitor_label(self) -> str:
        for mon in list_monitors():
            if mon["index"] == self._monitor_index:
                return (
                    f"index {self._monitor_index} ({mon['label']}, "
                    f"{mon['width']}x{mon['height']})"
                )
        return f"index {self._monitor_index}"

    def close(self) -> None:
        self._sct.close()

    def capture(
        self,
        *,
        full_quality: bool = False,
        probe: bool = False,
        breakdown: CaptureBreakdown | None = None,
    ) -> Screenshot:
        """
        Capture the monitor frame.

        full_quality: native resolution PNG (for OCR).
        probe: smaller/faster frame for OCR drift checks before a full vision capture.
        breakdown: optional timing split (mss grab vs PIL encode) for perf diagnosis.
        """
        monitors = self._sct.monitors
        if self._monitor_index >= len(monitors):
            raise ValueError(
                f"Monitor index {self._monitor_index} not found. "
                f"Available: 0-{len(monitors) - 1}"
            )

        grab_started = time.monotonic()
        raw = self._sct.grab(monitors[self._monitor_index])
        grab_s = time.monotonic() - grab_started
        # Let the compositor/game recover one frame after BitBlt capture.
        if sys.platform == "win32" and not probe:
            time.sleep(0.016)

        encode_started = time.monotonic()
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if full_quality:
            max_width = 0
            jpeg_quality = 0
            resample = Image.Resampling.LANCZOS
        elif probe:
            max_width = _PROBE_MAX_WIDTH
            jpeg_quality = _PROBE_JPEG_QUALITY
            resample = Image.Resampling.BILINEAR
        else:
            max_width = self._max_width
            jpeg_quality = self._jpeg_quality
            resample = Image.Resampling.LANCZOS

        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, resample)

        buffer = io.BytesIO()
        if jpeg_quality > 0:
            img.save(
                buffer,
                format="JPEG",
                quality=jpeg_quality,
                optimize=not probe,
            )
            mime = "image/jpeg"
        else:
            img.save(buffer, format="PNG", optimize=True)
            mime = "image/png"

        encode_s = time.monotonic() - encode_started
        if breakdown is not None:
            breakdown.grab_s = grab_s
            breakdown.encode_s = encode_s

        return Screenshot(
            png_bytes=buffer.getvalue(),
            captured_at=datetime.now(timezone.utc),
            monitor_index=self._monitor_index,
            width=img.width,
            height=img.height,
            mime_type=mime,
        )
