from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CycleTimings:
    """Wall-clock seconds per pipeline step (monotonic clock)."""

    capture_s: float = 0.0
    describe_s: float = 0.0
    screen_read_method: str = ""
    ocr_preview: str = ""
    coach_s: float = 0.0
    coach_api_calls: int = 0
    web_augment_s: float | None = None
    map_intel_note: str = ""
    analysis_s: float = 0.0
    stt_s: float | None = None
    stt_usd: float | None = None
    tts_api_s: float | None = None
    tts_play_s: float | None = None
    post_speech_wait_s: float | None = None
    interval_wait_s: float | None = None
    cycle_total_s: float | None = None
    extra: list[str] = field(default_factory=list)

    def format_lines(self) -> list[str]:
        lines = ["--- Timing ---"]

        def row(label: str, seconds: float | None, detail: str = "") -> None:
            if seconds is None:
                return
            suffix = f" ({detail})" if detail else ""
            lines.append(f"  {label}: {seconds:.2f}s{suffix}")

        row("screenshot capture", self.capture_s)
        if self.screen_read_method == "ocr":
            row("OCR (Tesseract)", self.describe_s)
        elif self.screen_read_method == "ocr+vision":
            row("OCR then vision fallback", self.describe_s)
        else:
            row("vision describe", self.describe_s)
        if self.map_intel_note:
            lines.append(f"  map intel: {self.map_intel_note}")
        row("coach text", self.coach_s, f"{self.coach_api_calls} API call(s)")
        row("web augment", self.web_augment_s)
        row("analysis total", self.analysis_s)
        if self.stt_s is not None:
            stt_detail = f"~${self.stt_usd:.4f}" if self.stt_usd is not None else ""
            row("speech-to-text", self.stt_s, stt_detail.strip())
        row("TTS API", self.tts_api_s)
        row("TTS playback", self.tts_play_s)
        row("post-speech wait", self.post_speech_wait_s)
        row("until next capture", self.interval_wait_s)
        row("cycle total", self.cycle_total_s)
        for note in self.extra:
            lines.append(f"  {note}")
        lines.append("---")
        return lines
