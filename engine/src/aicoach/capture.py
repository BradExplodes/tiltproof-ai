from __future__ import annotations

import io
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import mss
from PIL import Image

from aicoach.perf import CaptureBreakdown

logger = logging.getLogger(__name__)

_PROBE_MAX_WIDTH = 720
_PROBE_JPEG_QUALITY = 70


def _dxcam_importable() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import dxcam  # noqa: F401

        return True
    except ImportError:
        return False


def _select_backend() -> str:
    """Default mss (short GDI spike). Set AICOACH_CAPTURE_BACKEND=dxcam to opt in."""
    choice = os.getenv("AICOACH_CAPTURE_BACKEND", "mss").strip().lower()
    if choice == "dxcam" and _dxcam_importable():
        return "dxcam"
    return "mss"


def _mss_to_dxcam_output(monitor_index: int) -> int:
    """mss index 1 = primary; dxcam output_idx 0 = primary."""
    return max(0, monitor_index - 1)


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


def _encode_frame(
    img: Image.Image,
    *,
    full_quality: bool,
    probe: bool,
    default_max_width: int,
    default_jpeg_quality: int,
    breakdown: CaptureBreakdown | None,
    grab_s: float,
    encode_started: float | None = None,
) -> tuple[bytes, str, Image.Image]:
    if full_quality:
        max_width = 0
        jpeg_quality = 0
        resample = Image.Resampling.LANCZOS
    elif probe:
        max_width = _PROBE_MAX_WIDTH
        jpeg_quality = _PROBE_JPEG_QUALITY
        resample = Image.Resampling.BILINEAR
    else:
        max_width = default_max_width
        jpeg_quality = default_jpeg_quality
        resample = Image.Resampling.LANCZOS

    if max_width and img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, resample)

    started = encode_started if encode_started is not None else time.monotonic()
    buffer = io.BytesIO()
    if jpeg_quality > 0:
        img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=not probe)
        mime = "image/jpeg"
    else:
        img.save(buffer, format="PNG", optimize=True)
        mime = "image/png"

    if breakdown is not None:
        breakdown.encode_s = time.monotonic() - started
    return buffer.getvalue(), mime, img


class ScreenCapturer:
    """
    Captures one monitor as PNG/JPEG bytes.

    On Windows prefers DXGI Desktop Duplication (dxcam) over mss BitBlt so
    fullscreen games are not left in a degraded compositor state for the rest
    of the coaching cycle.
    """

    def __init__(
        self,
        monitor_index: int = 1,
        max_width: int = 1280,
        jpeg_quality: int = 82,
    ) -> None:
        self._monitor_index = monitor_index
        self._max_width = max_width
        self._jpeg_quality = jpeg_quality
        self._backend = _select_backend()
        if self._backend == "mss":
            logger.info(
                "Screen capture backend: mss (short-lived GDI grab per frame)"
            )
        else:
            logger.info(
                "Screen capture backend: dxcam (monitor index %s -> output %s)",
                monitor_index,
                _mss_to_dxcam_output(monitor_index),
            )

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def last_grab_backend(self) -> str:
        return getattr(self, "_last_grab_backend", self._backend)

    @property
    def monitor_index(self) -> int:
        return self._monitor_index

    def monitor_label(self) -> str:
        for mon in list_monitors():
            if mon["index"] == self._monitor_index:
                return (
                    f"index {self._monitor_index} ({mon['label']}, "
                    f"{mon['width']}x{mon['height']}, {self._backend})"
                )
        return f"index {self._monitor_index} ({self._backend})"

    def close(self) -> None:
        return

    def _grab_dxcam(self) -> Image.Image:
        import dxcam
        import numpy as np

        output_idx = _mss_to_dxcam_output(self._monitor_index)
        camera = dxcam.create(output_idx=output_idx, output_color="BGR")
        try:
            if getattr(camera, "is_capturing", False):
                camera.stop()
            frame = camera.grab()
            if frame is None:
                time.sleep(0.01)
                frame = camera.grab()
            if frame is None:
                raise RuntimeError("DXGI capture returned no frame")
            if not isinstance(frame, np.ndarray):
                raise RuntimeError(f"Unexpected DXGI frame type: {type(frame)!r}")
            rgb = frame[:, :, ::-1]
            return Image.fromarray(rgb.copy())
        finally:
            # Tear down capture mode; drop refs so DXGI duplication can unwind.
            # (camera.release() crashes on some comtypes builds — avoid it.)
            try:
                if getattr(camera, "is_capturing", False):
                    camera.stop()
            except Exception:
                logger.debug("dxcam stop failed", exc_info=True)
            del camera

    def _grab_mss(self) -> tuple[Image.Image, float]:
        grab_started = time.monotonic()
        with mss.mss() as sct:
            monitors = sct.monitors
            if self._monitor_index >= len(monitors):
                raise ValueError(
                    f"Monitor index {self._monitor_index} not found. "
                    f"Available: 0-{len(monitors) - 1}"
                )
            raw = sct.grab(monitors[self._monitor_index])
        grab_s = time.monotonic() - grab_started
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img, grab_s

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
        breakdown: optional timing split (grab vs encode) for perf diagnosis.
        """
        grab_started = time.monotonic()
        used_backend = self._backend
        if self._backend == "dxcam":
            try:
                img = self._grab_dxcam()
                grab_s = time.monotonic() - grab_started
            except Exception:
                logger.warning("DXGI capture failed; using mss for this frame", exc_info=True)
                img, _ = self._grab_mss()
                grab_s = time.monotonic() - grab_started
                used_backend = "mss"
        else:
            img, grab_s = self._grab_mss()
            if not probe:
                time.sleep(0.016)

        if breakdown is not None:
            breakdown.grab_s = grab_s
        self._last_grab_backend = used_backend

        encode_started = time.monotonic()
        png_bytes, mime, img = _encode_frame(
            img,
            full_quality=full_quality,
            probe=probe,
            default_max_width=self._max_width,
            default_jpeg_quality=self._jpeg_quality,
            breakdown=breakdown,
            grab_s=grab_s,
            encode_started=encode_started,
        )

        return Screenshot(
            png_bytes=png_bytes,
            captured_at=datetime.now(timezone.utc),
            monitor_index=self._monitor_index,
            width=img.width,
            height=img.height,
            mime_type=mime,
        )
