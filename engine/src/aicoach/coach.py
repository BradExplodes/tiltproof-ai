from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from aicoach.openai_client import build_openai_client

from aicoach.capture import Screenshot
from aicoach.cycle_timings import CycleTimings
from aicoach.pricing import UsageCost, estimate_cost_usd
from aicoach.prompts import load_coach_prompt
from aicoach.map_intel import (
    extract_map_title_from_description,
    format_map_intel_for_coach,
    normalize_map_key,
)
from aicoach.play_speech import gameplay_fallback_line, scene_requires_speech
from aicoach.response_parse import (
    ParsedCoachResponse,
    clean_spoken_output,
    is_silent_reply,
    parse_coach_response,
)
from aicoach.screen_observation import ScreenObservation
from aicoach.tts import TTSResult
from aicoach.screen_read import ScreenReader
from aicoach.voice.screen_intent import voice_needs_screen_context
from aicoach.vision_describe import ScreenDescriber
from aicoach.web_search import MapIntel, WebSearchCoach, WebSearchUsage, scene_triggers_web

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoachAdvice:
    """Final coaching output after describe + respond (+ optional web)."""

    text: str
    model: str
    game_id: str
    scene: str = ""
    skip: bool = False
    screen_description: str = ""
    ocr_preview: str = ""
    usage: UsageCost | None = None
    describe_usage: UsageCost | None = None
    response_usage: UsageCost | None = None
    web: WebSearchUsage | None = None
    tts: TTSResult | None = None
    map_intel_notes: str = ""
    map_intel_name: str = ""
    timings: CycleTimings = field(default_factory=CycleTimings)
    trigger: str = "screen"
    user_said: str = ""


def _merge_usage(
    a: UsageCost | None, b: UsageCost | None
) -> UsageCost | None:
    if not a and not b:
        return None
    if not a:
        return b
    if not b:
        return a
    return UsageCost(
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
        estimated_usd=a.estimated_usd + b.estimated_usd,
    )


def _usage_with_web(
    usage: UsageCost | None, web: WebSearchUsage | None
) -> UsageCost | None:
    if not web:
        return usage
    if not usage:
        return UsageCost(0, 0, web.estimated_usd)
    return UsageCost(
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.estimated_usd + web.estimated_usd,
    )


class AICoach:
    """
    Two-stage coach:
    1. Vision model — exhaustive screen description (no personality)
    2. Text model — friend voice response from that description
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        image_detail: str = "high",
        max_history_messages: int = 12,
        describe_max_tokens: int = 450,
        ocr_enabled: bool = True,
        ocr_language: str = "en",
        ocr_engine: str = "tesseract",
        tesseract_cmd: str | None = None,
        tesseract_config: str = "--oem 3 --psm 11",
        ocr_scale_factor: float = 2.0,
        ocr_preprocess_mode: str = "balanced",
        ocr_multi_psm: bool = True,
        ocr_max_width: int = 1600,
        ocr_voice_fast: bool = True,
        ocr_save_dir: Path | None = None,
        ocr_debug_dir: Path | None = None,
        temperature: float = 0.65,
        *,
        describe_model: str | None = None,
        web_search_enabled: bool = False,
        web_search_model: str = "gpt-4o-mini",
        web_search_context_size: str = "medium",
        web_search_scenes: frozenset[str] = frozenset(
            {"map_select", "menu", "results"}
        ),
    ) -> None:
        self._client = build_openai_client(api_key)
        self._response_model = model
        self._describe_model = describe_model or model
        self._max_history_messages = max_history_messages
        self._temperature = temperature
        self._spoken_lines: list[str] = []
        self._cycle = 0
        self._last_scene = ""
        self._last_observation_text = ""
        self._cached_observation: ScreenObservation | None = None
        self._cached_observation_at: float = 0.0
        self._last_screen_read_method: str = ""
        self._consecutive_silences = 0
        self._map_intel: MapIntel | None = None
        self._web_enabled = web_search_enabled
        self._web_scenes = web_search_scenes
        describer = ScreenDescriber(
            api_key,
            model=self._describe_model,
            image_detail=image_detail,
            max_tokens=describe_max_tokens,
        )
        self._screen_reader = ScreenReader(
            describer,
            ocr_enabled=ocr_enabled,
            ocr_lang=ocr_language,
            ocr_engine=ocr_engine,  # type: ignore[arg-type]
            tesseract_cmd=tesseract_cmd,
            tesseract_config=tesseract_config,
            ocr_scale_factor=ocr_scale_factor,
            ocr_preprocess_mode=ocr_preprocess_mode,
            ocr_multi_psm=ocr_multi_psm,
            ocr_max_width=ocr_max_width,
            ocr_voice_fast=ocr_voice_fast,
            ocr_save_dir=ocr_save_dir,
            ocr_debug_dir=ocr_debug_dir,
        )
        self._web: WebSearchCoach | None = None
        if web_search_enabled:
            self._web = WebSearchCoach(
                api_key,
                model=web_search_model,
                search_context_size=web_search_context_size,
            )

    @property
    def ocr_active(self) -> bool:
        return self._screen_reader.ocr_active

    def has_cached_observation(self) -> bool:
        return self._cached_observation is not None

    def screen_read_age_s(self) -> float:
        """Seconds since the last OCR/vision observation was stored."""
        if self._cached_observation_at <= 0:
            return float("inf")
        return time.monotonic() - self._cached_observation_at

    def probe_screen_change(self, screenshot: Screenshot, game_id: str) -> tuple[bool, str]:
        """Fast OCR compare vs last full read — True if the screen likely changed."""
        return self._screen_reader.probe_screen_change(screenshot, game_id=game_id)

    def cached_observation_still_valid(self, game_id: str) -> tuple[bool, str]:
        """Cross-check cached vision/OCR against the probe OCR from this capture."""
        from aicoach.ocr_change import (
            cached_observation_matches_probe,
            ocr_scene_changed,
        )

        if not self._cached_observation:
            return True, ""
        probe = self.pending_probe_ocr_text()
        changed, scene_reason = ocr_scene_changed(
            self._cached_observation, probe, game_id=game_id
        )
        if changed:
            return False, scene_reason
        return cached_observation_matches_probe(
            self._cached_observation,
            probe,
            game_id=game_id,
        )

    def voice_screen_refresh_needed(self, game_id: str) -> tuple[bool, str]:
        """
        After probe OCR on a fresh capture, decide if we must run OCR/vision again.
        """
        from aicoach.ocr_change import ocr_scene_changed, ocr_substantially_changed

        if not self._cached_observation:
            return True, "no cached screen read"
        probe = self.pending_probe_ocr_text()
        if not probe.strip():
            return True, "probe OCR empty"
        baseline = self._screen_reader._baseline_ocr_text  # noqa: SLF001
        changed, drift_reason = ocr_substantially_changed(
            baseline, probe, game_id=game_id
        )
        if changed:
            return True, drift_reason
        scene_changed, scene_reason = ocr_scene_changed(
            self._cached_observation, probe, game_id=game_id
        )
        if scene_changed:
            return True, scene_reason
        cache_ok, cache_reason = self.cached_observation_still_valid(game_id)
        if not cache_ok:
            return True, cache_reason
        return False, "OCR verified screen unchanged"

    def pending_probe_ocr_text(self) -> str:
        return self._screen_reader.pending_probe_ocr_text()

    def _trim_spoken_recall(self) -> None:
        if len(self._spoken_lines) > self._max_history_messages:
            self._spoken_lines = self._spoken_lines[-self._max_history_messages :]

    def _coach_system_prompt(self, coach_prompt: str) -> str:
        """Prior spoken lines only — never replay old observations (avoids 'nothing new' diffing)."""
        if not self._spoken_lines:
            return coach_prompt
        recap = "\n".join(f"- {line}" for line in self._spoken_lines)
        return (
            f"{coach_prompt}\n\n"
            "YOUR RECENT SPOKEN LINES (wording reference only — you MUST still speak this turn; "
            "do NOT treat these as proof nothing new happened):\n"
            f"{recap}"
        )

    def _scene_from_observation(self, obs: ScreenObservation) -> str:
        return obs.screen_type or "unknown"

    def _observe_screen(
        self,
        screenshot: Screenshot,
        game_id: str,
        timings: CycleTimings,
        *,
        transcript: str | None = None,
        force_vision: bool = False,
        prefetched_ocr_text: str | None = None,
        scene_sync: bool = False,
    ) -> tuple[ScreenObservation, UsageCost | None, str]:
        started = time.monotonic()
        observation, usage, method, ocr_preview = self._screen_reader.observe(
            screenshot,
            game_id,
            transcript=transcript,
            force_vision=force_vision,
            prefetched_ocr_text=prefetched_ocr_text,
            scene_sync=scene_sync,
        )
        timings.describe_s = time.monotonic() - started
        timings.screen_read_method = method
        timings.ocr_preview = ocr_preview
        self._last_screen_read_method = method
        return observation, usage, ocr_preview

    def _is_map_select(self, scene: str) -> bool:
        return scene_triggers_web(scene, frozenset({"map_select"}))

    def _is_gameplay(self, scene: str) -> bool:
        return scene_requires_speech(scene)

    def _resolve_map_name(self, obs: ScreenObservation) -> str | None:
        if obs.search_query:
            return obs.search_query
        from_desc = extract_map_title_from_description(obs.description)
        if from_desc:
            return from_desc
        first = obs.description.split("\n")[0].strip()[:120]
        if len(first) >= 8 and first.lower() not in ("unknown", "gameplay", "menu"):
            return first
        return None

    def _maybe_clear_stale_intel(self, map_name: str | None) -> None:
        if not self._map_intel or not map_name:
            return
        if normalize_map_key(map_name) != normalize_map_key(self._map_intel.map_name):
            logger.info("Clearing map intel for new map: %s", map_name)
            self._map_intel = None

    def _needs_map_research(self, obs: ScreenObservation) -> bool:
        if not self._web_enabled or not self._web:
            return False
        map_name = self._resolve_map_name(obs)
        if not map_name:
            return False
        if self._map_intel and normalize_map_key(self._map_intel.map_name) == normalize_map_key(
            map_name
        ):
            return False
        # One web search per map on song select; gameplay only reads cached MAP INTEL.
        return self._is_map_select(self._scene_from_observation(obs))

    def _prefetch_map_intel(
        self,
        observation: ScreenObservation,
        game_id: str,
    ) -> WebSearchUsage | None:
        if not self._needs_map_research(observation):
            return None
        map_name = self._resolve_map_name(observation)
        if not map_name:
            return None
        self._maybe_clear_stale_intel(map_name)
        try:
            _, intel, usage = self._web.research_map(  # type: ignore[union-attr]
                game_id=game_id,
                map_name=map_name,
                scene=self._scene_from_observation(observation),
                vision_say="",
                temperature=min(self._temperature, 0.55),
            )
            if intel:
                self._map_intel = intel
                logger.info("Map intel cached: %s", map_name)
            return usage
        except Exception:
            logger.exception("Map intel prefetch failed")
            return None

    def _prefetch_map_intel_background(
        self,
        observation: ScreenObservation,
        game_id: str,
        timings: CycleTimings,
    ) -> None:
        """Song-select research without blocking vision → coach → TTS."""

        def _run() -> None:
            started = time.monotonic()
            self._prefetch_map_intel(observation, game_id)
            logger.info("Background map research finished in %.1fs", time.monotonic() - started)

        threading.Thread(target=_run, daemon=True, name="map-intel-research").start()
        timings.map_intel_note = "web search started (background — not in analysis total)"
        logger.info(
            "Map research started in background (coach/TTS not waiting for it)"
        )

    def _should_general_web(self, obs: ScreenObservation) -> bool:
        if not self._web_enabled or not self._web:
            return False
        scene = self._scene_from_observation(obs)
        if self._is_map_select(scene):
            return False
        # No web during gameplay — hard-part intel comes from the initial map research only.
        if scene_requires_speech(scene, obs.screen_type):
            return False
        if obs.search_query:
            return True
        return scene_triggers_web(scene, self._web_scenes)

    def _build_response_user_message(
        self, obs: ScreenObservation, cycle: int, *, scene: str = ""
    ) -> str:
        prior = (
            f"\nPrevious screen type: {self._last_scene}."
            if self._last_scene
            else ""
        )
        intel_block = ""
        if self._map_intel:
            is_gameplay = scene_requires_speech(scene or obs.screen_type, obs.screen_type)
            intel_block = "\n\n" + format_map_intel_for_coach(
                self._map_intel, obs, is_gameplay=is_gameplay
            )

        base = (
            f"Moment #{cycle}. New screenshot — react to THIS observation only.{prior}\n\n"
            f"SCREEN_TYPE: {obs.screen_type}\n"
            f"SEARCH_QUERY: {obs.search_query or 'NONE'}\n\n"
            f"SCREEN OBSERVATION:\n{obs.description}\n"
            f"{intel_block}\n\n"
            "TURN RULES:\n"
            "- Output SCENE, SEARCH_QUERY, and a full SAY (2–4 sentences). SAY is required.\n"
            "- Do NOT conclude nothing new happened. Do NOT output NONE or skip.\n"
            "- Similar stats to earlier moments still count — find patterns, progress %, HP, "
            "cursor/playfield detail, MAP INTEL warnings, banter, or a new roast angle in the text above.\n"
            "- Prior spoken lines (if any) are only so you do not repeat the exact same joke."
        )
        if scene_requires_speech(scene or obs.screen_type, obs.screen_type):
            base += (
                "\n- ACTIVE PLAY: prioritize MAP INTEL section callouts (pattern + %) when intel exists; "
                "then reading/HP/combo."
            )
        return base

    def _build_voice_user_message(
        self,
        transcript: str,
        obs: ScreenObservation,
        cycle: int,
        *,
        scene: str = "",
        screen_context_note: str = "",
    ) -> str:
        intel_block = ""
        if self._map_intel:
            is_gameplay = scene_requires_speech(scene or obs.screen_type, obs.screen_type)
            intel_block = "\n\n" + format_map_intel_for_coach(
                self._map_intel, obs, is_gameplay=is_gameplay
            )

        context_line = screen_context_note or "Screen context below (may be from the last automatic capture)."
        return (
            f"Moment #{cycle}. The player spoke to you on voice chat.\n\n"
            f'USER SAID:\n"{transcript}"\n\n'
            "PRIORITY: Respond to what they said — answer questions, react, roast, or coach. "
            f"{context_line}\n\n"
            f"SCREEN_TYPE: {obs.screen_type}\n"
            f"SEARCH_QUERY: {obs.search_query or 'NONE'}\n\n"
            f"SCREEN OBSERVATION:\n{obs.description}\n"
            f"{intel_block}\n\n"
            "TURN RULES:\n"
            "- Output SCENE, SEARCH_QUERY (confirm or NONE), and SAY (2–4 sentences). SAY is required.\n"
            "- Directly address USER SAID; do not ignore their question.\n"
            "- No NONE / silence — you are replying in voice chat."
        )

    def _cache_observation(self, observation: ScreenObservation) -> None:
        self._cached_observation = observation
        self._cached_observation_at = time.monotonic()

    def _observation_changed(self, obs: ScreenObservation) -> bool:
        current = obs.description.strip()
        if not self._last_observation_text:
            return True
        return current != self._last_observation_text

    def _should_retry_after_none(
        self, obs: ScreenObservation, scene: str
    ) -> bool:
        if scene_requires_speech(scene, obs.screen_type):
            return True
        if self._cycle <= 4:
            return True
        if self._consecutive_silences >= 1:
            return True
        if self._observation_changed(obs):
            return True
        return False

    def _ensure_speakable_response(
        self,
        observation: ScreenObservation,
        game_id: str,
        coach_prompt: str,
        cycle: int,
        scene: str,
        parsed: ParsedCoachResponse,
        response_usage: UsageCost | None,
        user_text: str,
        *,
        voice_transcript: str | None = None,
    ) -> tuple[ParsedCoachResponse, UsageCost | None, str, int, float]:
        """Retry (and gameplay fallback) until we have something to speak."""
        requires = scene_requires_speech(scene, observation.screen_type) or bool(
            voice_transcript
        )
        max_attempts = 3 if requires else 2
        extra_calls = 0
        extra_s = 0.0

        for attempt in range(max_attempts):
            spoken = clean_spoken_output(parsed.spoken)
            if spoken and not is_silent_reply(spoken):
                return (
                    replace(parsed, spoken=spoken, skip=False),
                    response_usage,
                    user_text,
                    extra_calls,
                    extra_s,
                )

            if attempt + 1 >= max_attempts:
                break

            if (
                not requires
                and attempt == 0
                and not self._should_retry_after_none(observation, scene)
            ):
                break

            logger.info(
                "No speakable SAY (scene=%s, requires=%s) — retry %s/%s",
                scene,
                requires,
                attempt + 1,
                max_attempts - 1,
            )
            if voice_transcript:
                parsed, retry_usage, user_text, call_s = self._generate_voice_response(
                    voice_transcript,
                    observation,
                    game_id,
                    coach_prompt,
                    cycle,
                    scene,
                )
            else:
                parsed, retry_usage, user_text, call_s = self._generate_response(
                    observation,
                    game_id,
                    coach_prompt,
                    cycle,
                    scene=scene,
                    force_speak=True,
                    active_play=requires,
                )
            extra_calls += 1
            extra_s += call_s
            response_usage = _merge_usage(response_usage, retry_usage)

        if requires and not voice_transcript:
            fallback = gameplay_fallback_line(observation)
            logger.info("Gameplay fallback line after model silence")
            return (
                replace(
                    parsed,
                    spoken=fallback,
                    skip=False,
                    scene=scene or parsed.scene,
                ),
                response_usage,
                user_text,
                extra_calls,
                extra_s,
            )

        if voice_transcript:
            fallback = (
                f"Yeah — {voice_transcript[:100]} — I'm watching, "
                "say that again if you wanted something specific."
            )
            return (
                replace(
                    parsed,
                    spoken=fallback,
                    skip=False,
                    scene=scene or parsed.scene,
                ),
                response_usage,
                user_text,
                extra_calls,
                extra_s,
            )

        return parsed, response_usage, user_text, extra_calls, extra_s

    def _record_spoken(self, spoken: str) -> None:
        self._spoken_lines.append(spoken)
        self._trim_spoken_recall()

    def _generate_response(
        self,
        obs: ScreenObservation,
        game_id: str,
        coach_prompt: str,
        cycle: int,
        *,
        scene: str = "",
        force_speak: bool = False,
        active_play: bool = False,
    ) -> tuple[ParsedCoachResponse, UsageCost | None, str, float]:
        user_text = self._build_response_user_message(obs, cycle, scene=scene)
        if force_speak or active_play:
            user_text += (
                "\n\nREMINDER: Pick something concrete from the observation and SAY it — "
                "do not decide the situation is unchanged."
            )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._coach_system_prompt(coach_prompt)},
            {"role": "user", "content": user_text},
        ]

        started = time.monotonic()
        response = self._client.chat.completions.create(
            model=self._response_model,
            messages=messages,
            temperature=self._temperature,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raw = "SCENE: unknown\nSEARCH_QUERY: NONE\nSAY: NONE"

        parsed = parse_coach_response(raw)
        usage = None
        if response.usage:
            usage = estimate_cost_usd(
                self._response_model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
            logger.info(
                "Coach text (%s): ~$%.4f",
                self._response_model,
                usage.estimated_usd,
            )

        elapsed = time.monotonic() - started
        return parsed, usage, user_text, elapsed

    def _generate_voice_response(
        self,
        transcript: str,
        observation: ScreenObservation,
        game_id: str,
        coach_prompt: str,
        cycle: int,
        scene: str,
        *,
        screen_context_note: str = "",
    ) -> tuple[ParsedCoachResponse, UsageCost | None, str, float]:
        user_text = self._build_voice_user_message(
            transcript,
            observation,
            cycle,
            scene=scene,
            screen_context_note=screen_context_note,
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._coach_system_prompt(coach_prompt)},
            {"role": "user", "content": user_text},
        ]
        started = time.monotonic()
        response = self._client.chat.completions.create(
            model=self._response_model,
            messages=messages,
            temperature=self._temperature,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raw = "SCENE: unknown\nSEARCH_QUERY: NONE\nSAY: Give me a sec, my brain lagged."
        parsed = parse_coach_response(raw)
        usage = None
        if response.usage:
            usage = estimate_cost_usd(
                self._response_model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        return parsed, usage, user_text, time.monotonic() - started

    def respond_to_user(
        self,
        transcript: str,
        game_id: str,
        system_prompt: str,
        *,
        screenshot: Screenshot | None = None,
        refresh_screen: bool = False,
        vision_only: bool = False,
        prefetched_ocr_text: str | None = None,
        screen_ocr_verified: bool = False,
        scene_sync: bool = False,
        timings: CycleTimings | None = None,
    ) -> CoachAdvice:
        """Voice turn: answer USER SAID; screen read when refresh_screen=True."""
        coach_prompt = system_prompt or load_coach_prompt(game_id)
        timings = timings or CycleTimings()
        analysis_started = time.monotonic()
        transcript = transcript.strip()
        if not transcript:
            return CoachAdvice(
                text="",
                model=self._response_model,
                game_id=game_id,
                skip=True,
                trigger="voice",
                timings=timings,
            )

        self._cycle += 1
        cycle = self._cycle

        describe_usage: UsageCost | None = None
        screen_context_note = ""

        ocr_preview = ""
        if refresh_screen and screenshot is not None:
            observation, describe_usage, ocr_preview = self._observe_screen(
                screenshot,
                game_id,
                timings,
                transcript=transcript,
                force_vision=vision_only,
                prefetched_ocr_text=prefetched_ocr_text,
                scene_sync=scene_sync,
            )
            method = timings.screen_read_method
            screen_context_note = (
                f"Fresh screenshot for this voice reply ({method} screen read)."
            )
            logger.info("Voice turn: fresh screen read (%s)", method)
        elif screen_ocr_verified and self._cached_observation:
            if voice_needs_screen_context(transcript):
                observation = self._cached_observation
                screen_context_note = (
                    "OCR on this capture matched the cached screen — no new read."
                )
                timings.extra.append("screen read: skipped (OCR verified unchanged)")
                logger.info(
                    "Voice turn: OCR verified unchanged — using cached screen context"
                )
            else:
                observation = ScreenObservation(
                    screen_type="unknown",
                    description=(
                        "Casual voice line — OCR confirmed the screen has not changed "
                        "since the last read. Do not invent HUD details; answer from "
                        "what the player said."
                    ),
                    raw="",
                )
                screen_context_note = (
                    "Casual chat — OCR verified unchanged; prior gameplay HUD not attached."
                )
                timings.extra.append("screen read: skipped (casual, OCR unchanged)")
                logger.info(
                    "Voice turn: OCR verified unchanged — no HUD context for casual line"
                )
        else:
            observation = ScreenObservation(
                screen_type="unknown",
                description=(
                    "No screen snapshot available yet. The player has not asked for a "
                    "screen read this turn. Answer from voice chat context; if they need "
                    "what is on screen, they should ask explicitly."
                ),
                raw="",
            )
            screen_context_note = "No screen data cached — answer without inventing HUD details."
            timings.extra.append("vision: none cached")
            logger.info("Voice turn: no screen cache")

        self._cache_observation(observation)
        scene = self._scene_from_observation(observation)
        self._last_scene = scene

        coach_started = time.monotonic()
        parsed, response_usage, user_text, _ = self._generate_voice_response(
            transcript,
            observation,
            game_id,
            coach_prompt,
            cycle,
            scene,
            screen_context_note=screen_context_note,
        )
        scene = parsed.scene if parsed.scene != "unknown" else scene
        self._last_scene = scene

        parsed, response_usage, user_text, retry_calls, _ = (
            self._ensure_speakable_response(
                observation,
                game_id,
                coach_prompt,
                cycle,
                scene,
                parsed,
                response_usage,
                user_text,
                voice_transcript=transcript,
            )
        )
        timings.coach_api_calls = 1 + retry_calls
        timings.coach_s = time.monotonic() - coach_started

        spoken = clean_spoken_output(parsed.spoken)
        usage = _merge_usage(describe_usage, response_usage)

        if not spoken or is_silent_reply(spoken):
            spoken = (
                f"Yeah — about that: {transcript[:80]}… "
                "give me a beat, I'm still watching your screen."
            )

        self._consecutive_silences = 0
        self._record_spoken(spoken)
        self._last_observation_text = observation.description.strip()
        timings.analysis_s = time.monotonic() - analysis_started

        logger.info("Voice reply for: %r", transcript[:80])

        return CoachAdvice(
            text=spoken,
            model=self._response_model,
            game_id=game_id,
            scene=scene,
            skip=False,
            screen_description=observation.description,
            ocr_preview=ocr_preview,
            usage=usage,
            describe_usage=describe_usage,
            response_usage=response_usage,
            map_intel_notes=self._map_intel.notes if self._map_intel else "",
            map_intel_name=self._map_intel.map_name if self._map_intel else "",
            timings=timings,
            trigger="voice",
            user_said=transcript,
        )

    def analyze(
        self,
        screenshot: Screenshot,
        game_id: str,
        system_prompt: str,
        *,
        timings: CycleTimings | None = None,
    ) -> CoachAdvice:
        coach_prompt = system_prompt or load_coach_prompt(game_id)
        timings = timings or CycleTimings()
        analysis_started = time.monotonic()

        self._cycle += 1
        cycle = self._cycle

        observation, describe_usage, _ocr_preview = self._observe_screen(
            screenshot, game_id, timings, force_vision=True
        )
        scene = self._scene_from_observation(observation)
        self._last_scene = scene

        map_name = self._resolve_map_name(observation)
        if map_name:
            self._maybe_clear_stale_intel(map_name)

        web_usage: WebSearchUsage | None = None
        if self._needs_map_research(observation):
            self._prefetch_map_intel_background(observation, game_id, timings)
        elif self._map_intel:
            timings.map_intel_note = f"using cached intel ({self._map_intel.map_name})"

        coach_started = time.monotonic()
        parsed, response_usage, user_text, _call_s = self._generate_response(
            observation, game_id, coach_prompt, cycle, scene=scene
        )
        # Prefer observation scene; coach may refine SCENE line
        scene = parsed.scene if parsed.scene != "unknown" else scene
        self._last_scene = scene

        parsed, response_usage, user_text, retry_calls, _retry_s = (
            self._ensure_speakable_response(
                observation,
                game_id,
                coach_prompt,
                cycle,
                scene,
                parsed,
                response_usage,
                user_text,
            )
        )
        timings.coach_api_calls = 1 + retry_calls
        timings.coach_s = time.monotonic() - coach_started
        scene = parsed.scene if parsed.scene != "unknown" else scene
        spoken = parsed.spoken
        requires_speech = scene_requires_speech(scene, observation.screen_type)
        usage = _usage_with_web(
            _merge_usage(describe_usage, response_usage), web_usage
        )

        if parsed.skip and not requires_speech:
            self._consecutive_silences += 1
            logger.info(
                "Screen: %s — staying quiet (%s silences in a row)",
                scene,
                self._consecutive_silences,
            )
            self._last_observation_text = observation.description.strip()
            self._cache_observation(observation)
            timings.analysis_s = time.monotonic() - analysis_started
            return CoachAdvice(
                text="",
                model=self._response_model,
                game_id=game_id,
                scene=scene,
                skip=True,
                screen_description=observation.description,
                usage=usage,
                describe_usage=describe_usage,
                response_usage=response_usage,
                timings=timings,
            )

        self._consecutive_silences = 0

        if self._should_general_web(observation) and self._web:
            query = observation.search_query or f"{game_id} {scene}"
            try:
                web_started = time.monotonic()
                spoken, augment_usage = self._web.augment(
                    game_id=game_id,
                    scene=scene,
                    search_query=query,
                    vision_say=spoken,
                    temperature=self._temperature,
                )
                timings.web_augment_s = time.monotonic() - web_started
                web_usage = augment_usage
                usage = _usage_with_web(usage, web_usage)
            except Exception:
                logger.exception("Web search failed")
        elif self._is_gameplay(scene) and self._map_intel:
            logger.debug("Gameplay with cached map intel: %s", self._map_intel.map_name)

        spoken = clean_spoken_output(spoken)
        if (not spoken or is_silent_reply(spoken)) and requires_speech:
            spoken = gameplay_fallback_line(observation)
            logger.info("Post-web gameplay fallback line")
        elif not spoken or is_silent_reply(spoken):
            self._consecutive_silences += 1
            logger.info("Screen: %s — staying quiet after retries", scene)
            self._last_observation_text = observation.description.strip()
            self._cache_observation(observation)
            timings.analysis_s = time.monotonic() - analysis_started
            return CoachAdvice(
                text="",
                model=self._response_model,
                game_id=game_id,
                scene=scene,
                skip=True,
                screen_description=observation.description,
                usage=usage,
                describe_usage=describe_usage,
                response_usage=response_usage,
                web=web_usage,
                timings=timings,
            )

        self._consecutive_silences = 0
        logger.info("Screen: %s%s", scene, " +web" if web_usage else "")

        self._record_spoken(spoken)
        self._last_observation_text = observation.description.strip()
        self._cache_observation(observation)
        timings.analysis_s = time.monotonic() - analysis_started

        return CoachAdvice(
            text=spoken,
            model=self._response_model,
            game_id=game_id,
            scene=scene,
            skip=False,
            screen_description=observation.description,
            usage=usage,
            describe_usage=describe_usage,
            response_usage=response_usage,
            web=web_usage,
            map_intel_notes=self._map_intel.notes if self._map_intel else "",
            map_intel_name=self._map_intel.map_name if self._map_intel else "",
            timings=timings,
            trigger="screen",
        )
