from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

from aicoach.voice.audio import SAMPLE_RATE, pcm_rms

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicUtterance:
    """Completed speech segment from the microphone."""

    pcm_chunks: list[bytes]
    duration_s: float
    peak_rms: float


class VoiceListener:
    """
    RMS-gated mic capture. The input stream is opened only while the runner
    requests it — avoids PortAudio contention with TTS during capture/think/STT.
    """

    def __init__(
        self,
        *,
        min_rms: float = 0.018,
        silence_ms: int = 1500,
        min_speech_ms: int = 350,
        barge_speech_ms: int = 1500,
        max_utterance_s: float = 25.0,
        block_ms: int = 30,
    ) -> None:
        if not 0 < min_rms < 1:
            raise ValueError("min_rms must be between 0 and 1")
        self._min_rms = min_rms
        self._barge_min_rms = min(min_rms * 1.5, 0.14)
        self._barge_silence_ms = max(600, silence_ms // 2)
        self._silence_ms = silence_ms
        self._min_speech_ms = min_speech_ms
        self._barge_speech_ms = max(500, barge_speech_ms)
        self._max_utterance_s = max_utterance_s
        self._block_ms = block_ms
        self._block_samples = int(SAMPLE_RATE * block_ms / 1000)

        self._queue: queue.Queue[MicUtterance] = queue.Queue()
        self._coach_speaking = threading.Event()
        self._barge_in = threading.Event()
        self._user_speaking = threading.Event()
        self._mic_active = threading.Event()
        self._mic_active.set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="voice-listener",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Voice listener on (min RMS %.3f, silence %dms, min speech %dms)",
            self._min_rms,
            self._silence_ms,
            self._min_speech_ms,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None

    def set_mic_active(self, active: bool) -> None:
        """Close the mic device while inactive (capture / STT / thinking)."""
        if active:
            self._mic_active.set()
        else:
            self._mic_active.clear()

    def set_coach_speaking(self, active: bool) -> None:
        if active:
            self._barge_in.clear()
            self._coach_speaking.set()
        else:
            self._coach_speaking.clear()

    def is_coach_speaking(self) -> bool:
        return self._coach_speaking.is_set()

    def barge_in_requested(self) -> bool:
        return self._barge_in.is_set()

    def consume_barge_in(self) -> bool:
        if self._barge_in.is_set():
            self._barge_in.clear()
            return True
        return False

    def is_user_speaking(self) -> bool:
        return self._user_speaking.is_set()

    def poll(self) -> MicUtterance | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def wait(self, timeout: float) -> MicUtterance | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def pending_count(self) -> int:
        return self._queue.qsize()

    def _capture_loop(self) -> None:
        import sounddevice as sd

        blocksize = self._block_samples
        silence_blocks_needed = max(1, self._silence_ms // self._block_ms)
        barge_silence_blocks = max(1, self._barge_silence_ms // self._block_ms)
        min_speech_blocks = max(1, self._min_speech_ms // self._block_ms)
        barge_speech_blocks_needed = max(1, self._barge_speech_ms // self._block_ms)
        max_blocks = int(self._max_utterance_s * 1000 / self._block_ms)

        in_utterance = False
        chunks: list[bytes] = []
        speech_blocks = 0
        silence_blocks = 0
        barge_loud_blocks = 0
        peak_rms = 0.0
        utterance_start = 0.0

        while not self._stop.is_set():
            if not self._mic_active.is_set():
                time.sleep(0.05)
                continue

            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=blocksize,
            ) as stream:
                while not self._stop.is_set() and self._mic_active.is_set():
                    data, _overflowed = stream.read(blocksize)
                    pcm = bytes(data)
                    level = pcm_rms(pcm)
                    loud = level >= self._min_rms
                    loud_for_barge = level >= self._barge_min_rms

                    if loud:
                        if not in_utterance:
                            in_utterance = True
                            utterance_start = time.monotonic()
                            chunks = []
                            speech_blocks = 0
                            silence_blocks = 0
                            barge_loud_blocks = 0
                            peak_rms = 0.0
                        self._user_speaking.set()
                        peak_rms = max(peak_rms, level)
                        chunks.append(pcm)
                        speech_blocks += 1
                        silence_blocks = 0
                        if self._coach_speaking.is_set() and loud_for_barge:
                            barge_loud_blocks += 1
                            if (
                                barge_loud_blocks >= barge_speech_blocks_needed
                                and not self._barge_in.is_set()
                            ):
                                self._barge_in.set()
                                logger.info("Barge-in: speech above threshold")
                        if len(chunks) >= max_blocks:
                            self._finish_utterance(
                                chunks,
                                speech_blocks,
                                min_speech_blocks,
                                peak_rms,
                                utterance_start,
                            )
                            in_utterance = False
                            chunks = []
                            barge_loud_blocks = 0
                            self._user_speaking.clear()
                    elif in_utterance:
                        chunks.append(pcm)
                        silence_blocks += 1
                        end_silence_blocks = (
                            barge_silence_blocks
                            if self._coach_speaking.is_set()
                            else silence_blocks_needed
                        )
                        if silence_blocks >= end_silence_blocks:
                            self._finish_utterance(
                                chunks,
                                speech_blocks,
                                min_speech_blocks,
                                peak_rms,
                                utterance_start,
                            )
                            in_utterance = False
                            chunks = []
                            barge_loud_blocks = 0
                            self._user_speaking.clear()
                    else:
                        barge_loud_blocks = 0
                        self._user_speaking.clear()

    def _finish_utterance(
        self,
        chunks: list[bytes],
        speech_blocks: int,
        min_speech_blocks: int,
        peak_rms: float,
        utterance_start: float,
    ) -> None:
        if speech_blocks < min_speech_blocks:
            logger.debug(
                "Dropped short utterance (%.0fms speech, peak RMS %.4f)",
                speech_blocks * self._block_ms,
                peak_rms,
            )
            return

        duration = time.monotonic() - utterance_start
        logger.info("Utterance captured %.1fs (peak RMS %.3f)", duration, peak_rms)
        self._queue.put(
            MicUtterance(
                pcm_chunks=list(chunks),
                duration_s=duration,
                peak_rms=peak_rms,
            )
        )
        if self._coach_speaking.is_set():
            self._barge_in.set()
            logger.info("Barge-in: speech queued during coach TTS")
