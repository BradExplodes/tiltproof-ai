from __future__ import annotations

import io
import wave
from typing import Iterable

import numpy as np

SAMPLE_RATE = 16_000


def pcm_rms(pcm_int16: bytes) -> float:
    """Root-mean-square level for int16 PCM, normalized 0–1."""
    if len(pcm_int16) < 2:
        return 0.0
    samples = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return 0.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    return rms / 32768.0


def frames_to_wav_bytes(chunks: Iterable[bytes], sample_rate: int = SAMPLE_RATE) -> bytes:
    """Build an in-memory WAV from int16 mono chunks."""
    pcm = b"".join(chunks)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buffer.getvalue()
