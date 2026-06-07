from __future__ import annotations

import io
import logging
import os
import re
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from aicoach.elevenlabs_client import (
    DEFAULT_OUTPUT_FORMAT,
    ElevenLabsError,
    synthesize_speech,
)
from aicoach.openai_client import build_openai_client

from aicoach.config import Settings
from aicoach.pricing import estimate_elevenlabs_tts_cost_usd, estimate_tts_cost_usd
from aicoach.response_parse import clean_spoken_output

logger = logging.getLogger(__name__)

DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel
PREVIEW_SAMPLE_TEXT = "Hey — I'm your Tiltproof coach. Let's keep you sharp and tilt-free."


@dataclass(frozen=True)
class TTSResult:
    characters: int
    estimated_usd: float
    playback_seconds: float
    api_seconds: float = 0.0
    play_seconds: float = 0.0
    interrupted: bool = False


class SpeechSynthesizer(Protocol):
    def speak(
        self,
        text: str,
        *,
        stop_check: Callable[[], bool] | None = None,
    ) -> TTSResult: ...


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


def pcm_to_wav(pcm: bytes, *, sample_rate: int = 44100, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def write_pcm_wav_file(path: Path, pcm: bytes, *, sample_rate: int = 44100) -> None:
    path.write_bytes(pcm_to_wav(pcm, sample_rate=sample_rate))


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


def _poll_playback(
    proc: object | None,
    *,
    duration_s: float,
    stop_check: Callable[[], bool] | None,
    poll_interval_s: float,
    on_interrupt: Callable[[], None],
    is_done: Callable[[], bool] | None = None,
) -> bool:
    import subprocess
    import time

    deadline = time.monotonic() + duration_s + 2.0
    try:
        while time.monotonic() < deadline:
            if stop_check and stop_check():
                if isinstance(proc, subprocess.Popen):
                    proc.terminate()
                else:
                    on_interrupt()
                logger.info("TTS playback interrupted (barge-in)")
                return False
            if isinstance(proc, subprocess.Popen):
                if proc.poll() is not None:
                    return proc.returncode == 0
            elif is_done and is_done():
                return True
            time.sleep(poll_interval_s)
        if isinstance(proc, subprocess.Popen):
            proc.terminate()
        else:
            on_interrupt()
        return False
    finally:
        if isinstance(proc, subprocess.Popen) and proc.poll() is None:
            proc.terminate()


def _estimate_mp3_duration_s(path: Path) -> float:
    # mp3_44100_128 ≈ 16 KB/s payload; add headroom for ID3/container.
    return path.stat().st_size / 16_000 + 1.0


# Windows MCI (winmm) decodes MP3 natively, so we avoid the `playsound` package
# (which on Windows only handles WAV) and the frozen-exe footgun of spawning
# `sys.executable -c "..."` (a PyInstaller build relaunches itself instead of
# running inline Python). The script is run via a temp .ps1 with -File to avoid
# command-line quoting issues with the embedded C# / quoted MCI path. PowerShell
# ships on every supported Windows version. The audio path is passed via the
# AICOACH_TTS_PATH env var, and a non-zero MCI "open" result exits non-zero so
# the caller can detect playback failure.
_WIN_MP3_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$p = $env:AICOACH_TTS_PATH
Add-Type -Namespace TP -Name MCI -MemberDefinition '[DllImport("winmm.dll", CharSet=CharSet.Auto)] public static extern int mciSendString(string c, System.Text.StringBuilder b, int s, System.IntPtr h);'
$buf = New-Object System.Text.StringBuilder 256
if ([TP.MCI]::mciSendString('open "' + $p + '" type mpegvideo alias tpaudio', $buf, 256, [System.IntPtr]::Zero) -ne 0) { exit 1 }
[void][TP.MCI]::mciSendString('play tpaudio wait', $buf, 256, [System.IntPtr]::Zero)
[void][TP.MCI]::mciSendString('close tpaudio', $buf, 256, [System.IntPtr]::Zero)
"""

_win_mp3_script_path: Path | None = None


def _win_mp3_script() -> Path:
    global _win_mp3_script_path
    if _win_mp3_script_path is None or not _win_mp3_script_path.exists():
        path = Path(tempfile.gettempdir()) / "tiltproof_play_mp3.ps1"
        path.write_text(_WIN_MP3_PS_SCRIPT, encoding="utf-8")
        _win_mp3_script_path = path
    return _win_mp3_script_path


def play_mp3_file(
    path: Path,
    *,
    stop_check: Callable[[], bool] | None = None,
    poll_interval_s: float = 0.03,
) -> bool:
    """Play MP3 in a child process so playback can be killed without touching the mic stream."""
    import shutil
    import subprocess
    import sys

    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError(f"TTS audio file missing or too small: {path}")

    duration_s = _estimate_mp3_duration_s(path)
    env = {**os.environ, "AICOACH_TTS_PATH": str(path)}

    if sys.platform == "win32":
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_win_mp3_script()),
            ],
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _poll_playback(proc, duration_s=duration_s, stop_check=stop_check, poll_interval_s=poll_interval_s, on_interrupt=lambda: None)

    # Other platforms: use playsound via a real interpreter. In a frozen build
    # `sys.executable` is the bundled engine, so fall back to a system Python.
    python = sys.executable
    if getattr(sys, "frozen", False):
        python = shutil.which("python3") or shutil.which("python") or python
    proc = subprocess.Popen(
        [
            python,
            "-c",
            "import os; from playsound import playsound; playsound(os.environ['AICOACH_TTS_PATH'], block=True)",
        ],
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return _poll_playback(proc, duration_s=duration_s, stop_check=stop_check, poll_interval_s=poll_interval_s, on_interrupt=lambda: None)


def play_wav_file(
    path: Path,
    *,
    stop_check: Callable[[], bool] | None = None,
    poll_interval_s: float = 0.03,
) -> bool:
    """
    Play WAV without holding the PortAudio input device (mic uses sounddevice).

    On Windows we spawn a separate PowerShell SoundPlayer process so TTS does not
    share the same audio backend as the mic capture stream.
    """
    import subprocess
    import sys
    import sounddevice as sd

    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError(f"TTS audio file missing or too small: {path}")

    samples, sample_rate = _load_wav_mono(path)
    if samples.size == 0:
        return True

    duration_s = len(samples) / sample_rate + 0.25

    if sys.platform == "win32":
        escaped = str(path).replace("'", "''")
        proc = subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(New-Object System.Media.SoundPlayer '{escaped}').PlaySync()",
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _poll_playback(proc, duration_s=duration_s, stop_check=stop_check, poll_interval_s=poll_interval_s, on_interrupt=lambda: None)

    audio = samples.astype(np.float32) / 32768.0
    sd.play(audio, sample_rate, blocking=False)

    def stream_finished() -> bool:
        stream = sd.get_stream()
        return stream is None or not stream.active

    try:
        return _poll_playback(
            proc=None,
            duration_s=duration_s,
            stop_check=stop_check,
            poll_interval_s=poll_interval_s,
            on_interrupt=sd.stop,
            is_done=stream_finished,
        )
    finally:
        sd.stop()


def play_audio_file(
    path: Path,
    *,
    stop_check: Callable[[], bool] | None = None,
    poll_interval_s: float = 0.03,
) -> bool:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return play_mp3_file(path, stop_check=stop_check, poll_interval_s=poll_interval_s)
    return play_wav_file(path, stop_check=stop_check, poll_interval_s=poll_interval_s)


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


class ElevenLabsTTS:
    """ElevenLabs speech API with interruptible playback."""

    def __init__(
        self,
        *,
        voice_id: str,
        model_id: str = "eleven_turbo_v2_5",
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> None:
        self._voice_id = voice_id
        self._model_id = model_id
        self._output_format = output_format

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

        estimated = estimate_elevenlabs_tts_cost_usd(self._model_id, spoken)
        logger.info(
            "TTS (ElevenLabs %s, voice=%s): %s chars (~$%.4f)",
            self._model_id,
            self._voice_id,
            len(spoken),
            estimated,
        )

        started = time.monotonic()
        suffix = ".mp3" if self._output_format.startswith("mp3") else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            audio_path = Path(tmp.name)

        api_s = 0.0
        play_s = 0.0
        interrupted = False
        try:
            api_started = time.monotonic()
            audio = synthesize_speech(
                spoken,
                voice_id=self._voice_id,
                model_id=self._model_id,
                output_format=self._output_format,
            )
            audio_path.write_bytes(audio)
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
        except ElevenLabsError:
            logger.exception("ElevenLabs TTS failed")
            raise
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


def synthesize_preview_audio(
    *,
    voice_id: str,
    model_id: str,
    text: str = PREVIEW_SAMPLE_TEXT,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> tuple[bytes, str]:
    spoken = prepare_text_for_speech(text, max_chars=400)
    audio = synthesize_speech(
        spoken,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )
    if output_format.startswith("mp3"):
        return audio, "audio/mpeg"
    return pcm_to_wav(audio), "audio/wav"


def build_tts(settings: Settings) -> SpeechSynthesizer | None:
    if not settings.tts_enabled:
        return None
    provider = settings.tts_provider.strip().lower()
    if provider == "openai":
        return OpenAITTS(
            settings.openai_api_key,
            model=settings.tts_model,
            voice=settings.tts_voice,
        )
    if provider == "elevenlabs":
        return ElevenLabsTTS(
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model,
            output_format=settings.elevenlabs_output_format,
        )
    raise ValueError(f"Unknown TTS_PROVIDER: {settings.tts_provider!r}")
