from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens (standard tier). Update if OpenAI changes list prices.
MODEL_RATES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
}


@dataclass(frozen=True)
class UsageCost:
    prompt_tokens: int
    completion_tokens: int
    estimated_usd: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> UsageCost:
    """Estimate call cost from token usage returned by the API."""
    input_rate, output_rate = MODEL_RATES.get(model, (0.15, 0.60))
    usd = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return UsageCost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_usd=usd,
    )


def project_session_cost(
    cost_per_call_usd: float,
    interval_seconds: float,
    hours: float,
) -> float:
    calls = (hours * 3600) / interval_seconds
    return cost_per_call_usd * calls


# USD per 1M characters (OpenAI speech API, standard tier).
TTS_RATES_PER_1M_CHARS: dict[str, float] = {
    "tts-1": 15.0,
    "tts-1-hd": 30.0,
}


def estimate_tts_cost_usd(model: str, text: str) -> float:
    rate = TTS_RATES_PER_1M_CHARS.get(model, 15.0)
    return len(text) * rate / 1_000_000


# ElevenLabs approximate USD per 1M characters (varies by plan/model).
ELEVENLABS_RATES_PER_1M_CHARS: dict[str, float] = {
    "eleven_turbo_v2_5": 180.0,
    "eleven_turbo_v2": 180.0,
    "eleven_multilingual_v2": 300.0,
    "eleven_monolingual_v1": 300.0,
}


def estimate_elevenlabs_tts_cost_usd(model: str, text: str) -> float:
    rate = ELEVENLABS_RATES_PER_1M_CHARS.get(model, 180.0)
    return len(text) * rate / 1_000_000


# Speech-to-text: billed per minute of audio (OpenAI standard tier).
STT_USD_PER_MINUTE: dict[str, float] = {
    "whisper-1": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-transcribe-diarize": 0.006,
}


def estimate_stt_cost_usd(model: str, audio_duration_s: float) -> float:
    """Estimate transcription cost from recorded utterance length."""
    rate = STT_USD_PER_MINUTE.get(model, 0.006)
    minutes = max(audio_duration_s, 0.0) / 60.0
    return minutes * rate


# OpenAI hosted web_search tool (Responses API): $10 / 1,000 search actions.
WEB_SEARCH_USD_PER_CALL = 0.01

# gpt-4o-mini / gpt-4.1-mini: search content billed as ~8k input tokens per search.
WEB_SEARCH_CONTENT_INPUT_TOKENS_MINI = 8000


def estimate_web_search_tool_cost_usd(search_calls: int = 1) -> float:
    return max(1, search_calls) * WEB_SEARCH_USD_PER_CALL


def estimate_web_search_content_fallback_usd(model: str, search_calls: int = 1) -> float:
    """When Responses API usage is missing, approximate search-content tokens."""
    calls = max(1, search_calls)
    if "mini" not in model.lower():
        return 0.0
    input_rate = MODEL_RATES.get(model, (0.15, 0.60))[0]
    return calls * WEB_SEARCH_CONTENT_INPUT_TOKENS_MINI * input_rate / 1_000_000


def estimate_web_search_cost_usd(model: str, search_calls: int = 1) -> float:
    """Tool fee + typical content block (use API usage when available instead)."""
    return estimate_web_search_tool_cost_usd(search_calls) + estimate_web_search_content_fallback_usd(
        model, search_calls
    )
