"""
FastAPI app exposing the coach engine to the local desktop UI.

- `GET /health`   - liveness + whether a session is running
- `GET /games`    - supported game ids
- `GET /monitors` - capture monitor indices
- `WS  /ws`       - bidirectional: streams engine events; accepts control messages

Bound to 127.0.0.1 only. If `AICOACH_TOKEN` is set, the WebSocket requires a
matching `?token=` query param so other local processes can't drive the engine.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from aicoach import events as ev
from aicoach.capture import list_monitors
from aicoach.config import Settings
from aicoach.elevenlabs_client import ElevenLabsError
from aicoach.elevenlabs_client import list_voices as fetch_elevenlabs_voices
from aicoach.memory import default_memory
from aicoach.prompts import list_games
from aicoach.tts import PREVIEW_SAMPLE_TEXT, synthesize_preview_audio
from aicoach.service.bus import EventBus
from aicoach.service.session import CoachSession

logger = logging.getLogger(__name__)


def create_app(token: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        bus = EventBus(loop)
        session = CoachSession(bus)
        app.state.bus = bus
        app.state.session = session
        # Seed snapshot so first client sees a coherent initial state.
        session.emit_state()
        bus.publish(ev.status_event(ev.STATE_IDLE))
        try:
            yield
        finally:
            session.stop()

    app = FastAPI(title="AI Coach Engine", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "running": app.state.session.running}

    @app.get("/games")
    async def games() -> dict[str, Any]:
        return {"games": list_games()}

    @app.get("/monitors")
    async def monitors() -> dict[str, Any]:
        return {"monitors": list_monitors()}

    @app.get("/state")
    async def state() -> dict[str, Any]:
        return app.state.session.state()

    @app.get("/memory")
    async def get_memory() -> dict[str, Any]:
        return {"entries": default_memory().entries()}

    @app.delete("/memory")
    async def clear_memory() -> dict[str, Any]:
        default_memory().clear()
        return {"ok": True, "entries": []}

    @app.get("/voices")
    async def voices() -> dict[str, Any]:
        try:
            return {"voices": fetch_elevenlabs_voices()}
        except ElevenLabsError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/tts/preview")
    async def tts_preview(body: dict[str, Any]) -> Response:
        voice_id = (body.get("voice_id") or "").strip()
        if not voice_id:
            raise HTTPException(status_code=400, detail="voice_id is required")
        try:
            settings = Settings.from_env()
            text = (body.get("text") or PREVIEW_SAMPLE_TEXT).strip()
            audio, media_type = synthesize_preview_audio(
                voice_id=voice_id,
                model_id=settings.elevenlabs_model,
                text=text,
                output_format=settings.elevenlabs_output_format,
            )
        except ElevenLabsError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=audio, media_type=media_type)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, token_q: str | None = Query(default=None, alias="token")):
        if token and token_q != token:
            await websocket.close(code=1008)
            return
        await _handle_ws(websocket, app.state.bus, app.state.session)

    return app


async def _handle_ws(websocket: WebSocket, bus: EventBus, session: CoachSession) -> None:
    await websocket.accept()
    queue = bus.subscribe()

    async def forward() -> None:
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    # Replay current state to the freshly connected client.
    for event in bus.snapshot():
        await websocket.send_json(event)

    sender = asyncio.create_task(forward())
    try:
        while True:
            message = await websocket.receive_json()
            _handle_control(message, bus, session)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        sender.cancel()
        bus.unsubscribe(queue)


def _handle_control(message: dict[str, Any], bus: EventBus, session: CoachSession) -> None:
    action = message.get("action")
    config = message.get("config") or {}
    try:
        if action == "start":
            session.start(config or None)
        elif action == "stop":
            session.stop()
        elif action == "update_config":
            session.update_config(config)
        elif action == "set_game":
            session.update_config({"game_id": message.get("game_id")})
        elif action == "get_state":
            session.emit_state()
        else:
            bus.publish(ev.error_event(f"Unknown action: {action!r}"))
    except Exception as exc:  # noqa: BLE001 - report instead of dropping the socket
        logger.exception("Control action failed")
        bus.publish(ev.error_event(f"Action '{action}' failed: {exc}"))
