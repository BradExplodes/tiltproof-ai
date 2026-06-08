from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from aicoach.paths import app_dir

_APP_DIR = app_dir()
load_dotenv(_APP_DIR / ".env")
load_dotenv()  # allow overrides from current working directory


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_describe_model: str
    player_name: str
    capture_interval_seconds: float
    save_screenshots: bool
    image_detail: str
    capture_max_width: int
    capture_jpeg_quality: int
    describe_max_tokens: int
    tts_enabled: bool
    tts_provider: str
    tts_model: str
    tts_voice: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    elevenlabs_output_format: str
    post_speech_delay_seconds: float
    tts_barge_grace_seconds: float
    max_history_messages: int
    coach_temperature: float
    web_search_enabled: bool
    web_search_model: str
    web_search_context_size: str
    web_search_scenes: frozenset[str]
    screenshots_dir: Path
    voice_input_enabled: bool
    voice_min_rms: float
    voice_silence_ms: int
    voice_min_speech_ms: int
    voice_barge_speech_ms: int
    voice_max_utterance_seconds: float
    voice_stt_model: str
    ocr_enabled: bool
    ocr_language: str
    ocr_engine: str
    tesseract_cmd: str | None
    tesseract_config: str
    ocr_scale_factor: float
    ocr_preprocess_mode: str
    ocr_multi_psm: bool
    ocr_max_width: int
    ocr_voice_fast: bool
    ocr_save_screenshots: bool
    ocr_debug_save: bool
    ocr_capture_full_quality: bool

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        # In proxy mode the desktop app supplies a session token instead of a raw
        # OpenAI key; the real key lives on the backend. Accept that as the credential.
        proxy_base = os.getenv("AICOACH_OPENAI_BASE_URL", "").strip()
        proxy_token = os.getenv("AICOACH_PROXY_TOKEN", "").strip()
        if not api_key:
            if proxy_base and proxy_token:
                api_key = proxy_token
            else:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
                )

        player_name = os.getenv("PLAYER_NAME", "").strip()[:60]

        interval = float(os.getenv("CAPTURE_INTERVAL_SECONDS", "20"))
        if interval < 1:
            raise ValueError("CAPTURE_INTERVAL_SECONDS must be at least 1.")

        image_detail = os.getenv("IMAGE_DETAIL", "high").strip().lower()
        if image_detail not in ("low", "high"):
            raise ValueError("IMAGE_DETAIL must be 'low' or 'high'.")

        capture_max_width = int(os.getenv("CAPTURE_MAX_WIDTH", "1280"))
        if capture_max_width < 640:
            raise ValueError("CAPTURE_MAX_WIDTH must be at least 640.")

        capture_jpeg_quality = int(os.getenv("CAPTURE_JPEG_QUALITY", "82"))
        if not 0 <= capture_jpeg_quality <= 95:
            raise ValueError("CAPTURE_JPEG_QUALITY must be 0 (PNG) or 1–95.")

        describe_max_tokens = int(os.getenv("DESCRIBE_MAX_TOKENS", "900"))
        if describe_max_tokens < 150:
            raise ValueError("DESCRIBE_MAX_TOKENS must be at least 150.")

        post_speech_delay = float(os.getenv("POST_SPEECH_DELAY_SECONDS", "8"))
        if post_speech_delay < 0:
            raise ValueError("POST_SPEECH_DELAY_SECONDS must be >= 0.")

        tts_barge_grace = float(os.getenv("TTS_BARGE_GRACE_SECONDS", "1.25"))
        if tts_barge_grace < 0:
            raise ValueError("TTS_BARGE_GRACE_SECONDS must be >= 0.")

        max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
        if max_history_messages < 0:
            raise ValueError("MAX_HISTORY_MESSAGES must be >= 0.")

        coach_temperature = float(os.getenv("COACH_TEMPERATURE", "0.8"))
        if not 0 <= coach_temperature <= 2:
            raise ValueError("COACH_TEMPERATURE must be between 0 and 2.")

        web_context = os.getenv("WEB_SEARCH_CONTEXT_SIZE", "medium").strip().lower()
        if web_context not in ("low", "medium", "high"):
            raise ValueError("WEB_SEARCH_CONTEXT_SIZE must be low, medium, or high.")

        scenes_raw = os.getenv("WEB_SEARCH_SCENES", "map_select,menu,results")
        web_scenes = frozenset(
            s.strip().lower() for s in scenes_raw.split(",") if s.strip()
        )

        screenshots_dir = _APP_DIR / "screenshots"
        response_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        describe_model = os.getenv("OPENAI_DESCRIBE_MODEL", response_model)

        voice_min_rms = float(os.getenv("VOICE_MIN_RMS", "0.028"))
        if not 0 < voice_min_rms < 1:
            raise ValueError("VOICE_MIN_RMS must be between 0 and 1 (e.g. 0.028).")

        voice_silence_ms = int(os.getenv("VOICE_SILENCE_MS", "1500"))
        if voice_silence_ms < 400:
            raise ValueError("VOICE_SILENCE_MS must be at least 400.")
        voice_min_speech_ms = int(os.getenv("VOICE_MIN_SPEECH_MS", "350"))
        voice_barge_speech_ms = int(os.getenv("VOICE_BARGE_SPEECH_MS", "1500"))
        if voice_barge_speech_ms < 500:
            raise ValueError("VOICE_BARGE_SPEECH_MS must be at least 500.")
        voice_max_utterance = float(os.getenv("VOICE_MAX_UTTERANCE_SECONDS", "25"))
        if voice_max_utterance < 2:
            raise ValueError("VOICE_MAX_UTTERANCE_SECONDS must be >= 2.")

        ocr_enabled = _env_bool("OCR_ENABLED", True)
        ocr_language = os.getenv("OCR_LANGUAGE", "en").strip() or "en"
        ocr_engine = os.getenv("OCR_ENGINE", "tesseract").strip().lower()
        if ocr_engine not in ("tesseract", "windows", "auto"):
            raise ValueError("OCR_ENGINE must be tesseract, windows, or auto.")
        tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip() or os.getenv(
            "OCR_TESSERACT_CMD", ""
        ).strip() or None
        tesseract_config = os.getenv(
            "OCR_TESSERACT_CONFIG", "--oem 3 --psm 11"
        ).strip()
        ocr_scale_factor = float(os.getenv("OCR_SCALE_FACTOR", "2"))
        if ocr_scale_factor < 1:
            raise ValueError("OCR_SCALE_FACTOR must be >= 1.")
        ocr_preprocess_mode = os.getenv("OCR_PREPROCESS_MODE", "game").strip().lower()
        if ocr_preprocess_mode not in (
            "none",
            "fast",
            "game",
            "game_fast",
            "balanced",
            "max",
            "pil",
            "opencv",
        ):
            raise ValueError(
                "OCR_PREPROCESS_MODE must be none, fast, game, game_fast, "
                "balanced, max, pil, or opencv."
            )
        ocr_multi_psm = _env_bool("OCR_MULTI_PSM", True)
        ocr_max_width = int(os.getenv("OCR_MAX_WIDTH", "1600"))
        if ocr_max_width < 640:
            raise ValueError("OCR_MAX_WIDTH must be at least 640.")
        ocr_voice_fast = _env_bool("OCR_VOICE_FAST", True)
        ocr_save_screenshots = _env_bool("OCR_SAVE_SCREENSHOTS", False)
        ocr_debug_save = _env_bool("OCR_DEBUG_SAVE", False)
        ocr_capture_full_quality = _env_bool("OCR_CAPTURE_FULL_QUALITY", True)
        return cls(
            openai_api_key=api_key,
            openai_model=response_model,
            openai_describe_model=describe_model,
            player_name=player_name,
            capture_interval_seconds=interval,
            save_screenshots=_env_bool("SAVE_SCREENSHOTS", False),
            image_detail=image_detail,
            capture_max_width=capture_max_width,
            capture_jpeg_quality=capture_jpeg_quality,
            describe_max_tokens=describe_max_tokens,
            tts_enabled=_env_bool("TTS_ENABLED", True),
            tts_provider=os.getenv("TTS_PROVIDER", "elevenlabs").strip().lower(),
            tts_model=os.getenv("TTS_MODEL", "tts-1"),
            tts_voice=os.getenv("TTS_VOICE", "ash"),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
            elevenlabs_model=os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5"),
            elevenlabs_output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
            post_speech_delay_seconds=post_speech_delay,
            tts_barge_grace_seconds=tts_barge_grace,
            max_history_messages=max_history_messages,
            coach_temperature=coach_temperature,
            web_search_enabled=_env_bool("WEB_SEARCH_ENABLED", True),
            web_search_model=os.getenv("WEB_SEARCH_MODEL", "gpt-4o-mini"),
            web_search_context_size=web_context,
            web_search_scenes=web_scenes,
            screenshots_dir=screenshots_dir,
            voice_input_enabled=_env_bool("VOICE_INPUT_ENABLED", True),
            voice_min_rms=voice_min_rms,
            voice_silence_ms=voice_silence_ms,
            voice_min_speech_ms=voice_min_speech_ms,
            voice_barge_speech_ms=voice_barge_speech_ms,
            voice_max_utterance_seconds=voice_max_utterance,
            voice_stt_model=os.getenv("VOICE_STT_MODEL", "whisper-1"),
            ocr_enabled=ocr_enabled,
            ocr_language=ocr_language,
            ocr_engine=ocr_engine,
            tesseract_cmd=tesseract_cmd,
            tesseract_config=tesseract_config,
            ocr_scale_factor=ocr_scale_factor,
            ocr_preprocess_mode=ocr_preprocess_mode,
            ocr_multi_psm=ocr_multi_psm,
            ocr_max_width=ocr_max_width,
            ocr_voice_fast=ocr_voice_fast,
            ocr_save_screenshots=ocr_save_screenshots,
            ocr_debug_save=ocr_debug_save,
            ocr_capture_full_quality=ocr_capture_full_quality,
        )
