from __future__ import annotations

import re

from aicoach.screen_observation import ScreenObservation
from aicoach.web_search import MapIntel

_PROGRESS_PATTERNS = (
    r"progress[^.\n]{0,60}?(\d{1,3})\s*%",
    r"(\d{1,3})\s*%\s*(?:through|along|into|of)\s*(?:the\s*)?(?:song|map|track)",
    r"song\s+progress[^.\n]{0,40}?(\d{1,3})\s*%",
    r"progress\s+bar[^.\n]{0,50}?(\d{1,3})\s*%",
    r"~(\d{1,3})\s*%\s*(?:complete|done|in)",
)


def normalize_map_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def extract_song_progress_percent(description: str) -> int | None:
    for pattern in _PROGRESS_PATTERNS:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 100:
                return value
    return None


def extract_map_title_from_description(description: str) -> str | None:
    """Best-effort map title from vision text when SEARCH_QUERY is missing."""
    patterns = (
        r"(?:map|song|beatmap|title)[:\s]+([^\n]{3,80})",
        r"(?:playing|selected)[:\s]+([^\n]{3,80})",
        r"^([A-Za-z0-9].+?\s+-\s+.+?)(?:\n|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE | re.MULTILINE)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 5 and "screen" not in candidate.lower():
                return candidate[:120]
    return None


def format_map_intel_for_coach(
    intel: MapIntel,
    observation: ScreenObservation,
    *,
    is_gameplay: bool,
) -> str:
    progress = extract_song_progress_percent(observation.description)
    progress_hint = (
        f"~{progress}% through the song (from observation)"
        if progress is not None
        else "estimate % from song progress bar in observation (left=0%, right=100%)"
    )

    header = (
        f'MAP INTEL — "{intel.map_name}" (community / beatmap research; use real section names):\n'
        f"{intel.notes.strip()}\n"
    )

    if not is_gameplay:
        return (
            header
            + "\nOn map select: mention 1–2 specific hard sections from intel (with % or pattern type), "
            "not vague difficulty talk."
        )

    return (
        header
        + f"\nSong position: {progress_hint}.\n"
        "GAMEPLAY — HARD PARTS ARE TOP PRIORITY:\n"
        "1. Match progress % to SECTION / PEAK / FIRST_SPIKE lines in MAP INTEL above.\n"
        "2. Within ~20% before a listed section: warn with pattern type (stream/jump/burst/tech) "
        "and approximate % — e.g. '55% stream choke coming, stop panicking'.\n"
        "3. Inside a section (progress overlaps + dense notes in observation): coach that pattern live.\n"
        "4. At least one sentence MUST reference MAP INTEL or visible stream/jump density — "
        "no generic 'play better' without naming what's coming.\n"
        "5. If between sections, say what's next per intel, not random banter only."
    )
