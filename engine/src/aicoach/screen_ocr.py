from __future__ import annotations

import io
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from aicoach.ocr_preprocess import preprocess_for_ocr
from aicoach.screen_observation import ScreenObservation

if TYPE_CHECKING:
    from aicoach.capture import Screenshot

logger = logging.getLogger(__name__)

OcrEngine = Literal["tesseract", "windows", "auto"]
OCR_ENGINES: tuple[str, ...] = ("tesseract", "windows", "auto")

_MIN_OCR_CHARS = 12

# Short codes (OCR_LANGUAGE=en) → Tesseract traineddata codes.
_TESSERACT_LANG: dict[str, str] = {
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "ja": "jpn",
    "jpn": "jpn",
    "japanese": "jpn",
    "de": "deu",
    "fr": "fra",
}


def _tesseract_language(lang: str) -> str:
    key = lang.strip().lower()
    return _TESSERACT_LANG.get(key, key)


def _resolve_tesseract_cmd(explicit: str | None) -> str | None:
    if explicit and Path(explicit).is_file():
        return explicit
    env = os.getenv("TESSERACT_CMD") or os.getenv("OCR_TESSERACT_CMD", "").strip()
    if env and Path(env).is_file():
        return env
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if Path(candidate).is_file():
                return candidate
    return None


def tesseract_available(tesseract_cmd: str | None = None) -> bool:
    try:
        import pytesseract

        cmd = _resolve_tesseract_cmd(tesseract_cmd)
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def windows_ocr_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winocr  # noqa: F401

        return True
    except ImportError:
        return False


def ocr_available(
    engine: OcrEngine = "tesseract",
    *,
    tesseract_cmd: str | None = None,
) -> bool:
    if engine == "tesseract":
        return tesseract_available(tesseract_cmd)
    if engine == "windows":
        return windows_ocr_available()
    return tesseract_available(tesseract_cmd) or windows_ocr_available()


def _screenshot_to_image(screenshot: Screenshot):
    from PIL import Image

    img = Image.open(io.BytesIO(screenshot.png_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def _downscale_for_ocr(img, max_width: int):
    """Keep OCR responsive on 1440p/4K captures."""
    if max_width <= 0 or img.width <= max_width:
        return img
    from PIL import Image

    ratio = max_width / img.width
    new_size = (max_width, max(img.height * ratio, 1))
    return img.resize(
        (max_width, int(new_size[1])),
        Image.Resampling.LANCZOS,
    )


def _ocr_quality_score(text: str) -> float:
    """Higher = more plausible HUD/UI text."""
    if not text:
        return 0.0
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) >= 2]
    alnum = sum(ch.isalnum() for ch in text)
    words = sum(1 for ln in lines if re.search(r"[A-Za-z0-9]", ln))
    return alnum + words * 8 + len(lines) * 3


def _tesseract_psm_configs(multi_psm: bool, base_config: str) -> list[str]:
    base = base_config.strip()
    if not multi_psm:
        return [base or "--oem 3 --psm 6"]
    # 6 = block, 7 = line, 11 = sparse, 3 = auto (Tesseract / game UI guidance).
    extra = (
        "--oem 3 --psm 6",
        "--oem 3 --psm 7",
        "--oem 3 --psm 11",
        "--oem 3 --psm 3",
    )
    if base and base not in extra:
        return [base, *extra]
    return list(extra)


_TESSERACT_TIMEOUT_S = 25


def _run_tesseract_on_image(pytesseract, img, tess_lang: str, config: str) -> str:
    try:
        data = pytesseract.image_to_data(
            img,
            lang=tess_lang,
            config=config,
            output_type=pytesseract.Output.DICT,
            timeout=_TESSERACT_TIMEOUT_S,
        )
        parts: list[str] = []
        for word, conf in zip(data.get("text", []), data.get("conf", [])):
            if not word or not str(word).strip():
                continue
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = -1.0
            if c < 0 or c >= 50:
                parts.append(str(word).strip())
        if parts:
            return " ".join(parts)
    except Exception:
        logger.debug("image_to_data failed; using image_to_string", exc_info=True)
    return (
        pytesseract.image_to_string(
            img,
            lang=tess_lang,
            config=config,
            timeout=_TESSERACT_TIMEOUT_S,
        )
        or ""
    ).strip()


def _recognize_tesseract(
    screenshot: Screenshot,
    lang: str,
    *,
    tesseract_cmd: str | None,
    tesseract_config: str,
    scale_factor: float = 2.0,
    preprocess_mode: str = "balanced",
    multi_psm: bool = True,
    max_width: int = 1600,
    save_capture_dir: Path | None = None,
    save_capture_tag: str = "read",
    save_debug_path: Path | None = None,
) -> tuple[str, float]:
    import pytesseract

    cmd = _resolve_tesseract_cmd(tesseract_cmd)
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    if save_capture_dir is not None:
        try:
            saved = screenshot.save_for_ocr(save_capture_dir, tag=save_capture_tag)
            logger.info("OCR input frame saved: %s", saved)
            print(f"(OCR screenshot saved — {saved.name})", flush=True)
        except Exception:
            logger.debug("Could not save OCR capture", exc_info=True)

    started = time.monotonic()
    source = _downscale_for_ocr(_screenshot_to_image(screenshot), max_width)
    tess_lang = _tesseract_language(lang)
    configs = _tesseract_psm_configs(multi_psm, tesseract_config)

    best_text = ""
    best_score = -1.0
    best_label = ""

    debug_saved = False
    for prep_img, prep_label in preprocess_for_ocr(
        source, scale=scale_factor, mode=preprocess_mode
    ):
        if save_debug_path and not debug_saved:
            try:
                prep_img.save(save_debug_path)
                debug_saved = True
            except Exception:
                logger.debug("Could not save OCR debug image", exc_info=True)

        for cfg in configs:
            text = _run_tesseract_on_image(pytesseract, prep_img, tess_lang, cfg)
            score = _ocr_quality_score(text)
            if score > best_score:
                best_score = score
                best_text = text
                best_label = f"{prep_label}/{cfg}"

    elapsed = time.monotonic() - started
    logger.info(
        "Tesseract best pass: %s (score=%.0f, %d chars)",
        best_label or "none",
        best_score,
        len(best_text),
    )
    return best_text.strip(), elapsed


def _recognize_windows(screenshot: Screenshot, lang: str) -> tuple[str, float]:
    from winocr import recognize_pil_sync

    started = time.monotonic()
    img = _screenshot_to_image(screenshot)
    win_lang = lang if len(lang) <= 3 else _tesseract_language(lang)[:2]
    try:
        result = recognize_pil_sync(img, win_lang)
    except TypeError:
        result = recognize_pil_sync(img)
    elapsed = time.monotonic() - started
    if isinstance(result, dict):
        text = (result.get("text") or "").strip()
    else:
        text = (getattr(result, "text", None) or "").strip()
    return text, elapsed


def recognize_screenshot(
    screenshot: Screenshot,
    lang: str = "en",
    *,
    engine: OcrEngine = "tesseract",
    tesseract_cmd: str | None = None,
    tesseract_config: str = "--oem 3 --psm 11",
    scale_factor: float = 2.0,
    preprocess_mode: str = "balanced",
    multi_psm: bool = True,
    max_width: int = 1600,
    save_capture_dir: Path | None = None,
    save_capture_tag: str = "read",
    save_debug_path: Path | None = None,
) -> tuple[str, float, str]:
    """
    Run OCR on a captured frame.
    Returns (full text, elapsed seconds, engine label: tesseract | windows).
    """
    if engine == "auto":
        if tesseract_available(tesseract_cmd):
            engine = "tesseract"
        elif windows_ocr_available():
            engine = "windows"
        else:
            raise RuntimeError(
                "No OCR engine available. Install Tesseract "
                "(https://github.com/tesseract-ocr/tesseract) and pip install pytesseract, "
                "or on Windows: pip install winocr."
            )

    if engine == "tesseract":
        if not tesseract_available(tesseract_cmd):
            raise RuntimeError(
                "Tesseract is not available. Install the Tesseract binary "
                "(winget install UB-Mannheim.TesseractOCR) and: pip install pytesseract. "
                "Set TESSERACT_CMD if it is not on PATH."
            )
        text, elapsed = _recognize_tesseract(
            screenshot,
            lang,
            tesseract_cmd=tesseract_cmd,
            tesseract_config=tesseract_config,
            scale_factor=scale_factor,
            preprocess_mode=preprocess_mode,
            multi_psm=multi_psm,
            max_width=max_width,
            save_capture_dir=save_capture_dir,
            save_capture_tag=save_capture_tag,
            save_debug_path=save_debug_path,
        )
        return text, elapsed, "tesseract"

    if not windows_ocr_available():
        raise RuntimeError(
            "Windows OCR is not available. pip install winocr "
            "(Windows 10+ with Language.OCR pack)."
        )
    text, elapsed = _recognize_windows(screenshot, lang)
    return text, elapsed, "windows"


def infer_screen_type(ocr_text: str, game_id: str) -> str:
    """Heuristic scene from OCR lines (osu-first)."""
    from aicoach.scene_classify import infer_screen_type_from_text

    if len(ocr_text.strip()) < _MIN_OCR_CHARS:
        return "unknown"
    return infer_screen_type_from_text(ocr_text, game_id)


def extract_search_query_from_ocr(ocr_text: str) -> str | None:
    """Best-effort Artist - Title from OCR lines."""
    for line in ocr_text.splitlines():
        line = line.strip()
        if not line or len(line) < 5:
            continue
        if " - " in line and len(line) <= 120:
            low = line.lower()
            if any(
                skip in low
                for skip in ("http", "www.", "version", "copyright", "osu!")
            ):
                continue
            return line
    return None


def observation_from_ocr(
    ocr_text: str,
    game_id: str,
    *,
    engine_label: str = "ocr",
) -> ScreenObservation:
    screen_type = infer_screen_type(ocr_text, game_id)
    search_query = extract_search_query_from_ocr(ocr_text)
    if search_query and screen_type == "unknown":
        screen_type = "map_select"
    if screen_type != "map_select":
        search_query = None

    lines = [ln.strip() for ln in ocr_text.splitlines() if ln.strip()]
    body = "\n".join(lines) if lines else "(no text recognized)"
    results_note = ""
    if game_id == "osu" and screen_type == "results":
        from aicoach.osu_results import format_osu_results_summary, parse_osu_results_stats

        summary = format_osu_results_summary(parse_osu_results_stats(ocr_text))
        if summary:
            results_note = f"\n{summary}"

    description = (
        f"{engine_label} read {len(lines)} line(s) on screen. "
        f"Inferred screen: {screen_type}."
        f"{results_note}\n"
        f"Visible text:\n{body}"
    )

    raw = (
        f"SCREEN_TYPE: {screen_type}\n"
        f"SEARCH_QUERY: {search_query or 'NONE'}\n"
        f"DESCRIPTION:\n{description}"
    )
    return ScreenObservation(
        screen_type=screen_type,
        description=description,
        raw=raw,
        search_query=search_query,
    )


def ocr_is_usable(observation: ScreenObservation) -> bool:
    text = observation.description
    if "no text recognized" in text.lower():
        return False
    visible = text.split("Visible text:", 1)
    payload = visible[1].strip() if len(visible) > 1 else text
    return len(payload) >= _MIN_OCR_CHARS
