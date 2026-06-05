from __future__ import annotations

import io
import logging
import time

from aicoach.openai_client import build_openai_client

from aicoach.pricing import estimate_stt_cost_usd
from aicoach.voice.audio import SAMPLE_RATE, frames_to_wav_bytes

logger = logging.getLogger(__name__)


def transcribe_utterance(
    api_key: str,
    pcm_chunks: list[bytes],
    *,
    model: str = "whisper-1",
) -> tuple[str, float, float]:
    """
    Transcribe mic audio with OpenAI speech-to-text.
    Returns (text, api_seconds, estimated_usd).
    """
    wav_bytes = frames_to_wav_bytes(pcm_chunks, sample_rate=SAMPLE_RATE)
    total_samples = sum(len(c) for c in pcm_chunks) // 2
    audio_duration_s = total_samples / SAMPLE_RATE if total_samples else 0.0
    started = time.monotonic()

    client = build_openai_client(api_key)
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "utterance.wav"

    result = client.audio.transcriptions.create(
        model=model,
        file=audio_file,
        language="en",
    )
    text = (result.text or "").strip()
    elapsed = time.monotonic() - started
    cost = estimate_stt_cost_usd(model, audio_duration_s)
    logger.info(
        "STT (%s): %.1fs API, ~%.1fs audio, ~$%.4f — %r",
        model,
        elapsed,
        audio_duration_s,
        cost,
        text[:120],
    )
    return text, elapsed, cost
