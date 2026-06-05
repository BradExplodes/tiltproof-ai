from __future__ import annotations

import re

# Answer may use last screen observation (OCR/vision cache) — no new read.
_SCREEN_CONTEXT_PATTERNS = (
    r"\bwhat (?:map|song|beatmap)\b",
    r"\bwhich (?:map|song|beatmap)\b",
    r"\bwhat should i (?:play|pick|choose)\b",
    r"\bwhat(?:'s| is) (?:on|this)(?: the| this)? map\b",
    r"\bwhat am i (?:playing|on)\b",
    r"\b(?:artist|title|bpm|star rating|difficulty|mods)\b",
    r"\b(?:score|combo|accuracy|pp|miss(?:es)?)\b",
    r"\bwhat(?:'s| is) (?:the|my) (?:score|combo|accuracy)\b",
    r"\bhow(?:'s| is) my (?:accuracy|combo|score)\b",
    r"\bwhat(?:'s| is) (?:happening|going on)\b",
    r"\bwhat(?:'s| is) my rank\b",
    r"\bmy rank\b",
    r"\brank\b",
)

# Must capture + run OCR/vision again (not cache-only).
_FRESH_SCREEN_READ_PATTERNS = (
    r"\bwhat (?:can you |do you )?see\b",
    r"\bwhat(?:'s| is) on (?:the |my )?screen\b",
    r"\bwhat am i looking at\b",
    r"\blook at (?:the |my )?screen\b",
    r"\bcheck (?:the |my )?screen\b",
    r"\bwatch (?:the |my )?screen\b",
    r"\bsee (?:the |my )?screen\b",
    r"\bon (?:the |my )?screen\b",
    r"\bread (?:the |my )?screen\b",
    r"\bright now\b.*\bsee\b",
    r"\bsee\b.*\bright now\b",
    r"\bdescribe (?:the |my )?(?:screen|game|playfield)\b",
    r"\btell me what you see\b",
    r"\blook at (?:this|that|it)\b",
    # Map/song on screen now — must not reuse a prior map's OCR/vision cache.
    r"\bcheck\s+out\b.*\b(?:map|song|beatmap)\b",
    r"\bcheck\s+(?:out\s+)?(?:this|the|my|that)\s+(?:map|song|beatmap)\b",
    r"\blook\s+at\s+(?:this|the|my|that)\s+(?:map|song|beatmap)\b",
    r"\b(?:rate|review)\s+(?:this|the|my|that)?\s*(?:map|song|beatmap)\b",
    r"\bwhat\s+do\s+you\s+think\s+of\s+(?:this|the|my|that)?\s*(?:map|song|beatmap)\b",
    r"\btell\s+me\s+about\s+(?:this|the|my|that)\s+(?:map|song|beatmap)\b",
    r"\b(?:peek|scan|glance)\s+at\s+(?:this|the|my|that)?\s*(?:map|song|beatmap)\b",
)

# Legacy name — any question that may use screen context (fresh or cached).
_SCREEN_QUESTION_PATTERNS = _SCREEN_CONTEXT_PATTERNS + _FRESH_SCREEN_READ_PATTERNS

_VISUAL_REASONING_PATTERNS = (
    r"\bwhat (?:can you |do you )?see\b",
    r"\btell me what you see\b",
    r"\bprofile\s*(?:pic(?:ture)?|image|avatar)\b",
    r"\b(?:my|your)\s+avatar\b",
    r"\bwhat(?:'s| is)\s+(?:my|the)\s+(?:pic(?:ture)?|avatar|pfp)\b",
    r"\blook(?:s)?\s+like\b",
    r"\bwhat\s+colou?r\b",
    r"\b(?:circle|approach|slider|spinner|playfield)\b",
    r"\bdescribe\s+(?:the\s+)?(?:playfield|circles?|visual)\b",
    r"\b(?:skin|banner|background)\s+(?:look|show)\b",
    r"\bwho\s+is\s+(?:that|this)\s+(?:character|person|girl|guy)\b",
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pat, text) for pat in patterns)


def user_asks_about_screen(transcript: str) -> bool:
    """True when the reply may use screen context (cached or fresh)."""
    return voice_needs_screen_context(transcript)


def voice_needs_screen_context(transcript: str) -> bool:
    """Screen context helps answer (cache is OK)."""
    text = transcript.strip().lower()
    if not text:
        return False
    if needs_visual_reasoning(text):
        return True
    return _matches_any(text, _SCREEN_CONTEXT_PATTERNS) or _matches_any(
        text, _FRESH_SCREEN_READ_PATTERNS
    )


def _asks_to_inspect_current_map(text: str) -> bool:
    """Player is pointing at the map/song on screen right now."""
    if not re.search(r"\b(?:map|song|beatmap)\b", text):
        return False
    if not re.search(r"\b(this|that|the|my|current)\b", text):
        return False
    return bool(
        re.search(
            r"\b(?:check|look|see|watch|rate|review|peek|scan|glance|tell me about|"
            r"what do you think)\b",
            text,
        )
    )


def voice_wants_fresh_screen_read(transcript: str) -> bool:
    """Must capture and run OCR/vision — do not rely on cache alone."""
    text = transcript.strip().lower()
    if not text:
        return False
    if needs_visual_reasoning(text):
        return True
    if _matches_any(text, _FRESH_SCREEN_READ_PATTERNS):
        return True
    return _asks_to_inspect_current_map(text)


def needs_visual_reasoning(transcript: str) -> bool:
    """Questions that need OpenAI vision, not OCR alone."""
    text = transcript.strip().lower()
    if not text:
        return False
    return _matches_any(text, _VISUAL_REASONING_PATTERNS)


def prefer_screen_ocr(transcript: str) -> bool:
    """OCR-first when a new screen read runs (not visual-reasoning questions)."""
    text = transcript.strip().lower()
    if not text:
        return True
    if needs_visual_reasoning(text):
        return False
    return voice_needs_screen_context(text)


def voice_should_use_ocr_read(transcript: str) -> bool:
    """Text/HUD questions: capture + Tesseract (not vision)."""
    text = transcript.strip().lower()
    return prefer_screen_ocr(text) and not needs_visual_reasoning(text)


def voice_should_use_vision_read(transcript: str) -> bool:
    """Visual / describe-screen questions need OpenAI vision only (skip OCR path)."""
    return needs_visual_reasoning(transcript.strip().lower())
