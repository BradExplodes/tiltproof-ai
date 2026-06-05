from __future__ import annotations

import logging
from pathlib import Path

from aicoach.capture import Screenshot
from aicoach.pricing import UsageCost
from aicoach.screen_observation import ScreenObservation
from aicoach.ocr_change import ocr_substantially_changed
from aicoach.ocr_sufficiency import ocr_sufficient_for_transcript
from aicoach.screen_ocr import (
    OcrEngine,
    observation_from_ocr,
    ocr_available,
    ocr_is_usable,
    recognize_screenshot,
)
from aicoach.scene_classify import reconcile_screen_observation
from aicoach.vision_describe import ScreenDescriber
from aicoach.voice.screen_intent import (
    needs_visual_reasoning,
    prefer_screen_ocr,
    voice_needs_screen_context,
)

logger = logging.getLogger(__name__)


def _print_ocr_preview(observation: ScreenObservation, *, note: str = "") -> None:
    """Show Tesseract output in the console even when vision is used for the reply."""
    print("--- OCR output (not used for reply) ---", flush=True)
    if note:
        print(f"({note})", flush=True)
    print(observation.description, flush=True)
    print("---", flush=True)


class ScreenReader:
    """
    Stage 1 screen context.

    - Idle / 20s-interval refreshes: always OpenAI vision.
    - Voice turns: try Tesseract OCR first; if OCR is not enough for the
      user's question, fall back to OpenAI vision on the same screenshot.
    """

    def __init__(
        self,
        describer: ScreenDescriber,
        *,
        ocr_enabled: bool = True,
        ocr_lang: str = "en",
        ocr_engine: OcrEngine = "tesseract",
        tesseract_cmd: str | None = None,
        tesseract_config: str = "--oem 3 --psm 11",
        ocr_scale_factor: float = 2.0,
        ocr_preprocess_mode: str = "balanced",
        ocr_multi_psm: bool = True,
        ocr_max_width: int = 1600,
        ocr_voice_fast: bool = True,
        ocr_save_dir: Path | None = None,
        ocr_debug_dir: Path | None = None,
    ) -> None:
        self._describer = describer
        self._ocr_lang = ocr_lang.strip() or "en"
        self._ocr_engine: OcrEngine = ocr_engine
        self._tesseract_cmd = tesseract_cmd
        self._tesseract_config = tesseract_config
        self._ocr_scale_factor = max(1.0, ocr_scale_factor)
        self._ocr_preprocess_mode = ocr_preprocess_mode
        self._ocr_multi_psm = ocr_multi_psm
        self._ocr_max_width = max(640, int(ocr_max_width))
        self._ocr_voice_fast = ocr_voice_fast
        self._ocr_save_dir = ocr_save_dir
        self._ocr_debug_dir = ocr_debug_dir
        self._ocr_enabled = ocr_enabled and ocr_available(
            ocr_engine, tesseract_cmd=tesseract_cmd
        )
        if ocr_enabled and not self._ocr_enabled:
            logger.warning(
                "OCR_ENABLED but no OCR engine available (engine=%s). "
                "Install Tesseract + pytesseract, or winocr on Windows. "
                "Voice text reads will fall back to vision.",
                ocr_engine,
            )
        elif self._ocr_enabled:
            logger.info(
                "Screen read: OCR enabled (engine=%s, lang=%s, scale=%.1fx, preprocess=%s)",
                ocr_engine,
                self._ocr_lang,
                self._ocr_scale_factor,
                self._ocr_preprocess_mode,
            )
        self._baseline_ocr_text = ""
        self._pending_probe_ocr_text = ""

    @property
    def ocr_active(self) -> bool:
        return self._ocr_enabled

    def _quick_ocr_params(self) -> tuple[float, str, bool, int]:
        """Lightweight params for idle drift probes (minimize CPU during gameplay)."""
        return 1.25, "game_fast", False, 960

    def _voice_ocr_params(self) -> tuple[float, str, bool, int]:
        scale = min(self._ocr_scale_factor, 1.5) if self._ocr_voice_fast else self._ocr_scale_factor
        if self._ocr_voice_fast:
            preprocess = "game_fast"
        else:
            preprocess = self._ocr_preprocess_mode
        multi = False if self._ocr_voice_fast else self._ocr_multi_psm
        return scale, preprocess, multi, self._ocr_max_width

    def run_quick_ocr(self, screenshot: Screenshot) -> tuple[str, float]:
        """Fast OCR pass for drift detection (not a full screen read)."""
        scale, preprocess, multi, max_width = self._quick_ocr_params()
        return recognize_screenshot(
            screenshot,
            self._ocr_lang,
            engine=self._ocr_engine,
            tesseract_cmd=self._tesseract_cmd,
            tesseract_config=self._tesseract_config,
            scale_factor=scale,
            preprocess_mode=preprocess,
            multi_psm=multi,
            max_width=max_width,
            save_capture_dir=self._ocr_save_dir,
            save_capture_tag="probe",
        )[:2]

    def probe_screen_change(
        self,
        screenshot: Screenshot,
        *,
        game_id: str = "osu",
        scene_hint: str = "",
    ) -> tuple[bool, str]:
        """
        Compare current screen OCR to the last committed baseline.
        Does not update the baseline — call commit_ocr_baseline after a full read.
        """
        if not self._ocr_enabled:
            self._pending_probe_ocr_text = ""
            return True, "OCR disabled — interval refresh (no local OCR)"
        try:
            ocr_text, elapsed = self.run_quick_ocr(screenshot)
            self._pending_probe_ocr_text = ocr_text
            changed, reason = ocr_substantially_changed(
                self._baseline_ocr_text,
                ocr_text,
                game_id=game_id,
                scene_hint=scene_hint,
            )
            logger.info(
                "OCR drift check: %s (%.2fs, %d chars)",
                reason,
                elapsed,
                len(ocr_text),
            )
            return changed, reason
        except Exception:
            logger.exception("OCR drift check failed — assuming screen changed")
            return True, "OCR drift check failed"

    def commit_ocr_baseline(self, ocr_text: str) -> None:
        text = ocr_text.strip()
        if text:
            self._baseline_ocr_text = text
        self._pending_probe_ocr_text = ""

    def pending_probe_ocr_text(self) -> str:
        return self._pending_probe_ocr_text

    def _voice_may_use_ocr(self, transcript: str, *, scene_sync: bool = False) -> bool:
        if not self._ocr_enabled:
            return False
        if needs_visual_reasoning(transcript):
            return False
        if scene_sync:
            return True
        if not voice_needs_screen_context(transcript):
            return False
        return prefer_screen_ocr(transcript)

    def observe(
        self,
        screenshot: Screenshot,
        game_id: str,
        *,
        transcript: str | None = None,
        force_vision: bool = False,
        prefetched_ocr_text: str | None = None,
        scene_sync: bool = False,
    ) -> tuple[ScreenObservation, UsageCost | None, str, str]:
        """
        Returns (observation, API usage or None for OCR, method, ocr_preview).

        method: 'ocr' | 'vision' | 'ocr+vision'
        ocr_preview: OCR description when vision was used for the reply (else "").

        force_vision: idle cycles and 20s-interval voice refreshes (never OCR).
        transcript set without force_vision: voice-only OCR when appropriate.
        """
        if force_vision or transcript is None:
            observation, usage = self._describer.describe(
                screenshot, game_id, focus=transcript
            )
            probe = self._pending_probe_ocr_text
            observation = reconcile_screen_observation(
                observation, ocr_text=probe or None, game_id=game_id
            )
            self.commit_ocr_baseline(probe)
            return observation, usage, "vision", ""

        if not self._voice_may_use_ocr(transcript, scene_sync=scene_sync):
            logger.info("Voice screen read: using vision (not OCR path)")
            observation, usage = self._describer.describe(
                screenshot, game_id, focus=transcript
            )
            probe = self._pending_probe_ocr_text
            observation = reconcile_screen_observation(
                observation, ocr_text=probe or None, game_id=game_id
            )
            self.commit_ocr_baseline(probe)
            return observation, usage, "vision", ""

        scale, preprocess, multi_psm, ocr_max_width = self._voice_ocr_params()
        if self._ocr_voice_fast:
            logger.info(
                "Voice screen read: Tesseract OCR (fast path, max width %d)",
                ocr_max_width,
            )
        else:
            logger.info("Voice screen read: using Tesseract OCR")
        print("(reading screen with OCR…)", flush=True)

        ocr_preview = ""
        ocr_text = ""
        try:
            debug_path = None
            if self._ocr_debug_dir is not None:
                self._ocr_debug_dir.mkdir(parents=True, exist_ok=True)
                debug_path = self._ocr_debug_dir / "ocr_debug_last.png"

            if prefetched_ocr_text is not None:
                ocr_text = prefetched_ocr_text
                ocr_s = 0.0
                engine_label = self._ocr_engine
                logger.info("Reusing OCR from drift check (%d chars)", len(ocr_text))
                if self._ocr_save_dir is not None:
                    try:
                        saved = screenshot.save_for_ocr(
                            self._ocr_save_dir, tag="read"
                        )
                        logger.info("OCR input frame saved (prefetch): %s", saved)
                        print(f"(OCR screenshot saved — {saved.name})", flush=True)
                    except Exception:
                        logger.debug("Could not save OCR capture", exc_info=True)
            else:
                ocr_text, ocr_s, engine_label = recognize_screenshot(
                    screenshot,
                    self._ocr_lang,
                    engine=self._ocr_engine,
                    tesseract_cmd=self._tesseract_cmd,
                    tesseract_config=self._tesseract_config,
                    scale_factor=scale,
                    preprocess_mode=preprocess,
                    multi_psm=multi_psm,
                    max_width=ocr_max_width,
                    save_capture_dir=self._ocr_save_dir,
                    save_capture_tag="read",
                    save_debug_path=debug_path,
                )
            observation = observation_from_ocr(
                ocr_text, game_id, engine_label=engine_label
            )
            observation = reconcile_screen_observation(
                observation, ocr_text=ocr_text, game_id=game_id
            )
            logger.info(
                "%s OCR: %.2fs, %d chars, type=%s",
                engine_label.capitalize(),
                ocr_s,
                len(ocr_text),
                observation.screen_type,
            )
            if ocr_is_usable(observation):
                if scene_sync:
                    logger.info("Scene-sync OCR read (screen changed since last cache)")
                    self.commit_ocr_baseline(ocr_text)
                    return observation, None, "ocr", ""
                sufficient, reason = ocr_sufficient_for_transcript(
                    transcript,
                    observation,
                    ocr_text,
                    game_id,
                )
                if sufficient:
                    logger.info("OCR sufficient for voice question (%s)", reason)
                    self.commit_ocr_baseline(ocr_text)
                    return observation, None, "ocr", ""
                logger.info(
                    "OCR not sufficient for voice question (%s) — vision fallback",
                    reason,
                )
                print(
                    f"(OCR not enough for this question — using vision: {reason})",
                    flush=True,
                )
                _print_ocr_preview(observation, note=reason)
                ocr_preview = observation.description
                method = "ocr+vision"
            else:
                logger.info("OCR text too sparse — falling back to vision")
                print("(OCR found little text — using vision instead)", flush=True)
                _print_ocr_preview(observation, note="too little text")
                ocr_preview = observation.description
                method = "ocr+vision"
        except Exception:
            logger.exception("OCR failed — falling back to vision")
            print("(OCR failed — using vision instead)", flush=True)
            ocr_preview = ""
            method = "ocr+vision"

        print("(reading screen with vision…)", flush=True)
        observation, usage = self._describer.describe(
            screenshot, game_id, focus=transcript
        )
        probe = ocr_text or self._pending_probe_ocr_text
        observation = reconcile_screen_observation(
            observation, ocr_text=probe or None, game_id=game_id
        )
        self.commit_ocr_baseline(probe)
        return observation, usage, method, ocr_preview
