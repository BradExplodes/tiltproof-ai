from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _opencv_available() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def preprocess_for_ocr(img, *, scale: float = 2.0, mode: str = "game") -> list[tuple[object, str]]:
    """
    Return one or more PIL images to feed Tesseract (label, image).

    Modes:
    - game / game_fast: light UI on dark backgrounds (osu HUD) — invert + CLAHE
    - balanced / max: legacy OpenCV multi-pass
    - fast: quick PIL-only (fallback without OpenCV)
    """
    mode = (mode or "game").strip().lower()
    if mode == "none":
        return [(img.convert("L") if img.mode != "L" else img, "raw")]

    if mode in ("game", "game_fast") and _opencv_available():
        variants = _opencv_game_variants(img, scale=scale, fast=mode == "game_fast")
        return variants

    if mode == "fast":
        return _pil_variants(img, scale=scale)[:2]

    if _opencv_available() and mode in ("balanced", "max", "opencv"):
        return _opencv_variants(img, scale=scale, thorough=mode == "max")

    return _pil_variants(img, scale=scale)


def _opencv_game_variants(img, *, scale: float, fast: bool) -> list[tuple[object, str]]:
    """
    Game UI OCR prep (Tesseract expects dark-on-light; osu is mostly light-on-dark).

    See: tessdoc ImproveQuality, Stack Overflow #65635189 (adaptiveThreshold + BINARY_INV).
    """
    import cv2
    import numpy as np
    from PIL import Image

    rgb = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale > 1.0:
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    if not fast:
        gray = cv2.fastNlMeansDenoising(gray, None, h=5, templateWindowSize=7, searchWindowSize=15)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    variants: list[tuple[object, str]] = []

    def _add(label: str, arr) -> None:
        variants.append((Image.fromarray(arr), label))

    # Light text on dark UI — inverted thresholds often win (game HUD).
    adapt_gauss_inv = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        8,
    )
    _add("game-adapt-inv", adapt_gauss_inv)

    adapt_mean_inv = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        21,
        12,
    )
    _add("game-mean-inv", adapt_mean_inv)

    _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _add("game-otsu-inv", otsu_inv)

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _add("game-otsu", otsu)

    if not fast:
        adapt = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9
        )
        _add("game-adapt", adapt)
        _add("game-gray", gray)

    return variants


def _pil_variants(img, *, scale: float) -> list[tuple[object, str]]:
    from PIL import Image, ImageEnhance, ImageOps

    rgb = img.convert("RGB")
    if scale > 1.0:
        w, h = rgb.size
        rgb = rgb.resize(
            (int(w * scale), int(h * scale)),
            Image.Resampling.LANCZOS,
        )
    gray = ImageOps.autocontrast(rgb.convert("L"))
    sharp = ImageEnhance.Sharpness(gray).enhance(1.5)
    high = ImageEnhance.Contrast(sharp).enhance(1.5)
    bw = high.point(lambda p: 255 if p > 155 else 0)
    inv = high.point(lambda p: 0 if p > 100 else 255)
    return [(high, "pil-gray"), (bw, "pil-thresh"), (inv, "pil-invert")]


def _opencv_variants(img, *, scale: float, thorough: bool) -> list[tuple[object, str]]:
    import cv2
    import numpy as np
    from PIL import Image

    rgb = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale > 1.0:
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)

    variants: list[tuple[object, str]] = []

    def _add(label: str, arr) -> None:
        variants.append((Image.fromarray(arr), label))

    block = 31 if not thorough else 25
    c = 9 if not thorough else 7
    adapt = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c
    )
    _add("adapt", adapt)
    _add("adapt-inv", cv2.bitwise_not(adapt))

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _add("otsu", otsu)
    _add("otsu-inv", cv2.bitwise_not(otsu))

    if thorough:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        closed = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel)
        _add("adapt-closed", closed)

    _add("gray", gray)

    return variants
