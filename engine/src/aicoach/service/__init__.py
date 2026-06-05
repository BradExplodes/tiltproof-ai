"""Local control server: exposes the coach engine to the desktop UI over WebSocket."""

from aicoach.service.app import create_app

__all__ = ["create_app"]
