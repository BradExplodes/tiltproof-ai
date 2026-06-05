from __future__ import annotations

import re
from typing import TypedDict


class OsuResultsStats(TypedDict, total=False):
    great: int
    ok: int
    meh: int
    misses: int
    accuracy_pct: float
    max_combo: int
    pp: float


# Results-only UI — not shown on live gameplay HUDs (even with G/O/M/M counter skins).
_RESULTS_EXCLUSIVE_MARKERS = (
    "failed",
    "passed",
    "retry",
    "back to menu",
    "local score",
    "performance",
    "slider tick",
    "slider end",
    "spinner bonus",
    "spinner spin",
    "rank #",
    "rank:",
)


def osu_live_play_excludes_results(lower: str, ocr_text: str) -> bool:
    """
    True when text looks like active play — many skins show Great/Ok/Meh/Miss
    counters during the map, which must not be classified as the results screen.
    """
    if re.search(r"\b\d+x\b", lower):
        return True
    if any(w in lower for w in ("x100", "x50", "xmiss", "100k", "50k")):
        return True
    has_live_acc = "accuracy" in lower and re.search(
        r"\b\d{1,3}\.\d{2}\s*%", ocr_text
    )
    has_score = "score" in lower and re.search(r"\b\d{4,}\b", ocr_text)
    has_combo = (
        "combo" in lower
        and "max combo" not in lower
        and re.search(r"\bcombo\b[^0-9]*\d{2,}", lower)
    )
    if sum([bool(has_live_acc), bool(has_score), bool(has_combo)]) >= 2:
        return True
    return False


def osu_results_hit_breakdown_visible(lower: str, *, ocr_text: str | None = None) -> bool:
    """
    Post-play results summary: Great / Ok / Meh / Miss counts (not live gameplay HUD).
    """
    text = ocr_text if ocr_text is not None else lower
    if osu_live_play_excludes_results(lower, text):
        return False

    has_great = bool(re.search(r"\bgreat\b", lower))
    has_ok = bool(re.search(r"\bok\b", lower))
    has_meh = bool(re.search(r"\bmeh\b", lower))
    has_miss = bool(re.search(r"\bmiss(?:es)?\b", lower))
    label_count = sum([has_great, has_ok, has_meh, has_miss])

    if label_count >= 3:
        # Hit-counter skins during play — require results-only chrome as well.
        if any(m in lower for m in _RESULTS_EXCLUSIVE_MARKERS):
            return True
        if "max combo" in lower and re.search(r"\b\d{1,3}\.\d{2}\s*%", text):
            return True
        return False

    if has_great and has_miss and any(
        w in lower
        for w in (
            "max combo",
            "slider tick",
            "slider end",
            "spinner bonus",
            "spinner spin",
            "local score",
            "performance",
        )
    ):
        return True
    return False


def osu_results_screen_signals(lower: str, ocr_text: str | None = None) -> bool:
    """Results / fail screen — includes pass and fail summaries."""
    text = ocr_text if ocr_text is not None else lower
    if osu_live_play_excludes_results(lower, text):
        return False
    if osu_results_hit_breakdown_visible(lower, ocr_text=text):
        return True
    if any(w in lower for w in ("failed", "passed", "retry", "back to menu")):
        return True
    if any(w in lower for w in ("local score", "performance", "rank #", "rank:")):
        if any(w in lower for w in ("accuracy", "combo", "pp", "grade")):
            return True
    if "max combo" in lower and "accuracy" in lower and re.search(
        r"\b\d{1,3}\.\d{2}\s*%", lower
    ):
        if not re.search(r"\b\d+x\b", lower):
            return True
    return False


def _parse_accuracy(lower: str) -> float | None:
    matches = re.findall(r"\b(\d{1,3}\.\d{2})\s*%", lower)
    if not matches:
        return None
    # Results often show final acc; prefer the last plausible value.
    for raw in reversed(matches):
        val = float(raw)
        if 0 < val <= 100:
            return val
    return None


def _parse_labeled_count(lower: str, label: str) -> int | None:
    for m in re.finditer(rf"\b{label}\b", lower):
        chunk = lower[m.end() : m.end() + 40]
        num = re.search(r"(\d{1,5})", chunk)
        if not num:
            continue
        window = lower[max(0, m.start()) : m.end() + num.end() + 4]
        if re.search(r"\d+\.\d{2}\s*%", window):
            continue
        return int(num.group(1))
    return None


def _plausible_hit_counts(g: int, o: int, meh: int, miss: int) -> bool:
    if g < o or g < meh or g < miss:
        return False
    if g > 5000 or o > 2000 or meh > 500 or miss > 2000:
        return False
    return True


def _parse_four_count_run(lower: str) -> OsuResultsStats | None:
    """OCR often dumps Great/Ok/Meh/Miss counts as four integers in a row."""
    patterns = [
        r"%\s*(\d{1,4})\s+(\d{1,3})\s+(\d{1,2})\s+(\d{1,3})\s+(?:slider|spinner)",
        r"\b(\d{2,4})\s+(\d{1,3})\s+(\d{1,2})\s+(\d{1,3})\s+(?:slider|spinner|max\s*combo)",
        r"(?:great|ok|meh|miss)[\s\S]{0,200}?(\d{2,4})\s+(\d{1,3})\s+(\d{1,2})\s+(\d{1,3})\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, lower):
            g, o, meh, miss = (int(m.group(i)) for i in range(1, 5))
            if _plausible_hit_counts(g, o, meh, miss):
                return {"great": g, "ok": o, "meh": meh, "misses": miss}
    return None


def parse_osu_results_stats(ocr_text: str) -> OsuResultsStats:
    """Extract results-screen hit counts and accuracy from OCR text."""
    lower = ocr_text.lower()
    stats: OsuResultsStats = {}

    acc = _parse_accuracy(lower)
    if acc is not None:
        stats["accuracy_pct"] = acc

    combo_m = re.search(r"max\s*combo[^\d]{0,20}(\d{1,6})", lower)
    if combo_m:
        stats["max_combo"] = int(combo_m.group(1))

    pp_m = re.search(r"\bpp\b[^\d]{0,15}(\d{1,4}(?:\.\d+)?)", lower)
    if pp_m:
        stats["pp"] = float(pp_m.group(1))

    if osu_results_hit_breakdown_visible(lower, ocr_text=ocr_text):
        run = _parse_four_count_run(lower)
        if run:
            stats.update(run)

    for label, key in (
        ("great", "great"),
        ("ok", "ok"),
        ("meh", "meh"),
        ("misses", "misses"),
        ("miss", "misses"),
    ):
        if key in stats:
            continue
        val = _parse_labeled_count(lower, label)
        if val is not None:
            stats[key] = val

    return stats


def format_osu_results_summary(stats: OsuResultsStats) -> str:
    parts: list[str] = []
    if "great" in stats:
        parts.append(f"Great {stats['great']}")
    if "ok" in stats:
        parts.append(f"Ok {stats['ok']}")
    if "meh" in stats:
        parts.append(f"Meh {stats['meh']}")
    if "misses" in stats:
        parts.append(f"Misses {stats['misses']}")
    if not parts:
        return ""
    line = "Results hit counts: " + ", ".join(parts) + "."
    if "accuracy_pct" in stats:
        line += f" Accuracy {stats['accuracy_pct']:.2f}%."
    if "max_combo" in stats:
        line += f" Max combo {stats['max_combo']}."
    if "pp" in stats:
        line += f" PP {stats['pp']}."
    return line
