from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace

from aicoach.capture import list_monitors
from aicoach.config import Settings
from aicoach.prompts import list_games
from aicoach.runner import CoachRunner, install_signal_handlers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI Coach — periodic desktop screenshots analyzed for gaming tips.",
    )
    parser.add_argument(
        "--game",
        "-g",
        choices=list_games(),
        help="Game profile (selects the coaching prompt).",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=None,
        help="Seconds between captures (overrides CAPTURE_INTERVAL_SECONDS).",
    )
    parser.add_argument(
        "--monitor",
        "-m",
        type=int,
        default=1,
        help="Monitor index for mss (1 = primary; 0 = all monitors combined).",
    )
    parser.add_argument(
        "--save-screenshots",
        action="store_true",
        help="Write each capture to the screenshots/ folder.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List supported game profiles and exit.",
    )
    parser.add_argument(
        "--list-monitors",
        action="store_true",
        help="List mss monitor indices (1 = primary) and exit.",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Disable spoken coaching (overrides TTS_ENABLED).",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable web search (overrides WEB_SEARCH_ENABLED).",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Disable microphone / voice replies (overrides VOICE_INPUT_ENABLED).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_games:
        for game in list_games():
            print(game)
        return 0

    if args.list_monitors:
        print("mss monitor indices (use --monitor / -m):")
        for mon in list_monitors():
            print(
                f"  {mon['index']}: {mon['label']} — "
                f"{mon['width']}x{mon['height']} at ({mon['left']}, {mon['top']})"
            )
        print("Default is 1 (primary). Use 0 only if you want all monitors in one image.")
        return 0

    if not args.game:
        parser.error("--game/-g is required unless using --list-games")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    if args.interval is not None:
        settings = replace(settings, capture_interval_seconds=args.interval)

    if args.save_screenshots:
        settings = replace(settings, save_screenshots=True)

    if args.no_tts:
        settings = replace(settings, tts_enabled=False)

    if args.no_web:
        settings = replace(settings, web_search_enabled=False)

    if args.no_voice:
        settings = replace(settings, voice_input_enabled=False)

    runner = CoachRunner(
        settings=settings,
        game_id=args.game,
        monitor_index=args.monitor,
    )
    install_signal_handlers(runner)

    try:
        runner.run()
    except KeyboardInterrupt:
        runner.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
