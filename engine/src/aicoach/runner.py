from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import replace
from typing import Callable

from aicoach import events as ev
from aicoach.capture import ScreenCapturer, Screenshot
from aicoach.coach import AICoach, CoachAdvice
from aicoach.config import Settings
from aicoach.cycle_timings import CycleTimings
from aicoach.pricing import estimate_stt_cost_usd
from aicoach.prompts import load_prompt
from aicoach.tts import OpenAITTS
from aicoach.voice import (
    MicUtterance,
    VoiceListener,
    transcribe_utterance,
    voice_needs_screen_context,
    voice_should_use_vision_read,
    voice_wants_fresh_screen_read,
)
from aicoach.console import safe_print
from aicoach.perf import CaptureBreakdown, apply_low_priority, perf_event

logger = logging.getLogger(__name__)

_POLL_S = 0.2


class CoachRunner:
    """
    Main loop: periodic screen coaching when idle, voice-triggered replies when
    the user speaks (RMS-gated, no push-to-talk).
    """

    def __init__(
        self,
        settings: Settings,
        game_id: str,
        on_advice: Callable[[CoachAdvice, Screenshot], None] | None = None,
        on_event: Callable[[dict], None] | None = None,
        monitor_index: int = 1,
    ) -> None:
        self._settings = settings
        self._game_id = game_id
        self._on_event = on_event
        self._system_prompt = load_prompt(game_id)
        self._capturer = ScreenCapturer(
            monitor_index=monitor_index,
            max_width=settings.capture_max_width,
            jpeg_quality=settings.capture_jpeg_quality,
        )
        self._coach = AICoach(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            describe_model=settings.openai_describe_model,
            image_detail=settings.image_detail,
            describe_max_tokens=settings.describe_max_tokens,
            ocr_enabled=settings.ocr_enabled,
            ocr_language=settings.ocr_language,
            ocr_engine=settings.ocr_engine,
            tesseract_cmd=settings.tesseract_cmd,
            tesseract_config=settings.tesseract_config,
            ocr_scale_factor=settings.ocr_scale_factor,
            ocr_preprocess_mode=settings.ocr_preprocess_mode,
            ocr_multi_psm=settings.ocr_multi_psm,
            ocr_max_width=settings.ocr_max_width,
            ocr_voice_fast=settings.ocr_voice_fast,
            ocr_save_dir=(
                settings.screenshots_dir if settings.ocr_save_screenshots else None
            ),
            ocr_debug_dir=(
                settings.screenshots_dir if settings.ocr_debug_save else None
            ),
            max_history_messages=settings.max_history_messages,
            temperature=settings.coach_temperature,
            web_search_enabled=settings.web_search_enabled,
            web_search_model=settings.web_search_model,
            web_search_context_size=settings.web_search_context_size,
            web_search_scenes=settings.web_search_scenes,
        )
        self._tts: OpenAITTS | None = None
        if settings.tts_enabled:
            self._tts = OpenAITTS(
                settings.openai_api_key,
                model=settings.tts_model,
                voice=settings.tts_voice,
            )
        self._voice: VoiceListener | None = None
        if settings.voice_input_enabled:
            try:
                self._voice = VoiceListener(
                    min_rms=settings.voice_min_rms,
                    silence_ms=settings.voice_silence_ms,
                    min_speech_ms=settings.voice_min_speech_ms,
                    barge_speech_ms=settings.voice_barge_speech_ms,
                    max_utterance_s=settings.voice_max_utterance_seconds,
                )
            except Exception:
                logger.exception("Voice input unavailable — continuing screen-only")

        self._on_advice = on_advice or self._default_on_advice
        self._running = True
        self._session_cost_usd = 0.0
        self._call_count = 0
        self._last_screenshot: Screenshot | None = None
        self._last_screenshot_at: float = 0.0
    def _emit(self, event: dict) -> None:
        """Forward a structured event to the UI consumer; never crash the loop."""
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            logger.exception("event consumer raised; dropping event")

    def _set_mic_active(self, active: bool) -> None:
        if self._voice:
            self._voice.set_mic_active(active)

    def _emit_perf(
        self,
        phase: str,
        *,
        state: str,
        duration_ms: float,
        **extra: object,
    ) -> None:
        self._emit(perf_event(phase, state=state, duration_ms=duration_ms, **extra))

    def _emit_cost(self, advice: CoachAdvice) -> None:
        self._emit(
            ev.cost_event(
                advice,
                session_usd=self._session_cost_usd,
                call_count=self._call_count,
            )
        )

    def _seconds_since_last_screenshot(self) -> float:
        if self._last_screenshot_at <= 0:
            return float("inf")
        return time.monotonic() - self._last_screenshot_at

    def _record_screenshot(self, screenshot: Screenshot) -> None:
        self._last_screenshot = screenshot
        self._last_screenshot_at = time.monotonic()

    def _capture_for_ocr(
        self, *, breakdown: CaptureBreakdown | None = None
    ) -> Screenshot:
        """Native monitor PNG for voice/OCR (not CAPTURE_MAX_WIDTH JPEG)."""
        full = (
            self._coach.ocr_active
            and self._settings.ocr_capture_full_quality
        )
        return self._capturer.capture(full_quality=full, breakdown=breakdown)

    def _voice_screen_plan(
        self,
        transcript: str,
        *,
        refresh_needed: bool,
        refresh_reason: str,
    ) -> tuple[bool, bool, bool, str]:
        """
        Returns (capture, refresh_read, scene_sync, reason).

        Every voice turn captures + OCR-probes first (see _sync_voice_screen).
        """
        wants_fresh = voice_wants_fresh_screen_read(transcript)
        needs_context = voice_needs_screen_context(transcript)
        if refresh_needed:
            sync = not needs_context and not voice_should_use_vision_read(transcript)
            return True, True, sync, refresh_reason
        if wants_fresh or needs_context:
            return True, True, False, "screen question — OCR first, vision if needed"
        return True, False, False, "casual chat — OCR verified unchanged"

    def _voice_turn_cancelled(self) -> bool:
        """Another utterance finished while this turn was still running."""
        if self._voice and self._voice.pending_count() > 0:
            safe_print(
                "(newer speech detected — cancelling this reply)",
                flush=True,
            )
            return True
        return False

    def _pop_latest_utterance(self, first: MicUtterance) -> MicUtterance:
        """Keep only the newest queued clip so we do not loop stale requests."""
        latest = first
        dropped = 0
        while self._voice is not None:
            newer = self._voice.poll()
            if newer is None:
                break
            latest = newer
            dropped += 1
        if dropped:
            safe_print(
                f"(dropped {dropped} older queued clip(s) — processing latest speech only)",
                flush=True,
            )
        return latest

    def _print_timings(self, advice: CoachAdvice) -> None:
        for line in advice.timings.format_lines():
            safe_print(line)

    def _print_screen_observation(self, advice: CoachAdvice) -> None:
        ocr_preview = advice.ocr_preview or advice.timings.ocr_preview
        if ocr_preview:
            safe_print("--- OCR output (not used for reply) ---")
            safe_print(ocr_preview)
            safe_print("---")
        if not advice.screen_description:
            return
        method = advice.timings.screen_read_method
        if method == "ocr":
            label = "OCR (Tesseract)"
        elif method == "ocr+vision":
            label = "Vision (used for reply)"
        else:
            label = "vision"
        safe_print(f"--- Screen observation ({label}) ---")
        safe_print(advice.screen_description)
        safe_print("---")

    def _default_on_advice(self, advice: CoachAdvice, screenshot: Screenshot) -> None:
        vision_usd = advice.usage.estimated_usd if advice.usage else 0.0
        web_usd = advice.web.estimated_usd if advice.web else 0.0
        tts_usd = advice.tts.estimated_usd if advice.tts else 0.0
        self._session_cost_usd += vision_usd + web_usd + tts_usd
        self._call_count += 1

        divider = "=" * 60
        label = "Voice" if advice.trigger == "voice" else "Screen"
        safe_print(f"\n{divider}")
        safe_print(f"[{screenshot.captured_at.isoformat()}] Coach ({advice.game_id}) — {label}")
        if advice.scene:
            safe_print(f"Screen: {advice.scene}")
        self._print_screen_observation(advice)
        if advice.map_intel_notes:
            safe_print("--- Map intel (hard sections) ---")
            if advice.map_intel_name:
                safe_print(advice.map_intel_name)
            safe_print(advice.map_intel_notes)
            safe_print("---")
        if advice.web:
            safe_print("(web search used this cycle)")
        if advice.usage or advice.web or advice.tts:
            parts = []
            if advice.describe_usage and advice.response_usage:
                parts.append(
                    f"describe ~${advice.describe_usage.estimated_usd:.4f} | "
                    f"coach ~${advice.response_usage.estimated_usd:.4f}"
                )
            elif advice.usage:
                parts.append(
                    f"API ~${advice.usage.estimated_usd:.4f} "
                    f"({advice.usage.prompt_tokens} in / "
                    f"{advice.usage.completion_tokens} out)"
                )
            if advice.web:
                parts.append(
                    f"web ~${advice.web.estimated_usd:.4f} "
                    f"({advice.web.search_calls} search)"
                )
            if advice.tts:
                parts.append(
                    f"TTS ~${advice.tts.estimated_usd:.4f} "
                    f"({advice.tts.characters} chars, "
                    f"{advice.tts.playback_seconds:.1f}s)"
                )
            safe_print(" | ".join(parts))
            safe_print(
                f"Cycle total: ~${vision_usd + web_usd + tts_usd:.4f} | "
                f"Session: ~${self._session_cost_usd:.4f} ({self._call_count} cycles)"
            )
        safe_print(divider)
        safe_print(advice.text)
        safe_print(divider, flush=True)

    def stop(self) -> None:
        self._running = False
        if self._voice:
            self._voice.stop()

    def _wait_after_speech(self) -> float:
        delay = self._settings.post_speech_delay_seconds
        if delay > 0 and self._running:
            logger.info("Post-speech delay: %.1fs", delay)
            time.sleep(delay)
        return delay

    def _wait_min_cycle_interval(self, cycle_start: float) -> float:
        elapsed = time.monotonic() - cycle_start
        sleep_for = max(0.0, self._settings.capture_interval_seconds - elapsed)
        if sleep_for > 0 and self._running:
            logger.debug("Waiting %.1fs to complete cycle interval", sleep_for)
            time.sleep(sleep_for)
        return sleep_for

    def _barge_in_stop_check(self, *, grace_until: float = 0.0) -> bool:
        """
        Stop TTS when the user has spoken ~VOICE_BARGE_SPEECH_MS during coach audio,
        or when a full utterance is queued. grace_until ignores bleed at TTS start.
        """
        if not self._voice:
            return False
        if grace_until > 0.0 and time.monotonic() < grace_until:
            return False
        if self._voice.barge_in_requested():
            return True
        if self._voice.pending_count() > 0:
            return True
        return False

    def _speak_advice(
        self,
        advice: CoachAdvice,
        cycle_start: float,
        *,
        mic_during_tts: bool = True,
    ) -> CoachAdvice:
        if not self._tts or advice.skip or not advice.text:
            return advice
        if self._voice and self._voice_turn_cancelled():
            advice.timings.extra.append("TTS: skipped (newer speech)")
            return advice
        tts_hold = False
        if mic_during_tts and self._voice and not self._voice.is_coach_speaking():
            self._voice.set_coach_speaking(True)
            tts_hold = True
        try:
            grace_s = max(0.0, self._settings.tts_barge_grace_seconds)
            grace_until = time.monotonic() + grace_s if grace_s > 0 else 0.0

            def stop_check() -> bool:
                if not mic_during_tts:
                    return False
                return self._barge_in_stop_check(grace_until=grace_until)

            if mic_during_tts:
                self._set_mic_active(True)
            self._emit(ev.status_event(ev.STATE_SPEAKING, game_id=self._game_id))
            tts_started = time.monotonic()
            tts_result = self._tts.speak(
                advice.text,
                stop_check=stop_check,
            )
            self._emit_perf(
                "tts_playback",
                state=ev.STATE_SPEAKING,
                duration_ms=(time.monotonic() - tts_started) * 1000,
                chars=tts_result.characters,
                interrupted=tts_result.interrupted,
            )
            if self._voice:
                self._voice.consume_barge_in()
            advice = replace(advice, tts=tts_result)
            advice.timings.tts_api_s = tts_result.api_seconds
            advice.timings.tts_play_s = tts_result.play_seconds
            self._session_cost_usd += tts_result.estimated_usd
            status = "interrupted" if tts_result.interrupted else "done"
            safe_print(
                f"TTS ({status}): ~${tts_result.estimated_usd:.4f} "
                f"({tts_result.characters} chars, "
                f"{tts_result.play_seconds:.1f}s playback)",
                flush=True,
            )
            if tts_result.interrupted:
                advice.timings.extra.append("TTS interrupted — user speech")
                return advice
            if mic_during_tts and self._voice and self._voice.pending_count() > 0:
                advice.timings.extra.append("post-speech wait: skipped (voice queued)")
            else:
                if not mic_during_tts:
                    self._emit(
                        ev.status_event(
                            ev.STATE_LISTENING,
                            detail="cooldown",
                            game_id=self._game_id,
                        )
                    )
                advice.timings.post_speech_wait_s = self._wait_after_speech()
        finally:
            if tts_hold and self._voice:
                self._voice.set_coach_speaking(False)
        advice.timings.cycle_total_s = time.monotonic() - cycle_start
        return advice

    def _run_screen_cycle(self) -> None:
        cycle_start = time.monotonic()
        self._set_mic_active(False)
        try:
            deferred = self._run_screen_cycle_inner(cycle_start)
            if deferred is None:
                return
            advice, _screenshot = deferred
            if not self._tts or not advice.text:
                self._emit_cost(advice)
                return
            advice = self._speak_advice(advice, cycle_start, mic_during_tts=False)
            self._print_timings(advice)
            self._emit_cost(advice)
        finally:
            self._set_mic_active(True)

    def _run_screen_cycle_inner(
        self, cycle_start: float
    ) -> tuple[CoachAdvice, Screenshot] | None:
        timings = CycleTimings()
        apply_low_priority()
        self._emit(ev.status_event(ev.STATE_CAPTURING, game_id=self._game_id))
        screenshot: Screenshot | None = None

        if self._coach.has_cached_observation() and self._coach.ocr_active:
            probe_bd = CaptureBreakdown()
            probe_started = time.monotonic()
            probe_shot = self._capturer.capture(probe=True, breakdown=probe_bd)
            probe_ms = (time.monotonic() - probe_started) * 1000
            self._emit_perf(
                "capture_probe",
                state=ev.STATE_CAPTURING,
                duration_ms=probe_ms,
                grab_ms=round(probe_bd.grab_s * 1000, 1),
                encode_ms=round(probe_bd.encode_s * 1000, 1),
                backend=self._capturer.last_grab_backend,
                w=probe_shot.width,
                h=probe_shot.height,
            )
            timings.extra.append(f"probe grab={probe_bd.grab_s:.3f}s encode={probe_bd.encode_s:.3f}s")
            changed, drift_reason = self._coach.probe_screen_change(
                probe_shot,
                self._game_id,
            )
            timings.extra.append(f"OCR drift check: {drift_reason}")
            if not changed:
                cache_ok, cache_reason = self._coach.cached_observation_still_valid(
                    self._game_id
                )
                if not cache_ok:
                    changed = True
                    drift_reason = cache_reason
            if not changed:
                safe_print(
                    f"(idle screen check — unchanged: {drift_reason}, skipping vision)",
                    flush=True,
                )
                self._emit(
                    ev.status_event(
                        ev.STATE_LISTENING,
                        detail=f"idle screen unchanged ({drift_reason})",
                        game_id=self._game_id,
                    )
                )
                return None
            full_bd = CaptureBreakdown()
            capture_started = time.monotonic()
            screenshot = self._capturer.capture(breakdown=full_bd)
            timings.capture_s = time.monotonic() - capture_started
            self._emit_perf(
                "capture_full",
                state=ev.STATE_CAPTURING,
                duration_ms=timings.capture_s * 1000,
                grab_ms=round(full_bd.grab_s * 1000, 1),
                encode_ms=round(full_bd.encode_s * 1000, 1),
                backend=self._capturer.last_grab_backend,
                w=screenshot.width,
                h=screenshot.height,
                kb=round(screenshot.size_kb),
            )
        else:
            full_bd = CaptureBreakdown()
            capture_started = time.monotonic()
            screenshot = self._capturer.capture(breakdown=full_bd)
            timings.capture_s = time.monotonic() - capture_started
            self._emit_perf(
                "capture_full",
                state=ev.STATE_CAPTURING,
                duration_ms=timings.capture_s * 1000,
                grab_ms=round(full_bd.grab_s * 1000, 1),
                encode_ms=round(full_bd.encode_s * 1000, 1),
                backend=self._capturer.last_grab_backend,
                w=screenshot.width,
                h=screenshot.height,
                kb=round(screenshot.size_kb),
            )

        self._record_screenshot(screenshot)
        if self._settings.save_screenshots:
            path = screenshot.save(self._settings.screenshots_dir)
            logger.info("Saved screenshot to %s", path)

        self._emit(ev.status_event(ev.STATE_THINKING, game_id=self._game_id))
        think_started = time.monotonic()
        advice = self._coach.analyze(
            screenshot=screenshot,
            game_id=self._game_id,
            system_prompt=self._system_prompt,
            timings=timings,
        )
        self._emit_perf(
            "coach_screen_cycle",
            state=ev.STATE_THINKING,
            duration_ms=(time.monotonic() - think_started) * 1000,
            vision_s=round(timings.describe_s, 2),
            coach_s=round(timings.coach_s, 2),
            scene=advice.scene,
        )

        if advice.skip:
            if advice.usage:
                self._session_cost_usd += advice.usage.estimated_usd
            self._call_count += 1
            divider = "=" * 60
            safe_print(f"\n{divider}")
            safe_print(f"[{screenshot.captured_at.isoformat()}] Coach ({advice.game_id}) — Screen")
            if advice.scene:
                safe_print(f"Screen: {advice.scene}")
            self._print_screen_observation(advice)
            if advice.map_intel_notes:
                safe_print("--- Map intel (hard sections) ---")
                if advice.map_intel_name:
                    safe_print(advice.map_intel_name)
                safe_print(advice.map_intel_notes)
                safe_print("---")
            safe_print("(nothing new to say — no TTS)")
            if advice.usage:
                safe_print(
                    f"API ~${advice.usage.estimated_usd:.4f} "
                    f"({advice.usage.prompt_tokens} in / "
                    f"{advice.usage.completion_tokens} out)"
                )
            advice.timings.cycle_total_s = time.monotonic() - cycle_start
            self._print_timings(advice)
            safe_print(divider, flush=True)
            self._emit(ev.advice_event(advice, screenshot))
            self._emit_cost(advice)
            self._emit(ev.status_event(ev.STATE_LISTENING, game_id=self._game_id))
            return None

        self._on_advice(advice, screenshot)
        self._emit(ev.advice_event(advice, screenshot))
        self._emit(ev.status_event(ev.STATE_LISTENING, game_id=self._game_id))
        return advice, screenshot

    def _run_voice_turn(self, utterance: MicUtterance) -> None:
        cycle_start = time.monotonic()
        timings = CycleTimings()
        try:
            self._run_voice_turn_inner(utterance, cycle_start, timings)
        finally:
            if self._voice:
                self._voice.consume_barge_in()
                self._voice.set_coach_speaking(False)
                self._set_mic_active(True)

    def _run_voice_turn_inner(
        self,
        utterance: MicUtterance,
        cycle_start: float,
        timings: CycleTimings,
    ) -> None:
        safe_print("(processing your speech…)", flush=True)
        logger.info("Voice utterance ended — transcribing")
        self._set_mic_active(False)
        self._emit(ev.status_event(ev.STATE_TRANSCRIBING, game_id=self._game_id))

        transcript = ""
        stt_s = 0.0
        stt_usd = 0.0

        try:
            stt_started = time.monotonic()
            transcript, stt_s, stt_usd = transcribe_utterance(
                self._settings.openai_api_key,
                utterance.pcm_chunks,
                model=self._settings.voice_stt_model,
            )
            self._emit_perf(
                "stt_whisper",
                state=ev.STATE_TRANSCRIBING,
                duration_ms=(time.monotonic() - stt_started) * 1000,
                audio_s=round(stt_s, 2),
            )
        except Exception:
            logger.exception("Speech-to-text failed")
            self._set_mic_active(True)
            return

        timings.stt_s = stt_s
        timings.stt_usd = stt_usd
        self._session_cost_usd += stt_usd

        if len(transcript) < 2:
            safe_print(
                "(voice ignored — transcription empty or noise; "
                "try speaking louder or longer)",
                flush=True,
            )
            logger.info("Ignored empty/noise transcription")
            return

        safe_print(
            f'You said: "{transcript}"',
            flush=True,
        )
        safe_print(
            f"STT: ~${stt_usd:.4f} ({stt_s:.1f}s API) — starting coach",
            flush=True,
        )
        self._emit(ev.transcript_event(transcript, partial=False))

        if self._voice_turn_cancelled():
            return

        capture_bd = CaptureBreakdown()
        capture_started = time.monotonic()
        screenshot = self._capture_for_ocr(breakdown=capture_bd)
        timings.capture_s = time.monotonic() - capture_started
        self._record_screenshot(screenshot)
        self._emit_perf(
            "capture_voice",
            state=ev.STATE_CAPTURING,
            duration_ms=timings.capture_s * 1000,
            grab_ms=round(capture_bd.grab_s * 1000, 1),
            encode_ms=round(capture_bd.encode_s * 1000, 1),
            w=screenshot.width,
            h=screenshot.height,
        )

        refresh_needed = True
        refresh_reason = "no OCR baseline"
        if self._coach.ocr_active:
            self._coach.probe_screen_change(screenshot, game_id=self._game_id)
            refresh_needed, refresh_reason = self._coach.voice_screen_refresh_needed(
                self._game_id
            )
        elif self._coach.has_cached_observation():
            refresh_needed, refresh_reason = False, "OCR disabled"

        capture, refresh_read, scene_sync, reason = self._voice_screen_plan(
            transcript,
            refresh_needed=refresh_needed,
            refresh_reason=refresh_reason,
        )
        screen_ocr_verified = (
            self._coach.ocr_active
            and not refresh_needed
            and self._coach.has_cached_observation()
        )
        prefetched = (
            self._coach.pending_probe_ocr_text()
            if refresh_read and self._coach.ocr_active
            else None
        )

        if refresh_read:
            safe_print(f"(screenshot + read — {reason})", flush=True)
        elif screen_ocr_verified:
            safe_print(f"(screenshot — {reason})", flush=True)
        else:
            safe_print(f"(screenshot — {reason})", flush=True)

        if self._voice_turn_cancelled():
            return

        vision_only = voice_should_use_vision_read(transcript)

        think_started = time.monotonic()
        self._emit(ev.status_event(ev.STATE_THINKING, game_id=self._game_id))
        advice = self._coach.respond_to_user(
            transcript,
            game_id=self._game_id,
            system_prompt=self._system_prompt,
            screenshot=screenshot,
            refresh_screen=refresh_read,
            vision_only=vision_only,
            prefetched_ocr_text=prefetched or None,
            screen_ocr_verified=screen_ocr_verified,
            scene_sync=scene_sync,
            timings=timings,
        )
        self._emit_perf(
            "coach_voice_turn",
            state=ev.STATE_THINKING,
            duration_ms=(time.monotonic() - think_started) * 1000,
            vision_s=round(timings.describe_s, 2),
            coach_s=round(timings.coach_s, 2),
        )

        if advice.skip or not advice.text:
            return

        if self._voice_turn_cancelled():
            return

        display_shot = screenshot or self._last_screenshot
        if display_shot is None:
            from datetime import datetime, timezone

            display_shot = Screenshot(
                png_bytes=b"",
                captured_at=datetime.now(timezone.utc),
                monitor_index=self._capturer.monitor_index,
            )

        self._on_advice(advice, display_shot)
        self._emit(ev.advice_event(advice, display_shot))
        if self._voice_turn_cancelled():
            return
        advice = self._speak_advice(advice, cycle_start)
        self._print_timings(advice)
        self._emit_cost(advice)
        self._emit(ev.status_event(ev.STATE_LISTENING, game_id=self._game_id))

    def _screen_cycle_due(self, last_screen_cycle: float) -> bool:
        if self._voice and (
            self._voice.is_user_speaking()
            or self._voice.is_coach_speaking()
            or self._voice.pending_count() > 0
        ):
            return False
        elapsed = time.monotonic() - last_screen_cycle
        return elapsed >= self._settings.capture_interval_seconds

    def run(self) -> None:
        interval = self._settings.capture_interval_seconds
        delay = self._settings.post_speech_delay_seconds
        logger.info(
            "Starting AI coach for '%s' — capture %s, screen=%s, coach=%s, "
            "screen every %.0fs when idle, %.0fs after coach speech, TTS=%s, web=%s, voice=%s, OCR=%s",
            self._game_id,
            self._capturer.monitor_label(),
            "OCR+vision" if self._coach.ocr_active else self._settings.openai_describe_model,
            self._settings.openai_model,
            interval,
            delay,
            bool(self._tts),
            self._settings.web_search_enabled,
            bool(self._voice),
            self._coach.ocr_active,
        )
        apply_low_priority()
        self._emit(ev.status_event(ev.STATE_STARTING, game_id=self._game_id))
        if self._voice:
            self._voice.start()
            logger.info(
                "Speak naturally — min volume gate %.3f (raise VOICE_MIN_RMS if phantom speech)",
                self._settings.voice_min_rms,
            )
        if self._settings.web_search_enabled:
            logger.info(
                "Map web research runs once per map on song select; gameplay uses cached MAP INTEL only."
            )

        last_screen_cycle = time.monotonic()
        self._emit(ev.status_event(ev.STATE_LISTENING, game_id=self._game_id))

        while self._running:
            try:
                utterance: MicUtterance | None = None
                if self._voice:
                    utterance = self._voice.poll()
                    if utterance is None:
                        if self._voice.pending_count() > 0:
                            timeout = 0.05
                        elif self._screen_cycle_due(last_screen_cycle):
                            timeout = _POLL_S
                        else:
                            remaining = (
                                self._settings.capture_interval_seconds
                                - (time.monotonic() - last_screen_cycle)
                            )
                            timeout = min(_POLL_S, max(0.05, remaining))
                        utterance = self._voice.wait(timeout)

                if utterance is not None:
                    utterance = self._pop_latest_utterance(utterance)
                    self._run_voice_turn(utterance)
                    last_screen_cycle = time.monotonic()
                    continue

                if self._screen_cycle_due(last_screen_cycle):
                    self._run_screen_cycle()
                    last_screen_cycle = time.monotonic()
            except Exception as exc:
                logger.exception("Coach cycle failed; will retry after short delay")
                self._emit(ev.error_event(f"Coach cycle failed: {exc}"))
                time.sleep(min(5.0, self._settings.capture_interval_seconds))

        if self._voice:
            self._voice.stop()
        self._emit(ev.status_event(ev.STATE_STOPPED, game_id=self._game_id))


def install_signal_handlers(runner: CoachRunner) -> None:
    def _handle_signal(_signum: int, _frame: object) -> None:
        safe_print("\nStopping AI coach...", flush=True)
        runner.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _handle_signal)
