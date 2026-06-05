from __future__ import annotations

import re

from aicoach.screen_observation import ScreenObservation

# Substrings matched against SCREEN_TYPE / SCENE (vision + coach labels).
_ACTIVE_PLAY_MARKERS = (
    "gameplay",
    "playing",
    "in_game",
    "in-game",
    "in game",
    "active play",
    "match",
    "round",
)


def scene_requires_speech(*labels: str | None) -> bool:
    """True when the user is in active play — coach must not stay silent."""
    for label in labels:
        if not label:
            continue
        lower = label.lower()
        if any(marker in lower for marker in _ACTIVE_PLAY_MARKERS):
            return True
    return False


def _extract_play_facts(description: str) -> list[str]:
    facts: list[str] = []
    patterns: list[tuple[str, str]] = [
        (r"combo[:\s]+(\d+)", "combo {0}"),
        (r"(\d+)\s*x?\s*combo", "combo {0}"),
        (r"acc(?:uracy)?[:\s]+([\d.]+%?)", "acc {0}"),
        (r"([\d.]+)\s*%\s*acc(?:uracy)?", "acc {0}%"),
        (r"progress[^.\n]{0,50}?(\d+)\s*%", "{0}% through the song"),
        (r"(\d+)\s*%\s*(?:through|along|into)\s*(?:the\s*)?(?:song|map)", "{0}% in"),
        (r"HP[^.\n]{0,30}?(\d+)\s*%", "HP around {0}%"),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            facts.append(fmt.format(match.group(1)))
    return facts


def gameplay_fallback_line(obs: ScreenObservation) -> str:
    """
    Last-resort spoken line when the text model keeps returning NONE during play.
    Built from the vision description so it still references the screen.
    """
    facts = _extract_play_facts(obs.description)
    seed = hash(obs.description[:200] + obs.screen_type)

    if facts:
        detail = ", ".join(facts[:3])
        lines = (
            f"Still watching — {detail}. Read what's coming, don't sleep on the streams.",
            f"{detail} on screen. Snap to the rhythm before you throw combo.",
            f"You're at {detail}. Eyes ahead of the cursor, something's about to spike.",
        )
        return lines[seed % len(lines)]

    generic = (
        "You're in the map — stop staring at the scoreboard and read the approach circles.",
        "Keep your aim smooth, the patterns are moving and you look half asleep.",
        "Tap clean — if you autopilot this section you're gonna eat a miss.",
    )
    return generic[seed % len(generic)]
