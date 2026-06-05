"""
Single place that constructs OpenAI clients.

By default the engine talks to OpenAI directly with the user's key. When the
desktop app runs the engine as a sidecar, it points the engine at the backend
proxy by setting two environment variables:

- ``AICOACH_OPENAI_BASE_URL`` - the proxy base URL (e.g. https://api.example.com/openai)
- ``AICOACH_PROXY_TOKEN``     - the signed-in user's session token

In proxy mode the session token is sent as the Bearer credential and the real
OpenAI key never leaves the backend. All engine modules build their clients
through :func:`build_openai_client` so this routing is decided in exactly one place.
"""

from __future__ import annotations

import os

from openai import OpenAI

ENV_BASE_URL = "AICOACH_OPENAI_BASE_URL"
ENV_PROXY_TOKEN = "AICOACH_PROXY_TOKEN"


def proxy_base_url() -> str | None:
    return os.getenv(ENV_BASE_URL, "").strip() or None


def build_openai_client(api_key: str) -> OpenAI:
    """Direct-to-OpenAI by default; routed through the backend proxy when configured."""
    base_url = proxy_base_url()
    if base_url:
        token = os.getenv(ENV_PROXY_TOKEN, "").strip() or api_key
        return OpenAI(api_key=token, base_url=base_url)
    return OpenAI(api_key=api_key)
