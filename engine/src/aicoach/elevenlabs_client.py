"""
ElevenLabs HTTP client.

Direct mode uses ``ELEVENLABS_API_KEY``. In proxy mode the desktop app sets
``AICOACH_ELEVENLABS_BASE_URL`` and ``AICOACH_PROXY_TOKEN`` (session token).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ENV_BASE_URL = "AICOACH_ELEVENLABS_BASE_URL"
ENV_API_KEY = "ELEVENLABS_API_KEY"
ENV_PROXY_TOKEN = "AICOACH_PROXY_TOKEN"

DEFAULT_BASE_URL = "https://api.elevenlabs.io/v1"
USER_AGENT = "TiltproofAI-Engine/0.2.2 (+https://tiltproof.net)"
# Free/starter tiers do not include raw PCM; MP3 44.1 kHz @ 128kbps works on all plans.
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

_FORMAT_ACCEPT: dict[str, str] = {
    "mp3_44100_128": "audio/mpeg",
    "mp3_44100_192": "audio/mpeg",
    "pcm_44100": "audio/pcm",
}


class ElevenLabsError(RuntimeError):
    pass


def proxy_base_url() -> str | None:
    return os.getenv(ENV_BASE_URL, "").strip() or None


def api_key() -> str:
    key = os.getenv(ENV_API_KEY, "").strip()
    if key:
        return key
    if proxy_base_url():
        return os.getenv(ENV_PROXY_TOKEN, "").strip()
    return ""


def base_url() -> str:
    custom = proxy_base_url()
    if custom:
        return custom.rstrip("/")
    return DEFAULT_BASE_URL


def configured() -> bool:
    return bool(api_key())


def _format_http_error(code: int, detail: str) -> str:
    try:
        payload = json.loads(detail)
        if isinstance(payload, dict):
            inner = payload.get("detail", detail)
            if isinstance(inner, dict):
                msg = inner.get("message") or inner.get("status") or str(inner)
                return f"ElevenLabs HTTP {code}: {msg}"
            if isinstance(inner, str):
                try:
                    nested = json.loads(inner)
                    errors = nested.get("errors") if isinstance(nested, dict) else None
                    if errors and isinstance(errors, list) and errors:
                        err = errors[0]
                        title = err.get("title", "")
                        msg = err.get("detail", "")
                        return f"ElevenLabs HTTP {code}: {title}. {msg}".strip()
                except json.JSONDecodeError:
                    pass
                if len(inner) > 240:
                    inner = inner[:240] + "…"
                return f"ElevenLabs HTTP {code}: {inner}"
    except json.JSONDecodeError:
        pass
    if len(detail) > 240:
        detail = detail[:240] + "…"
    return f"ElevenLabs HTTP {code}: {detail}"


def request(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    accept: str = "application/json",
) -> bytes:
    key = api_key()
    if not key:
        raise ElevenLabsError(
            "ElevenLabs is not configured. Sign in to the app or set ELEVENLABS_API_KEY."
        )

    url = f"{base_url()}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    data = None
    headers = {
        "xi-api-key": key,
        "Accept": accept,
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ElevenLabsError(_format_http_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise ElevenLabsError(f"ElevenLabs request failed: {exc}") from exc


def list_voices() -> list[dict[str, Any]]:
    raw = request("voices")
    payload = json.loads(raw.decode("utf-8"))
    voices = payload.get("voices") or []
    return [
        {
            "voice_id": v.get("voice_id", ""),
            "name": v.get("name", ""),
            "description": (v.get("description") or "").strip(),
            "category": v.get("category", ""),
            "preview_url": v.get("preview_url"),
            "labels": v.get("labels") or {},
        }
        for v in voices
        if v.get("voice_id")
    ]


def synthesize_speech(
    text: str,
    *,
    voice_id: str,
    model_id: str,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> bytes:
    path = f"text-to-speech/{voice_id}"
    accept = _FORMAT_ACCEPT.get(output_format, "audio/mpeg")
    return request(
        path,
        method="POST",
        body={"text": text, "model_id": model_id},
        query={"output_format": output_format},
        accept=accept,
    )
