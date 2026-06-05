from __future__ import annotations

import base64
import logging

from aicoach.openai_client import build_openai_client

from aicoach.capture import Screenshot
from aicoach.pricing import UsageCost, estimate_cost_usd
from aicoach.prompts import load_describer_prompt
from aicoach.screen_observation import ScreenObservation, parse_screen_observation

logger = logging.getLogger(__name__)

_VISION_DETAIL_DEFAULT = "high"

_DESCRIBER_FORMAT = """
Output format (no other commentary):
SCREEN_TYPE: menu | map_select | gameplay | results | lobby | loading | pause | desktop_other | unknown
SEARCH_QUERY: the specific map/match/title shown (e.g. "Artist - Title" on a song/map select), else NONE
DESCRIPTION:
<An exhaustive, literal rundown of EVERYTHING visible on screen, organized clearly. Cover, when present:
- The overall scene and what the player is doing right now.
- Every HUD value with its EXACT number: health/HP, mana, shields, score, combo, accuracy %, timer/clock, ammo, gold/currency, KDA, rank/rating, level/XP, match or song progress %, etc.
- All readable text: titles, menu items, button labels, player/character names, chat, notifications, tooltips, objectives.
- Characters/units/players visible: who/what they are, their positions, and states (alive/dead, low HP, casting, stunned, etc.).
- Map/minimap details, objectives, icons, ability/cooldown indicators, and anything actionable.
- Spatial layout (top-left, center, bottom-right, etc.) so positions are unambiguous.
Be specific and quantitative — prefer exact numbers and proper names over vague summaries. Aim for 6–12 sentences. Never invent anything you cannot actually see; if a region is unreadable, say so.
CRITICAL: a beatmap/song PREVIEW playing behind a song/map select menu is still map_select, NOT gameplay. Only use gameplay when the live in-match HUD is visible during active play. Report match/song progress % ONLY during gameplay, never on a menu or select screen.>
"""


class ScreenDescriber:
    """Stage 1: vision model describes the screen; no personality."""

    def __init__(
        self,
        api_key: str,
        model: str,
        image_detail: str = _VISION_DETAIL_DEFAULT,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> None:
        detail = image_detail.strip().lower()
        if detail not in ("low", "high"):
            raise ValueError("image_detail must be 'low' or 'high'")
        self._client = build_openai_client(api_key)
        self._model = model
        self._image_detail = detail
        self._temperature = temperature
        self._max_tokens = max_tokens

    def describe(
        self,
        screenshot: Screenshot,
        game_id: str,
        *,
        focus: str | None = None,
    ) -> tuple[ScreenObservation, UsageCost | None]:
        mime = screenshot.mime_type or "image/png"
        image_b64 = base64.standard_b64encode(screenshot.png_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{image_b64}"

        system = load_describer_prompt(game_id) + "\n\n" + _DESCRIBER_FORMAT.strip()
        user_text = (
            "Describe this game screenshot in exhaustive, literal detail, following the output format. "
            "First decide the screen type. Then describe everything visible: every stat with its exact "
            "value, all readable text, every character/unit/player and their state, map/minimap and "
            "objectives, and where each element sits on screen. Be specific and quantitative; never "
            "invent details you cannot actually see."
        )
        focus = (focus or "").strip()
        if focus:
            user_text += (
                f'\n\nThe player just said: "{focus}". In addition to the full-screen rundown, '
                "find and describe in extra detail whatever on screen is relevant to what they said "
                "(exact numbers, names, positions, states). If nothing on screen relates to it, note that briefly."
            )

        size_kb = screenshot.size_kb
        dims = (
            f"{screenshot.width}x{screenshot.height}"
            if screenshot.width
            else "unknown"
        )
        logger.info(
            "Vision request: %s, detail=%s, image=%.0fKB %s",
            self._model,
            self._image_detail,
            size_kb,
            dims,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                                "detail": self._image_detail,
                            },
                        },
                    ],
                },
            ],
            temperature=self._temperature,
        )

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            raw = "SCREEN_TYPE: unknown\nSEARCH_QUERY: NONE\nDESCRIPTION: Empty or unreadable frame."

        observation = parse_screen_observation(raw)
        usage = None
        if response.usage:
            usage = estimate_cost_usd(
                self._model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
            logger.info(
                "Describe (%s): %s in / %s out (~$%.4f) | type=%s",
                self._model,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.estimated_usd,
                observation.screen_type,
            )

        logger.debug("Screen description: %s", observation.description[:300])
        return observation, usage
