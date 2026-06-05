from __future__ import annotations

import re

from aicoach.screen_observation import ScreenObservation
from aicoach.screen_ocr import (
    extract_search_query_from_ocr,
    infer_screen_type,
    ocr_is_usable,
)

_MAP_QUESTION = (
    r"\bwhat (?:map|song|beatmap)\b",
    r"\bwhich (?:map|song|beatmap)\b",
    r"\bwhat should i (?:play|pick|choose)\b",
    r"\bwhat(?:'s| is) (?:on|this)(?: the| this)? map\b",
    r"\bwhat am i (?:playing|on)\b",
    r"\b(?:artist|title|bpm|star rating|difficulty|mods)\b",
)

_STATS_QUESTION = (
    r"\b(?:score|combo|accuracy|pp|miss(?:es)?)\b",
    r"\bwhat(?:'s| is) (?:the|my) (?:score|combo|accuracy)\b",
    r"\bhow(?:'s| is) my (?:accuracy|combo|score)\b",
)

_RANK_QUESTION = (
    r"\bwhat(?:'s| is) my rank\b",
    r"\bmy rank\b",
    r"\brank\b",
)


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pat, text) for pat in patterns)


def _alnum_ratio(text: str) -> float:
    if not text:
        return 0.0
    alnum = sum(ch.isalnum() for ch in text)
    return alnum / len(text)


def _meaningful_line_count(ocr_text: str) -> int:
    count = 0
    for line in ocr_text.splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        words = [w for w in re.split(r"\s+", line) if re.search(r"[A-Za-z0-9]", w)]
        if len(words) >= 2 or (len(line) >= 6 and _alnum_ratio(line) >= 0.5):
            count += 1
    return count


def _asks_map_question(transcript_lower: str) -> bool:
    return _matches(transcript_lower, _MAP_QUESTION)


def _asks_stats_question(transcript_lower: str) -> bool:
    return _matches(transcript_lower, _STATS_QUESTION)


def _asks_rank_question(transcript_lower: str) -> bool:
    return _matches(transcript_lower, _RANK_QUESTION)


def _ocr_has_map_signals(ocr_text: str, observation: ScreenObservation, game_id: str) -> bool:
    if extract_search_query_from_ocr(ocr_text):
        return True
    lower = ocr_text.lower()
    if observation.screen_type == "map_select":
        return _meaningful_line_count(ocr_text) >= 2
    if game_id == "osu":
        if re.search(r"\d+(?:\.\d+)?\s*\*|\bstars?\b", lower) and re.search(r"\d", ocr_text):
            return True
        if any(
            w in lower
            for w in ("beatmap", "bpm", "od:", "ar:", "cs:", "hp:", "mods", "difficulty")
        ):
            return True
    return _meaningful_line_count(ocr_text) >= 4


def _ocr_has_stats_signals(ocr_text: str) -> bool:
    scene = infer_screen_type(ocr_text, "osu")
    if scene == "results":
        return True
    if scene != "gameplay":
        return False
    lower = ocr_text.lower()
    if "accuracy" in lower and re.search(r"\b\d{1,3}\.\d{2}\s*%", ocr_text):
        return True
    if re.search(r"\b\d{1,6}\b", ocr_text) and any(
        w in lower for w in ("combo", "score", "miss", "x100", "x50", "pp")
    ):
        return True
    return False


def _ocr_has_rank_signals(ocr_text: str) -> bool:
    lower = ocr_text.lower()
    if "rank" in lower and re.search(r"\d", ocr_text):
        return True
    if re.search(r"#\s*\d{1,7}\b", ocr_text):
        return True
    if re.search(r"\bglobal\s*#?\s*\d+", lower):
        return True
    return False


def ocr_sufficient_for_transcript(
    transcript: str,
    observation: ScreenObservation,
    ocr_text: str,
    game_id: str,
) -> tuple[bool, str]:
    """
    Whether OCR text is good enough to answer this voice question without vision.

    Returns (sufficient, short reason for logs).
    """
    if not ocr_is_usable(observation):
        return False, "too little recognized text"

    text = ocr_text.strip()
    ratio = _alnum_ratio(text)
    if len(text) >= 20 and ratio < 0.32:
        return False, "OCR output looks garbled"

    lower_t = transcript.strip().lower()

    if _asks_map_question(lower_t):
        if _ocr_has_map_signals(text, observation, game_id):
            return True, "map or song details in OCR"
        return False, "no map or song info in OCR"

    if _asks_stats_question(lower_t):
        if _ocr_has_stats_signals(text):
            return True, "score or accuracy details in OCR"
        return False, "no gameplay stats in OCR"

    if _asks_rank_question(lower_t):
        if _ocr_has_rank_signals(text):
            return True, "rank info in OCR"
        return False, "no rank info in OCR"

    if observation.screen_type != "unknown" and len(text) >= 24:
        return True, f"scene={observation.screen_type}"

    lines = _meaningful_line_count(text)
    if lines >= 3 and ratio >= 0.4:
        return True, f"{lines} readable HUD lines"

    return False, "unclear scene or sparse HUD for this question"
