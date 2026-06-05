from __future__ import annotations

import logging
import re

from aicoach.osu_results import osu_results_screen_signals
from aicoach.screen_observation import ScreenObservation

logger = logging.getLogger(__name__)

_GAMEPLAY_TYPES = frozenset({"gameplay", "playing", "in_game", "in-game", "in game"})
_MAP_UI_TYPES = frozenset({"map_select", "map select", "song select", "song_select", "beatmap select"})
_MENU_TYPES = frozenset({"menu", "main menu", "main_menu"})


def normalize_screen_type_label(raw: str) -> str:
    """Map vision/OCR labels to canonical scene ids."""
    lower = (raw or "").strip().lower()
    if not lower or lower == "unknown":
        return "unknown"
    if any(x in lower for x in _MAP_UI_TYPES) or "select" in lower and "map" in lower:
        return "map_select"
    if any(x in lower for x in _MENU_TYPES):
        return "menu"
    if any(x in lower for x in _GAMEPLAY_TYPES):
        return "gameplay"
    if "result" in lower or "score screen" in lower:
        return "results"
    if lower in ("lobby", "multiplayer", "multi"):
        return "lobby"
    if lower in ("pause", "paused"):
        return "pause"
    if lower in ("loading", "load"):
        return "loading"
    return lower.split()[0] if lower else "unknown"


def _osu_map_select_signals(lower: str) -> bool:
    if any(
        w in lower
        for w in (
            "beatmap",
            "song select",
            "map select",
            "mods",
            "difficulty",
            "star rating",
            "mapper",
            "bpm",
            "length",
            "od:",
            "ar:",
            "cs:",
            "hp:",
            "nomod",
            "no beatmap",
            "beatmaps",
            "ranked",
            "loved",
            "qualified",
            "featured artist",
        )
    ):
        return True
    if re.search(r"\b(?:od|ar|cs|hp)\s*[:\s]\s*[\d.]+", lower):
        return True
    if re.search(r"\d+(?:\.\d+)?\s*(?:\*|stars?|★)", lower):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*★", lower):
        return True
    return False


def _osu_menu_signals(lower: str, ocr_text: str | None = None) -> bool:
    text = ocr_text if ocr_text is not None else lower
    if osu_results_screen_signals(lower, text):
        return False
    if any(w in lower for w in ("main menu", "click to start", "back to menu")):
        return True
    if "osu!" in lower and any(
        w in lower for w in ("play", "edit", "options", "solo", "multi", "exit")
    ):
        return True
    return False


def _osu_results_signals(lower: str, ocr_text: str) -> bool:
    return osu_results_screen_signals(lower, ocr_text)


def _osu_live_gameplay_hud(lower: str, ocr_text: str) -> bool:
    """Active play HUD — not song-select star % or background preview."""
    if _osu_map_select_signals(lower) or _osu_menu_signals(lower, ocr_text):
        return False
    if _osu_results_signals(lower, ocr_text):
        return False

    has_acc = "accuracy" in lower and re.search(r"\b\d{1,3}\.\d{2}\s*%", ocr_text)
    has_combo = bool(
        re.search(r"\b\d+x\b", lower)
        or (
            "combo" in lower
            and re.search(r"\bcombo\b[^0-9]*\d{2,}", lower)
        )
    )
    has_judgements = any(
        w in lower for w in ("x100", "x50", "xmiss", "100k", "50k")
    ) and "max combo" not in lower
    has_score_hud = "score" in lower and re.search(r"\b\d{4,}\b", ocr_text)
    signals = sum([bool(has_acc), bool(has_combo), bool(has_judgements), bool(has_score_hud)])
    return signals >= 2


def infer_screen_type_from_text(ocr_text: str, game_id: str) -> str:
    """Heuristic scene from OCR or description text (osu-first)."""
    lower = ocr_text.lower()
    if not lower.strip():
        return "unknown"

    if game_id == "osu":
        if _osu_menu_signals(lower, ocr_text) and not _osu_map_select_signals(lower):
            return "menu"
        if _osu_map_select_signals(lower):
            return "map_select"
        # Before results — G/O/M/M counter skins look like results to naive OCR.
        if _osu_live_gameplay_hud(lower, ocr_text):
            return "gameplay"
        if _osu_results_signals(lower, ocr_text):
            return "results"

    if len(ocr_text.strip()) < 40:
        return "unknown"
    return "unknown"


def description_suggests_map_select(description: str) -> bool:
    lower = description.lower()
    if _osu_map_select_signals(lower):
        return True
    if any(
        phrase in lower
        for phrase in (
            "song select",
            "map select",
            "beatmap select",
            "difficulty panel",
            "star rating",
            "bpm",
            "mapper",
            "mod selection",
            "mods panel",
            "play button",
            "no score",
            "not in gameplay",
            "not actively playing",
            "preview",
            "background preview",
        )
    ):
        return True
    return False


def description_suggests_menu(description: str) -> bool:
    lower = description.lower()
    return _osu_menu_signals(lower, description) or any(
        p in lower for p in ("main menu", "title screen", "menu screen", "mode select")
    )


def description_suggests_gameplay(description: str) -> bool:
    lower = description.lower()
    if description_suggests_map_select(description) or description_suggests_menu(description):
        return False
    return _osu_live_gameplay_hud(lower, description)


def reconcile_screen_observation(
    obs: ScreenObservation,
    *,
    ocr_text: str | None = None,
    game_id: str = "osu",
) -> ScreenObservation:
    """
    Fix mislabeled gameplay when OCR/description indicate menu or song select.
    """
    declared = normalize_screen_type_label(obs.screen_type)
    ocr_type = (
        infer_screen_type_from_text(ocr_text, game_id)
        if ocr_text and ocr_text.strip()
        else "unknown"
    )
    desc_type = infer_screen_type_from_text(obs.description, game_id)
    if desc_type == "unknown":
        if description_suggests_map_select(obs.description):
            desc_type = "map_select"
        elif description_suggests_menu(obs.description):
            desc_type = "menu"
        elif description_suggests_gameplay(obs.description):
            desc_type = "gameplay"

    corrected = declared
    reason = ""
    non_play = frozenset({"map_select", "menu", "results", "lobby", "pause", "loading"})

    if declared == "gameplay":
        if ocr_type in non_play:
            corrected, reason = ocr_type, f"OCR says {ocr_type}"
        elif desc_type in non_play:
            corrected, reason = desc_type, f"description says {desc_type}"
        elif description_suggests_map_select(obs.description):
            corrected, reason = "map_select", "song-select UI in description"
        elif description_suggests_menu(obs.description):
            corrected, reason = "menu", "menu UI in description"
    elif declared == "results":
        if ocr_type == "gameplay" or description_suggests_gameplay(obs.description):
            corrected, reason = (
                "gameplay",
                "live HUD with hit counters — not post-play results",
            )
    elif declared == "unknown":
        corrected = ocr_type if ocr_type != "unknown" else desc_type

    if corrected == declared and declared == normalize_screen_type_label(obs.screen_type):
        return obs

    if corrected != declared and reason:
        if corrected == "results":
            note = (
                f"[Scene corrected: {declared} -> {corrected} ({reason}). "
                "Post-play results — use Great/Ok/Meh/Miss counts and final accuracy, "
                "NOT live gameplay or song progress %.]"
            )
        else:
            note = (
                f"[Scene corrected: {declared} -> {corrected} ({reason}). "
                "Do NOT mention live combo, accuracy HUD, or song progress % on "
                "song select/menu/results.]"
            )
        description = f"{note}\n{obs.description}"
        raw = re.sub(
            r"(?i)^SCREEN_TYPE:\s*.+$",
            f"SCREEN_TYPE: {corrected}",
            obs.raw,
            count=1,
            flags=re.MULTILINE,
        )
        sq = obs.search_query
        if corrected == "map_select" and not sq:
            from aicoach.screen_ocr import extract_search_query_from_ocr

            if ocr_text:
                sq = extract_search_query_from_ocr(ocr_text)
            if not sq:
                sq = extract_search_query_from_ocr(obs.description)

        logger.info("Screen type corrected: %s -> %s (%s)", declared, corrected, reason)
        return ScreenObservation(
            screen_type=corrected,
            description=description,
            raw=raw,
            search_query=sq if corrected == "map_select" else obs.search_query,
        )

    return ScreenObservation(
        screen_type=corrected,
        description=obs.description,
        raw=obs.raw,
        search_query=obs.search_query,
    )
