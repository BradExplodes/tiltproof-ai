"""
OpenAI Realtime API transcription (live captions + final transcript).

Ephemeral tokens are minted through the backend proxy (quota gate); audio streams
directly to OpenAI over WebSocket. Falls back to batch Whisper when unavailable.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aicoach.openai_client import proxy_base_url
from aicoach.pricing import estimate_stt_cost_usd
from aicoach.voice.audio import REALTIME_SAMPLE_RATE, SAMPLE_RATE, resample_pcm16

logger = logging.getLogger(__name__)

REALTIME_WS_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
INTERIM_COMMIT_BLOCKS = 15  # ~450ms at 30ms blocks — rolling partials while speaking
FINAL_WAIT_S = 6.0


def _mint_ephemeral_token(session_token: str, model: str) -> str | None:
    base = proxy_base_url()
    if not base:
        logger.warning("Realtime STT requires proxy mode (AICOACH_OPENAI_BASE_URL)")
        return None
    url = f"{base.rstrip('/')}/v1/realtime/client_secrets"
    body = json.dumps(
        {
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": REALTIME_SAMPLE_RATE},
                        "transcription": {"model": model, "language": "en"},
                        "turn_detection": None,
                    }
                },
            }
        }
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {session_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Failed to mint realtime ephemeral token: %s", exc)
        return None
    secret = payload.get("value") or (payload.get("client_secret") or {}).get("value")
    if not secret:
        logger.warning("Realtime client_secrets response missing value")
        return None
    return str(secret)


class RealtimeTranscriber:
    """
    Streams mic PCM to OpenAI Realtime transcription; emits partial/final callbacks.

    Thread-safe for append() from the capture thread; WebSocket I/O runs on a daemon thread.
    """

    def __init__(
        self,
        *,
        session_token: str,
        model: str = "gpt-4o-mini-transcribe",
        on_partial: Callable[[str, str], None] | None = None,
        on_final: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self._session_token = session_token
        self._model = model
        self._on_partial = on_partial
        self._on_final = on_final

        self._available = False
        self._stop = threading.Event()
        self._ws_thread: threading.Thread | None = None
        self._ws_app: Any = None
        self._send_lock = threading.Lock()
        self._connected = threading.Event()

        self._utterance_id: str | None = None
        self._utterance_started = 0.0
        self._blocks_since_commit = 0
        self._latest_partial = ""
        self._segment_texts: list[str] = []
        self._pending_final = threading.Event()
        self._final_transcript = ""
        self._final_seconds = 0.0

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> None:
        if self._ws_thread and self._ws_thread.is_alive():
            return
        token = _mint_ephemeral_token(self._session_token, self._model)
        if not token:
            self._available = False
            return
        self._ephemeral_token = token
        self._stop.clear()
        self._connected.clear()
        self._ws_thread = threading.Thread(
            target=self._run_ws,
            name="realtime-stt",
            daemon=True,
        )
        self._ws_thread.start()
        if not self._connected.wait(timeout=12.0):
            logger.warning("Realtime STT WebSocket did not connect in time")
            self._available = False
            self.stop()
            return
        self._available = True
        logger.info("Realtime STT connected (model=%s)", self._model)

    def stop(self) -> None:
        self._stop.set()
        self._available = False
        try:
            if self._ws_app is not None:
                self._ws_app.close()
        except Exception:
            pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2.0)
        self._ws_thread = None
        self._ws_app = None

    def begin_utterance(self) -> str:
        """Start a new logical utterance; returns a stable id for UI correlation."""
        utterance_id = uuid.uuid4().hex
        with self._send_lock:
            self._utterance_id = utterance_id
            self._utterance_started = time.monotonic()
            self._blocks_since_commit = 0
            self._latest_partial = ""
            self._segment_texts = []
            self._pending_final.clear()
            self._final_transcript = ""
            self._final_seconds = 0.0
        return utterance_id

    def append(self, pcm_16k: bytes) -> None:
        if not self._available or not pcm_16k:
            return
        pcm_24k = resample_pcm16(pcm_16k, SAMPLE_RATE, REALTIME_SAMPLE_RATE)
        audio_b64 = base64.b64encode(pcm_24k).decode("ascii")
        self._send({"type": "input_audio_buffer.append", "audio": audio_b64})
        with self._send_lock:
            self._blocks_since_commit += 1
            if self._blocks_since_commit >= INTERIM_COMMIT_BLOCKS:
                self._blocks_since_commit = 0
                self._commit_buffer_locked(interim=True)

    def interim_commit(self) -> None:
        if not self._available:
            return
        with self._send_lock:
            self._commit_buffer_locked(interim=True)

    def finish_utterance(self, *, audio_duration_s: float) -> tuple[str, float] | None:
        """Commit remaining audio and wait for the final transcript."""
        if not self._available:
            return None
        with self._send_lock:
            self._commit_buffer_locked(interim=False)
            utterance_id = self._utterance_id
        if not utterance_id:
            return None
        if not self._pending_final.wait(timeout=FINAL_WAIT_S):
            logger.warning("Realtime STT final transcript timed out")
            text = self._combined_transcript()
            if len(text) < 2:
                return None
            return text, audio_duration_s
        with self._send_lock:
            text = self._final_transcript or self._combined_transcript()
            seconds = self._final_seconds or audio_duration_s
            cost = estimate_stt_cost_usd(self._model, seconds)
            logger.info(
                "Realtime STT final: %.1fs audio, ~$%.4f — %r",
                seconds,
                cost,
                text[:120],
            )
            if self._on_final:
                try:
                    self._on_final(text, utterance_id, seconds)
                except Exception:
                    logger.exception("on_final callback failed")
            return text, seconds

    def _combined_transcript(self) -> str:
        parts = [t.strip() for t in self._segment_texts if t.strip()]
        if self._latest_partial.strip():
            parts.append(self._latest_partial.strip())
        return " ".join(parts).strip()

    def _commit_buffer_locked(self, *, interim: bool) -> None:
        self._send({"type": "input_audio_buffer.commit"})
        if not interim:
            self._pending_final.clear()

    def _send(self, event: dict[str, Any]) -> None:
        if self._ws_app is None:
            return
        try:
            self._ws_app.send(json.dumps(event))
        except Exception:
            logger.exception("Realtime STT send failed")
            self._available = False

    def _run_ws(self) -> None:
        import websocket

        headers = [
            f"Authorization: Bearer {self._ephemeral_token}",
            "OpenAI-Beta: realtime=v1",
        ]

        def on_open(ws: Any) -> None:
            self._ws_app = ws
            ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {
                                        "type": "audio/pcm",
                                        "rate": REALTIME_SAMPLE_RATE,
                                    },
                                    "transcription": {
                                        "model": self._model,
                                        "language": "en",
                                    },
                                    "turn_detection": None,
                                }
                            },
                        },
                    }
                )
            )
            self._connected.set()

        def on_message(_ws: Any, message: str) -> None:
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                return
            self._handle_event(event)

        def on_error(_ws: Any, error: Any) -> None:
            logger.warning("Realtime STT WebSocket error: %s", error)
            self._available = False

        def on_close(_ws: Any, _code: Any, _msg: Any) -> None:
            self._available = False
            self._connected.clear()

        self._ws_app = websocket.WebSocketApp(
            REALTIME_WS_URL,
            header=headers,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        while not self._stop.is_set():
            try:
                self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                logger.exception("Realtime STT run_forever crashed")
            if self._stop.is_set():
                break
            time.sleep(0.5)

    def _handle_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type", "")
        if etype == "error":
            logger.warning("Realtime STT server error: %s", event.get("error", event))
            return

        utterance_id = self._utterance_id
        if not utterance_id:
            return

        if etype == "conversation.item.input_audio_transcription.delta":
            delta = (event.get("delta") or "").strip()
            if not delta:
                return
            with self._send_lock:
                self._latest_partial += delta
                text = self._combined_transcript()
            if self._on_partial:
                try:
                    self._on_partial(text, utterance_id)
                except Exception:
                    logger.exception("on_partial callback failed")
            return

        if etype == "conversation.item.input_audio_transcription.completed":
            transcript = (event.get("transcript") or "").strip()
            with self._send_lock:
                if transcript:
                    self._segment_texts.append(transcript)
                self._latest_partial = ""
                combined = self._combined_transcript()
                self._final_transcript = combined
                if self._utterance_started > 0:
                    self._final_seconds = time.monotonic() - self._utterance_started
                self._pending_final.set()
            if self._on_partial and combined:
                try:
                    self._on_partial(combined, utterance_id)
                except Exception:
                    logger.exception("on_partial callback failed")
            return

        if etype == "input_audio_buffer.committed":
            # Segment committed; keep listening for transcription on this item.
            return

        if etype == "session.updated":
            return
