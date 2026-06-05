"""
Best-effort usage reporting back to the Tiltproof backend (proxy mode only).
"""

from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aicoach.openai_client import ENV_PROXY_TOKEN, proxy_base_url

logger = logging.getLogger(__name__)


def _backend_root() -> str | None:
    base = proxy_base_url()
    if not base:
        return None
    # Proxy base is e.g. https://api.tiltproof.net/openai
    return base.rstrip("/").removesuffix("/openai")


def report_stt_usage(*, seconds: float, model: str) -> None:
    """Record realtime STT seconds against the signed-in user's monthly quota."""
    root = _backend_root()
    token = os.getenv(ENV_PROXY_TOKEN, "").strip()
    if not root or not token:
        return
    url = f"{root}/usage/report"
    body = json.dumps(
        {
            "kind": "stt-realtime",
            "model": model,
            "seconds": max(0.0, seconds),
        }
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=8) as resp:
            if resp.status >= 400:
                logger.warning("Usage report failed with status %s", resp.status)
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.debug("Usage report failed (non-fatal): %s", exc)
