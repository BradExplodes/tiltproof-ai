"""
Structured event vocabulary for the engine.

The CLI prints to stdout; the desktop app instead consumes these JSON-serializable
event dicts over a WebSocket. Both the `CoachRunner` (producer) and the local
`service` (transport) speak this vocabulary so the UI has a stable contract.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aicoach.capture import Screenshot
    from aicoach.coach import CoachAdvice

# Event type constants (also the `type` field on every event dict).
STATUS = "status"
TRANSCRIPT = "transcript"
ADVICE = "advice"
COST = "cost"
ERROR = "error"
SESSION = "session"
CONFIG = "config"

# Coarse lifecycle states for the `status` event.
STATE_IDLE = "idle"
STATE_STARTING = "starting"
STATE_LISTENING = "listening"
STATE_CAPTURING = "capturing"
STATE_TRANSCRIBING = "transcribing"
STATE_THINKING = "thinking"
STATE_SPEAKING = "speaking"
STATE_STOPPED = "stopped"
STATE_ERROR = "error"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(event_type: str, **payload: Any) -> dict[str, Any]:
    return {"type": event_type, "ts": iso_now(), **payload}


def status_event(state: str, detail: str = "", **extra: Any) -> dict[str, Any]:
    return _envelope(STATUS, state=state, detail=detail, **extra)


def transcript_event(text: str) -> dict[str, Any]:
    return _envelope(TRANSCRIPT, text=text)


def error_event(message: str) -> dict[str, Any]:
    return _envelope(ERROR, message=message)


def session_event(running: bool, game_id: str | None) -> dict[str, Any]:
    return _envelope(SESSION, running=running, game_id=game_id)


def _serialize_usage(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    return asdict(usage)


def advice_event(advice: "CoachAdvice", screenshot: "Screenshot | None") -> dict[str, Any]:
    """The coaching line plus the supporting screen read (no cost totals here)."""
    captured_at = None
    monitor_index = None
    if screenshot is not None:
        captured_at = screenshot.captured_at.isoformat()
        monitor_index = screenshot.monitor_index
    return _envelope(
        ADVICE,
        text=advice.text,
        model=advice.model,
        game_id=advice.game_id,
        scene=advice.scene,
        skip=advice.skip,
        trigger=advice.trigger,
        screen_description=advice.screen_description,
        ocr_preview=advice.ocr_preview,
        screen_read_method=advice.timings.screen_read_method,
        map_intel_name=advice.map_intel_name,
        map_intel_notes=advice.map_intel_notes,
        user_said=advice.user_said,
        captured_at=captured_at,
        monitor_index=monitor_index,
    )


def cost_breakdown(advice: "CoachAdvice") -> dict[str, float]:
    """Per-cycle USD split, mirroring the CLI's accounting in runner._default_on_advice."""
    vision_usd = advice.usage.estimated_usd if advice.usage else 0.0
    web_usd = advice.web.estimated_usd if advice.web else 0.0
    tts_usd = advice.tts.estimated_usd if advice.tts else 0.0
    stt_usd = advice.timings.stt_usd or 0.0
    return {
        "vision_usd": vision_usd,
        "web_usd": web_usd,
        "tts_usd": tts_usd,
        "stt_usd": stt_usd,
        "cycle_usd": vision_usd + web_usd + tts_usd + stt_usd,
    }


def cost_event(
    advice: "CoachAdvice",
    *,
    session_usd: float,
    call_count: int,
) -> dict[str, Any]:
    breakdown = cost_breakdown(advice)
    return _envelope(
        COST,
        breakdown=breakdown,
        cycle_usd=breakdown["cycle_usd"],
        session_usd=session_usd,
        call_count=call_count,
        timings=asdict(advice.timings),
    )
