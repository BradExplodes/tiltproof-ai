from __future__ import annotations

import re

from aicoach.screen_observation import ScreenObservation
from aicoach.screen_ocr import extract_search_query_from_ocr, infer_screen_type


def normalize_ocr_text(text: str) -> str:
    """Loose normalization so minor OCR jitter does not count as a scene change."""
    lowered = text.lower()
    lowered = re.sub(r"[^\w\s%#.+\-:|]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _token_set(text: str) -> set[str]:
    if not text:
        return set()
    return {t for t in text.split() if len(t) >= 2 or t.isdigit()}


# Score/combo/accuracy digits churn every frame during play — not a scene change.
_VOLATILE_HUD_RE = re.compile(
    r"\b\d{1,6}x\b|\b\d{1,3}\.\d{2}\s*%|\b\d{4,}\b|\b\d+\b",
    re.IGNORECASE,
)


def stable_ocr_text(text: str) -> str:
    """OCR text with volatile HUD numbers stripped (for gameplay drift checks)."""
    norm = normalize_ocr_text(text)
    norm = _VOLATILE_HUD_RE.sub(" ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def ocr_similarity(previous: str, current: str) -> float:
    """1.0 = identical normalized OCR; 0.0 = completely different."""
    prev = normalize_ocr_text(previous)
    curr = normalize_ocr_text(current)
    if not prev and not curr:
        return 1.0
    if not prev or not curr:
        return 0.0
    if prev == curr:
        return 1.0
    prev_tokens = _token_set(prev)
    curr_tokens = _token_set(curr)
    if not prev_tokens or not curr_tokens:
        return 0.0
    overlap = len(prev_tokens & curr_tokens)
    union = len(prev_tokens | curr_tokens)
    return overlap / union if union else 0.0


def map_content_fingerprint(ocr_text: str, game_id: str = "osu") -> str:
    """
    HUD chrome is similar across maps; fingerprint the map-specific lines.
    """
    parts: list[str] = []
    query = extract_search_query_from_ocr(ocr_text)
    if query:
        parts.append(normalize_ocr_text(query))
    for line in ocr_text.splitlines():
        line = line.strip()
        if " - " in line and 8 <= len(line) <= 120:
            parts.append(normalize_ocr_text(line))
    for match in re.findall(r"\d+(?:\.\d+)?\s*\*|\b\d+\.\d{2}\s*stars?\b", ocr_text.lower()):
        parts.append(match.replace(" ", ""))
    if game_id == "osu":
        for tag in ("bpm", "od:", "ar:", "cs:", "hp:"):
            m = re.search(rf"{tag}\s*[\d.]+", ocr_text.lower())
            if m:
                parts.append(m.group(0).replace(" ", ""))
    if parts:
        return "|".join(parts)
    return normalize_ocr_text(ocr_text)[:240]


def ocr_substantially_changed(
    previous: str,
    current: str,
    *,
    game_id: str = "osu",
    similarity_threshold: float = 0.72,
    scene_hint: str = "",
) -> tuple[bool, str]:
    """
    Returns (changed, reason).

    changed=True means the screen likely moved on — run a full screen read.
    """
    if not previous.strip():
        return True, "no prior OCR baseline"
    prev_norm = normalize_ocr_text(previous)
    curr_norm = normalize_ocr_text(current)
    if not curr_norm:
        return True, "current OCR empty"

    from aicoach.scene_classify import infer_screen_type_from_text

    in_gameplay = scene_hint == "gameplay" or (
        infer_screen_type_from_text(previous, game_id) == "gameplay"
        and infer_screen_type_from_text(current, game_id) == "gameplay"
    )
    if in_gameplay:
        prev_stable = stable_ocr_text(previous)
        curr_stable = stable_ocr_text(current)
        if prev_stable and curr_stable:
            if prev_stable == curr_stable:
                return False, "gameplay HUD drift ignored (labels unchanged)"
            stable_sim = ocr_similarity(prev_stable, curr_stable)
            if stable_sim >= 0.5:
                pct = int(stable_sim * 100)
                return False, f"gameplay HUD drift ignored ({pct}% stable)"

    prev_map = map_content_fingerprint(previous, game_id)
    curr_map = map_content_fingerprint(current, game_id)
    if prev_map and curr_map and prev_map != curr_map:
        return True, "map/song fingerprint changed"

    if prev_norm == curr_norm:
        return False, "OCR text unchanged"
    similarity = ocr_similarity(previous, current)
    if similarity < similarity_threshold:
        pct = int(similarity * 100)
        return True, f"OCR changed ({pct}% similar)"
    pct = int(similarity * 100)
    return False, f"minor OCR drift ({pct}% similar)"


def cached_observation_matches_probe(
    cached: ScreenObservation,
    probe_ocr: str,
    *,
    game_id: str = "osu",
) -> tuple[bool, str]:
    """
    False when a fresh vision/OCR read is required — cached text cannot answer
    what is on screen *right now*.
    """
    if not probe_ocr.strip():
        return True, ""
    desc_norm = normalize_ocr_text(cached.description)

    query = extract_search_query_from_ocr(probe_ocr)
    if query:
        q_norm = normalize_ocr_text(query)
        if q_norm and q_norm not in desc_norm:
            short = query if len(query) <= 50 else query[:47] + "..."
            return False, f"cache missing current map ({short})"

    for line in probe_ocr.splitlines():
        line = line.strip()
        if " - " not in line or len(line) < 10:
            continue
        line_norm = normalize_ocr_text(line)
        if line_norm and line_norm not in desc_norm:
            short = line if len(line) <= 40 else line[:37] + "..."
            return False, f"cache missing on-screen title ({short})"

    probe_map = map_content_fingerprint(probe_ocr, game_id)
    if probe_map and probe_map not in desc_norm and len(probe_map) > 12:
        return False, "cache does not match current map HUD"

    return True, ""


def ocr_scene_changed(
    cached: ScreenObservation,
    probe_ocr: str,
    *,
    game_id: str = "osu",
) -> tuple[bool, str]:
    """
    Detect gameplay -> results/failed/menu transitions OCR similarity can miss.
    """
    if not probe_ocr.strip():
        return False, ""
    prev_type = (cached.screen_type or "unknown").lower()
    curr_type = infer_screen_type(probe_ocr, game_id).lower()
    if (
        prev_type != curr_type
        and prev_type != "unknown"
        and curr_type != "unknown"
    ):
        return True, f"screen type {prev_type} -> {curr_type}"

    probe_l = probe_ocr.lower()
    desc_l = cached.description.lower()
    from aicoach.osu_results import osu_results_screen_signals
    from aicoach.scene_classify import infer_screen_type_from_text

    probe_results = osu_results_screen_signals(probe_l, probe_ocr)
    cache_gameplay = prev_type == "gameplay" or infer_screen_type_from_text(
        cached.description, game_id
    ) == "gameplay"
    if probe_results and cache_gameplay:
        return True, "OCR shows results/failed; cached context was gameplay"

    probe_gameplay = infer_screen_type_from_text(probe_ocr, game_id) == "gameplay"
    cache_results = prev_type in ("results", "map_select", "menu") or (
        osu_results_screen_signals(desc_l, cached.description)
    )
    if probe_gameplay and cache_results:
        return True, "OCR shows active play; cached context was post-play/results"

    return False, ""
