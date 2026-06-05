"""Run the local engine server: `python -m aicoach.service [--port 8765]`."""

from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from aicoach.perf import configure_file_logging
from aicoach.service.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Coach local engine server (WebSocket API).")
    parser.add_argument("--host", default=os.getenv("AICOACH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AICOACH_PORT", "8765")))
    parser.add_argument(
        "--token",
        default=os.getenv("AICOACH_TOKEN"),
        help="Optional shared secret required as ?token= on the WebSocket.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    configure_file_logging()
    app = create_app(token=args.token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
