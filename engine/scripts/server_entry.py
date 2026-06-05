"""PyInstaller entry point for the desktop sidecar (local WebSocket engine server)."""

from aicoach.service.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
