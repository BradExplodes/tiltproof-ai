from __future__ import annotations

import logging
import re
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from aicoach.openai_client import build_openai_client

from aicoach.pricing import estimate_tts_cost_usd
from aicoach.response_parse import clean_spoken_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TTSResult:
    characters: int
    estimated_usd: float
    playback_seconds: float
    api_seconds: float = 0.0
    play_seconds: float = 0.0
    interrupted: bool = False


def prepare_text_for_speech(text: str, max_chars: int = 1200) -> str:
    """Strip markdown, brackets, and cap length so TTS sounds natural."""
    cleaned = clean_spoken_output(text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[\s]*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3].rsplit(" ", 1)[0] + "..."
    return cleaned


def _load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if sample_width != 2:
        raise RuntimeError(f"Unsupported WAV sample width: {sample_width}")
    samples = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return samples, sample_rate


def play_audio_file(
    path: Path,
    *,
    stop_check: Callable[[], bool] | None = None,
    poll_interval_s: float = 0.03,
) -> bool:
    """
    Play WAV via sounddevice. Returns True if played to end, False if interrupted.
    """
    import sounddevice as sd

    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError(f"TTS audio file missing or too small: {path}")

    samples, sample_rate = _load_wav_mono(path)
    if samples.size == 0:
        return True

    audio = samples.astype(np.float32) / 32768.0
    sd.play(audio, sample_rate, blocking=False)
    try:
        deadline = time.monotonic() + len(samples) / sample_rate + 2.0
        while time.monotonic() < deadline:
            if stop_check and stop_check():
                sd.stop()
                logger.info("TTS playback interrupted (queued speech)")
                return False
            stream = sd.get_stream()
            if stream is None or not stream.active:
                return True
            time.sleep(poll_interval_s)
        sd.stop()
        return False
    finally:
        sd.stop()


class OpenAITTS:
    """OpenAI speech API with interruptible playback."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "tts-1",
        voice: str = "ash",
    ) -> None:
        self._client = build_openai_client(api_key)
        self._model = model
        self._voice = voice

    def speak(
        self,
        text: str,
        *,
        stop_check: Callable[[], bool] | None = None,
    ) -> TTSResult:
        spoken = prepare_text_for_speech(text)
        if not spoken:
            logger.warning("Empty TTS text; skipping playback")
            return TTSResult(
                characters=0,
                estimated_usd=0.0,
                playback_seconds=0.0,
                api_seconds=0.0,
                play_seconds=0.0,
            )

        estimated = estimate_tts_cost_usd(self._model, spoken)
        logger.info(
            "TTS (%s, voice=%s): %s chars (~$%.4f)",
            self._model,
            self._voice,
            len(spoken),
            estimated,
        )

        started = time.monotonic()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = Path(tmp.name)

        api_s = 0.0
        play_s = 0.0
        interrupted = False
        try:
            api_started = time.monotonic()
            response = self._client.audio.speech.create(
                model=self._model,
                voice=self._voice,
                input=spoken,
                response_format="wav",
            )
            response.stream_to_file(audio_path)
            api_s = time.monotonic() - api_started
            logger.info(
                "TTS audio received in %.1fs (%s bytes) — playing",
                api_s,
                audio_path.stat().st_size,
            )
            play_started = time.monotonic()
            completed = play_audio_file(audio_path, stop_check=stop_check)
            play_s = time.monotonic() - play_started
            interrupted = not completed
            if interrupted:
                logger.debug("TTS playback stopped after %.1fs", play_s)
        finally:
            audio_path.unlink(missing_ok=True)

        playback = time.monotonic() - started
        return TTSResult(
            characters=len(spoken),
            estimated_usd=estimated,
            playback_seconds=playback,
            api_seconds=api_s,
            play_seconds=play_s,
            interrupted=interrupted,
        )
