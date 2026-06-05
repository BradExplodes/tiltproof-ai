from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aicoach.openai_client import build_openai_client

from aicoach.pricing import (
    estimate_cost_usd,
    estimate_web_search_content_fallback_usd,
    estimate_web_search_tool_cost_usd,
)
from aicoach.response_parse import (
    extract_map_intel,
    extract_say_only,
    parse_coach_response,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSearchUsage:
    search_calls: int
    estimated_usd: float
    model: str


@dataclass(frozen=True)
class MapIntel:
    """Web research cached for the current map."""

    map_name: str
    notes: str


def _extract_output_text(response: Any) -> str:
    texts: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for block in getattr(item, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def _count_search_actions(response: Any) -> int:
    count = 0
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "web_search_call":
            continue
        action = getattr(item, "action", None)
        if action and getattr(action, "type", None) == "search":
            count += 1
    return count


def _usage_cost(response: Any, model: str, search_calls: int) -> float:
    cost = estimate_web_search_tool_cost_usd(search_calls)
    if getattr(response, "usage", None):
        in_tok = getattr(response.usage, "input_tokens", 0) or 0
        out_tok = getattr(response.usage, "output_tokens", 0) or 0
        cost += estimate_cost_usd(model, in_tok, out_tok).estimated_usd
    else:
        cost += estimate_web_search_content_fallback_usd(model, search_calls)
    return cost


def scene_triggers_web(scene: str, trigger_scenes: frozenset[str]) -> bool:
    scene_lower = scene.lower()
    for trigger in trigger_scenes:
        if trigger in scene_lower:
            return True
    return False


class WebSearchCoach:
    """OpenAI Responses API + web_search tool."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4o-mini",
        search_context_size: str = "medium",
    ) -> None:
        self._client = build_openai_client(api_key)
        self._model = model
        self._search_context_size = search_context_size

    def _run_search(self, prompt: str, max_output_tokens: int, temperature: float) -> Any:
        tool: dict[str, Any] = {
            "type": "web_search",
            "search_context_size": self._search_context_size,
        }
        return self._client.responses.create(
            model=self._model,
            tools=[tool],
            tool_choice="required",
            input=[{"role": "user", "content": prompt}],
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

    def _map_research_prompt(
        self, *, game_id: str, map_name: str, vision_say: str
    ) -> str:
        if game_id == "osu":
            search_hints = (
                f'"{map_name}" osu beatmap hardest part stream jump timing '
                f'"{map_name}" site:reddit.com/r/osugame '
                f'"{map_name}" choke finger control section percent'
            )
            intel_format = """
MAP_INTEL (required — be specific, not vague):
MAP: <Artist - Title>
SECTION: <start%-end%> | <pattern: stream/jump/burst/tech/stamina/1-2/spaced stream> | <why it's hard> | <community choke note>
SECTION: ... (2–5 sections if found)
PEAK: <single hardest moment — %> | <pattern> | <why>
FIRST_SPIKE: <earliest nasty section — %> | <pattern>
LENGTH_HINT: <approx map length MM:SS if found, else unknown>

Rules:
- Use song progress % (0%=start, 100%=end). Convert timestamps to % when map length is known.
- Do NOT write fluff like "has hard streams" without WHERE. Every SECTION needs a % range.
- Pull from osu.ppy.sh discussions, Reddit, YouTube comments, mapper notes if available.
"""
        else:
            search_hints = (
                f'"{map_name}" {game_id} hardest part difficult section '
                "timing percentage community"
            )
            intel_format = """
MAP_INTEL:
SECTION: <start%-end%> | <what happens> | <why players fail>
PEAK: <hardest moment — %>
"""

        say_note = ""
        if vision_say.strip():
            say_note = f"\nDraft reaction from screenshot (may be wrong):\n{vision_say}\n"

        return f"""You are researching a {game_id} map for live coaching (hard-section callouts during play).

MAP TO RESEARCH: {map_name}
Search the web. Example queries: {search_hints}
{intel_format}
{say_note}
CRITICAL: Put ALL research detail in MAP_INTEL only. SAY is spoken aloud — no URLs, bullets, or tags in SAY.

Output format (each tag on its own line):
MAP_INTEL:
<structured lines as above>
SCENE: map research done
SAY: 2-4 spoken sentences (friend voice) — name 1–2 specific sections with % or pattern type from MAP_INTEL. No URLs.
"""

    def research_map(
        self,
        *,
        game_id: str,
        map_name: str,
        scene: str,
        vision_say: str,
        temperature: float = 0.65,
        max_output_tokens: int = 900,
    ) -> tuple[str, MapIntel | None, WebSearchUsage]:
        """
        Search for community info on map difficulty spikes and hard sections.
        Returns spoken line for map select + cached intel for gameplay warnings.
        """
        logger.info("Map web research: %s", map_name)

        prompt = self._map_research_prompt(
            game_id=game_id, map_name=map_name, vision_say=vision_say
        )

        response = self._run_search(prompt, max_output_tokens, temperature)
        raw = _extract_output_text(response)
        search_calls = _count_search_actions(response) or 1
        cost = _usage_cost(response, self._model, search_calls)

        if not raw:
            logger.warning("Map web research returned empty text")
            return vision_say, None, WebSearchUsage(
                search_calls=search_calls,
                estimated_usd=cost,
                model=self._model,
            )

        parsed = parse_coach_response(raw)
        intel_notes = parsed.map_intel or extract_map_intel(raw)
        intel = None
        if intel_notes:
            intel = MapIntel(map_name=map_name, notes=intel_notes)
            logger.info("Stored map intel for: %s", map_name)

        spoken = extract_say_only(raw) or parsed.spoken
        if not spoken:
            logger.warning("Web SAY parse failed; using vision draft")
            spoken = vision_say
        logger.info("Map web research: %s search(es) (~$%.4f)", search_calls, cost)

        return spoken, intel, WebSearchUsage(
            search_calls=search_calls,
            estimated_usd=cost,
            model=self._model,
        )

    def augment(
        self,
        *,
        game_id: str,
        scene: str,
        search_query: str,
        vision_say: str,
        temperature: float = 0.65,
        max_output_tokens: int = 200,
    ) -> tuple[str, WebSearchUsage]:
        """General web grounding for non-map screens."""
        prompt = f"""Friend coaching {game_id}. Screen: {scene}
Search: {search_query}

Draft: {vision_say}

Use web for ONE useful fact. No square brackets in SAY.

SCENE: {scene} — web check done
SAY: 2-4 sentences, plain spoken text only
"""

        logger.info("Web search: %s", search_query)
        response = self._run_search(prompt, max_output_tokens, temperature)
        raw = _extract_output_text(response)
        search_calls = _count_search_actions(response) or 1
        cost = _usage_cost(response, self._model, search_calls)

        if not raw:
            return vision_say, WebSearchUsage(
                search_calls=search_calls,
                estimated_usd=cost,
                model=self._model,
            )

        spoken = extract_say_only(raw) or parse_coach_response(raw).spoken or vision_say
        return spoken, WebSearchUsage(
            search_calls=search_calls,
            estimated_usd=cost,
            model=self._model,
        )
