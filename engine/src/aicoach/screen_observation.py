from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenObservation:
    """Factual vision pass — fed into the coach text model."""

    screen_type: str
    description: str
    raw: str
    search_query: str | None = None


def parse_screen_observation(raw: str) -> ScreenObservation:
    text = raw.strip()
    screen_type = "unknown"
    search_query: str | None = None
    description = text

    type_match = re.search(
        r"^SCREEN_TYPE:\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    query_match = re.search(
        r"^SEARCH_QUERY:\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    desc_match = re.search(
        r"^DESCRIPTION:\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )

    if type_match:
        screen_type = type_match.group(1).strip().split("\n")[0]

    if query_match:
        q = query_match.group(1).strip().split("\n")[0]
        if q.upper() not in ("NONE", "N/A", "NA", "-", ""):
            search_query = q

    if desc_match:
        description = desc_match.group(1).strip()
    elif type_match:
        # Fallback: body after headers
        parts = re.split(r"^DESCRIPTION:\s*", text, flags=re.IGNORECASE | re.MULTILINE)
        if len(parts) > 1:
            description = parts[-1].strip()

    from aicoach.scene_classify import normalize_screen_type_label

    screen_type = normalize_screen_type_label(screen_type)

    return ScreenObservation(
        screen_type=screen_type,
        description=description,
        raw=text,
        search_query=search_query,
    )
