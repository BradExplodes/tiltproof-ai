"""
Owns the lifecycle of a single CoachRunner on a background thread and exposes
start/stop/reconfigure to the WebSocket layer. Runtime config from the UI is
layered on top of the env-based `Settings`.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, replace
from typing import Any

from aicoach import events as ev
from aicoach.config import Settings
from aicoach.prompts import list_games
from aicoach.runner import CoachRunner
from aicoach.service.bus import EventBus

logger = logging.getLogger(__name__)

_THREAD_JOIN_TIMEOUT_S = 15.0


@dataclass
class RuntimeConfig:
    """UI-controlled settings layered over env defaults."""

    game_id: str | None = None
    monitor_index: int = 1
    interval_seconds: float | None = None
    tts_enabled: bool | None = None
    voice_input_enabled: bool | None = None
    ocr_enabled: bool | None = None
    web_search_enabled: bool | None = None
    screen_coaching_enabled: bool | None = None

    def merged(self, patch: dict[str, Any]) -> "RuntimeConfig":
        allowed = {f for f in RuntimeConfig.__dataclass_fields__}
        updates = {k: v for k, v in patch.items() if k in allowed}
        return replace(self, **updates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "monitor_index": self.monitor_index,
            "interval_seconds": self.interval_seconds,
            "tts_enabled": self.tts_enabled,
            "voice_input_enabled": self.voice_input_enabled,
            "ocr_enabled": self.ocr_enabled,
            "web_search_enabled": self.web_search_enabled,
            "screen_coaching_enabled": self.screen_coaching_enabled,
        }

    def apply_to(self, settings: Settings) -> Settings:
        changes: dict[str, Any] = {}
        if self.interval_seconds is not None:
            changes["capture_interval_seconds"] = self.interval_seconds
        if self.tts_enabled is not None:
            changes["tts_enabled"] = self.tts_enabled
        if self.voice_input_enabled is not None:
            changes["voice_input_enabled"] = self.voice_input_enabled
        if self.ocr_enabled is not None:
            changes["ocr_enabled"] = self.ocr_enabled
        if self.web_search_enabled is not None:
            changes["web_search_enabled"] = self.web_search_enabled
        if self.screen_coaching_enabled is not None:
            changes["screen_coaching_enabled"] = self.screen_coaching_enabled
        return replace(settings, **changes) if changes else settings


class CoachSession:
    """Single-session manager (one active game at a time) guarded by a lock."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._lock = threading.RLock()
        self._config = RuntimeConfig()
        self._runner: CoachRunner | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def state(self) -> dict[str, Any]:
        return {"running": self.running, "config": self._config.to_dict()}

    def emit_state(self) -> None:
        self._bus.publish(ev.session_event(self.running, self._config.game_id))
        self._bus.publish({"type": ev.CONFIG, "ts": ev.iso_now(), **self._config.to_dict()})

    def update_config(self, patch: dict[str, Any]) -> None:
        with self._lock:
            self._config = self._config.merged(patch)
            was_running = self.running
            if was_running:
                # Settings are read once at runner construction; restart to apply.
                self._stop_locked()
                self._start_locked()
            else:
                self.emit_state()

    def start(self, patch: dict[str, Any] | None = None) -> None:
        with self._lock:
            if patch:
                self._config = self._config.merged(patch)
            self._start_locked()

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()
            self.emit_state()

    # --- internals (lock held) ---

    def _start_locked(self) -> None:
        if self.running:
            logger.info("Session already running; ignoring start")
            self.emit_state()
            return

        game_id = self._config.game_id
        if not game_id:
            self._bus.publish(ev.error_event("No game selected. Pick a game before starting."))
            return
        if game_id not in list_games():
            self._bus.publish(ev.error_event(f"Unknown game '{game_id}'."))
            return

        try:
            settings = self._config.apply_to(Settings.from_env())
        except ValueError as exc:
            self._bus.publish(ev.error_event(f"Configuration error: {exc}"))
            return

        runner = CoachRunner(
            settings=settings,
            game_id=game_id,
            on_event=self._bus.publish_threadsafe,
            monitor_index=self._config.monitor_index,
        )
        thread = threading.Thread(
            target=self._run_runner,
            args=(runner,),
            name="coach-runner",
            daemon=True,
        )
        self._runner = runner
        self._thread = thread
        thread.start()
        self.emit_state()

    def _run_runner(self, runner: CoachRunner) -> None:
        try:
            runner.run()
        except Exception as exc:  # noqa: BLE001 - surface to UI, keep server alive
            logger.exception("Runner thread crashed")
            self._bus.publish_threadsafe(ev.error_event(f"Engine crashed: {exc}"))
            self._bus.publish_threadsafe(ev.status_event(ev.STATE_STOPPED))

    def _stop_locked(self) -> None:
        runner, thread = self._runner, self._thread
        self._runner = None
        self._thread = None
        if runner is None:
            return
        runner.stop()
        if thread is not None and thread.is_alive():
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_S)
            if thread.is_alive():
                logger.warning("Runner thread did not stop within %.0fs", _THREAD_JOIN_TIMEOUT_S)
