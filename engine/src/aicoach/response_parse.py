from __future__ import annotations

import re
from dataclasses import dataclass

_STRUCTURAL_TAGS = ("SCENE", "SAY", "MAP_INTEL", "SEARCH_QUERY")

_SILENT_SAY = frozenset(
    {
        "none",
        "skip",
        "n/a",
        "na",
        "-",
        "...",
        "(silence)",
        "silence",
        "nothing",
        "no comment",
        "nothing to add",
        "no comment.",
    }
)


@dataclass(frozen=True)
class ParsedCoachResponse:
    scene: str
    spoken: str
    raw: str
    search_query: str | None = None
    skip: bool = False
    map_intel: str | None = None


def is_silent_reply(spoken: str) -> bool:
    """True when the model chose not to say anything aloud."""
    normalized = spoken.strip().lower().rstrip(".")
    if not normalized:
        return True
    if normalized in _SILENT_SAY:
        return True
    if normalized.startswith("none") and len(normalized) <= 24:
        return True
    return False


def normalize_response_text(text: str) -> str:
    """Turn inline **TAG:** blobs into line-based tags for parsing."""
    normalized = text.strip()
    for tag in _STRUCTURAL_TAGS:
        normalized = re.sub(
            rf"\*\*{tag}\*\*\s*:",
            f"\n{tag}:",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\*\*{tag}\s*:",
            f"\n{tag}:",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized


def extract_map_intel(text: str) -> str | None:
    normalized = normalize_response_text(text)
    match = re.search(
        r"(?:^|\n)MAP_INTEL:\s*(.+?)(?=\n(?:SCENE|SAY|SEARCH_QUERY):|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r"MAP_INTEL:\s*(.+?)(?=(?:SCENE|SAY|SEARCH_QUERY):|$)",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return None
    intel = match.group(1).strip()
    if intel.upper() in ("NONE", "N/A", ""):
        return None
    return intel


def extract_scene(text: str) -> str:
    normalized = normalize_response_text(text)
    match = re.search(
        r"(?:^|\n)SCENE:\s*(.+?)(?=\n(?:SAY|MAP_INTEL|SEARCH_QUERY):|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r"SCENE:\s*(.+?)(?=(?:SAY|MAP_INTEL|SEARCH_QUERY):|$)",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if match:
        return match.group(1).strip().split("\n")[0].strip()
    return "unknown"


def extract_search_query(text: str) -> str | None:
    normalized = normalize_response_text(text)
    match = re.search(
        r"(?:^|\n)SEARCH_QUERY:\s*(.+?)(?=\n(?:SCENE|SAY|MAP_INTEL):|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    q = match.group(1).strip().split("\n")[0].strip()
    if q.upper() in ("NONE", "N/A", "NA", "-", ""):
        return None
    return q


def extract_say_only(text: str) -> str:
    """
    Pull only the spoken line from model output.
    Handles inline **SAY:** tags and research blobs before/after.
    """
    normalized = normalize_response_text(text)

    match = re.search(
        r"(?:^|\n)SAY:\s*(.+)$",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r"SAY:\s*(.+)$",
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )

    if not match:
        return ""

    say = match.group(1).strip()
    say = re.split(r"\n(?:MAP_INTEL|SCENE|SEARCH_QUERY):", say, flags=re.IGNORECASE)[0]
    say = re.sub(r"\(https?://[^)]+\)", "", say)
    say = re.sub(r"https?://\S+", "", say)
    say = re.sub(r"\*\*", "", say)
    say = say.strip().strip('"').strip("'")
    return clean_spoken_output(say)


def clean_spoken_output(text: str) -> str:
    """Remove bracketed metadata the model must not speak aloud."""
    cleaned = text.strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
    for tag in _STRUCTURAL_TAGS:
        cleaned = re.sub(rf"{tag}:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_like_unparsed_blob(spoken: str, raw: str) -> bool:
    if not spoken:
        return True
    if spoken == raw.strip():
        return True
    lower = spoken.lower()
    return any(marker in lower for marker in ("map_intel", "scene:", "search_query:"))


def parse_coach_response(raw: str) -> ParsedCoachResponse:
    """Extract SCENE, SEARCH_QUERY, MAP_INTEL, and SAY from model output."""
    text = raw.strip()
    scene = extract_scene(text)
    search_query = extract_search_query(text)
    map_intel = extract_map_intel(text)
    spoken = extract_say_only(text)

    if _looks_like_unparsed_blob(spoken, text):
        spoken = ""

    spoken = clean_spoken_output(spoken)
    skip = is_silent_reply(spoken)
    if skip:
        spoken = ""

    return ParsedCoachResponse(
        scene=scene,
        spoken=spoken,
        raw=text,
        search_query=search_query,
        skip=skip,
        map_intel=map_intel,
    )
