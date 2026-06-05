# AI Coach

Desktop AI coach for gaming. Captures your screen on a fixed interval (~10 seconds by default), sends each frame to OpenAI vision with a **game-specific prompt**, and prints actionable coaching advice to the terminal.

This repo is the **core engine** only â€” no UI yet. A desktop shell (Electron, Tauri, etc.) can call the same Python modules or subprocess later.

## Requirements

- Python 3.10+
- Windows, macOS, or Linux
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to a vision-capable model (default: `gpt-4o-mini`)

## Setup

```powershell
cd "c:\Users\survi\Documents\Cursor Projects\aicoach"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

# Tesseract OCR (default for voice HUD/map reads)
winget install UB-Mannheim.TesseractOCR
```

Copy `.env.example` to `.env` and add your OpenAI API key (`.env` is gitignored).

```powershell
copy .env.example .env
```

## Windows executable

### Build / rebuild the exe and `.bat` launchers

Whenever you change Python code, run this from the **project root**:

```powershell
cd "c:\Users\survi\Documents\Cursor Projects\aicoach"
.\scripts\build-exe.ps1
```

That script will:

1. Install/update dependencies in `.venv`
2. Run PyInstaller â†’ writes **`dist\aicoach.exe`**
3. Copy your root **`.env`** â†’ **`dist\.env`**
4. Regenerate **`dist\run-*.bat`** (LoL, VALORANT, Deadlock, osu!)

You only need to rebuild after code changes â€” editing `.env` alone does not require a rebuild (just keep `dist\.env` in sync or re-run the script).

### Run the packaged app

Output in `dist/`:

| File | Purpose |
|------|---------|
| `aicoach.exe` | CLI â€” same flags as `python -m aicoach` |
| `run-league-of-legends.bat` | Double-click launcher (LoL) |
| `run-valorant.bat` | Double-click launcher |
| `run-deadlock.bat` | Double-click launcher |
| `run-osu.bat` | Double-click launcher (osu!) |
| `.env` | Copied from project root if present; otherwise copy from `.env.example` |

Put `.env` in the **same folder as `aicoach.exe`** (the build script tries to copy it automatically). Example:

```powershell
cd dist
.\aicoach.exe --game valorant
# or double-click run-valorant.bat
```

## Run

```powershell
# League of Legends
python -m aicoach --game league-of-legends

# VALORANT, 15 second interval
python -m aicoach --game valorant --interval 15

# Deadlock, save captures for debugging
python -m aicoach --game deadlock --save-screenshots -v

# osu!
python -m aicoach --game osu
```

List supported games:

```powershell
python -m aicoach --list-games
```

Press **Ctrl+C** to stop.

### Which runner to use?

| Method | When to use |
|--------|-------------|
| **`run-osu-dev.bat`** (project root) | Latest code from source â€” best while developing |
| **`dist\run-osu.bat`** | Packaged exe â€” run `.\scripts\build-exe.ps1` after code changes |
| **Python** | `.\.venv\Scripts\python -m aicoach --game osu` |

The `.bat` files in `dist\` only launch `aicoach.exe`; they do not contain app logic. If behavior looks old, **rebuild the exe** and ensure `dist\.env` has `TTS_ENABLED=true` (the build script copies your root `.env`).

**New build startup log** should say: `TTS voice=ash, delay after speech=4.0s` â€” if you still see `capture every 10.0s`, you are on an old exe.

## Supported games

| CLI id | Prompt file |
|--------|-------------|
| `league-of-legends` | `src/aicoach/prompts/league_of_legends.md` |
| `valorant` | `src/aicoach/prompts/valorant.md` |
| `deadlock` | `src/aicoach/prompts/deadlock.md` |
| `osu` | `src/aicoach/prompts/osu.md` |

Add a game by creating a new `.md` file under `src/aicoach/prompts/` and registering it in `src/aicoach/prompts/__init__.py`.

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | Vision model (`gpt-4o` for higher quality) |
| `CAPTURE_INTERVAL_SECONDS` | `10` | Seconds between screenshots |
| `SAVE_SCREENSHOTS` | `false` | Persist PNGs under `screenshots/` |
| `IMAGE_DETAIL` | `high` | `high` = sharper HUD read; `low` = faster describe |
| `CAPTURE_MAX_WIDTH` | `1280` | Max width before upload (was 1920; smaller = faster) |
| `CAPTURE_JPEG_QUALITY` | `82` | JPEG 1â€“95; `0` = PNG (larger uploads) |
| `DESCRIBE_MAX_TOKENS` | `450` | Max tokens for vision describe pass |
| `OCR_ENABLED` | `true` | Voice text reads use OCR |
| `OCR_ENGINE` | `tesseract` | `tesseract`, `windows`, or `auto` |
| `OCR_LANGUAGE` | `en` | `en` maps to Tesseract `eng` |
| `TESSERACT_CMD` | *(auto)* | Path to `tesseract.exe` if not on PATH |
| *(no token cap)* | â€” | Reply length is controlled by the prompt (~2â€“4 sentences), not `max_tokens` |
| `TTS_ENABLED` | `true` | Speak advice with OpenAI TTS (voice `ash`) |
| `TTS_MODEL` | `tts-1` | `tts-1-hd` for higher quality (2Ã— price) |
| `TTS_VOICE` | `ash` | OpenAI speech voice |
| `POST_SPEECH_DELAY_SECONDS` | `4` | Wait after audio ends before next screenshot |

**Timing:** There is **no deliberate delay before TTS** â€” speech starts as soon as vision + coach finish (map web research on song select runs **in the background** so it does not block audio). What feels like â€œlateâ€ TTS is usually stacked API time (screenshot describe ~3â€“8s with fast settings, or ~12â€“20s with `IMAGE_DETAIL=high` + large PNG). **`POST_SPEECH_DELAY_SECONDS`** (default 8s) runs **after** audio finishes, before the next capture â€” lower it in `.env` if you want quicker cycles (e.g. `2`). Console text prints **before** TTS plays; check logs for `Coach ready in Xs`, `Vision request: â€¦ image=XXXkB`, and `TTS audio received in Xs`.

**Vision speed** â€” Most of the ~18s you may see is the OpenAI vision call, not local capture. Biggest levers (in order):

1. **`IMAGE_DETAIL=high`** (default) for readable HUD; use `low` if speed matters more.
2. **`CAPTURE_MAX_WIDTH=1280`** + **JPEG** (defaults; old builds used 1920 PNG).
3. **`DESCRIBE_MAX_TOKENS=350`** if you only need short HUD notes.
4. **`OPENAI_DESCRIBE_MODEL=gpt-4o-mini`** â€” already fast; `gpt-4o` is slower but reads tiny text better.

You cannot get vision to â€œinstantâ€ â€” there is always network + model time â€” but **~4â€“8s** describe is realistic with `low` detail. **`high` at 1920px** is the slow path and is mainly for debugging HUD readability.

**Memory:** The coach only recalls your last few **spoken lines** (not old screenshots), so it does not â€œdiffâ€ prior observations and decide nothing changed. Prompts forbid `SAY: NONE` and â€œnothing new happenedâ€ reasoning; during gameplay a fallback line is used if the model still stays quiet.

## Screen read (Tesseract OCR + vision)

| When | Method |
|------|--------|
| **Idle screen cycle** (~20s) | OpenAI **vision** |
| **Voice after >=20s** without a screenshot | **Vision** |
| **Voice -- map/HUD questions** | **Tesseract OCR** |
| **Voice -- profile pic / visual** | **Vision** |
| **OCR sparse or fails** | Vision fallback |

Default **`OCR_ENGINE=tesseract`** ([pytesseract](https://github.com/madmaze/pytesseract) + [Tesseract](https://github.com/tesseract-ocr/tesseract)). Screenshots are upscaled/grayscale/contrast-boosted before OCR.

```powershell
winget install UB-Mannheim.TesseractOCR
```

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_TESSERACT_CONFIG=--psm 6
```

`OCR_ENGINE=auto` tries Tesseract then Windows OCR (`winocr`). See `.env.example`.

## Architecture (two-stage)

```
Screenshot
  â†’ Stage 1: Windows OCR (text/HUD) or VISION when needed (facts only)
  â†’ Stage 2 TEXT: friend/coach reply from that written observation (+ memory, map intel)
  â†’ optional WEB map research (song select or first gameplay) â†’ structured MAP INTEL cached
  â†’ TTS (ash) â†’ wait â†’ next capture (min 20s)
```

Stage 2 never sees the image â€” only the description â€” so it reacts like a person reading notes, not a stats overlay.

Optional: set `OPENAI_DESCRIBE_MODEL=gpt-4o` for harder-to-read HUD text while keeping `OPENAI_MODEL=gpt-4o-mini` for the coach line.

Use `-v` to print the full screen observation in the console each cycle.

Disable speech: `--no-tts` or `TTS_ENABLED=false`.

**Voice input** â€” always-on mic with a **minimum volume gate** (`VOICE_MIN_RMS`, not push-to-talk). After STT, the coach replies immediately. **Screenshot rules:** captures + vision on voice only if (1) no screenshot in the last `CAPTURE_INTERVAL_SECONDS` (e.g. first thing you say after a while), or (2) you explicitly ask about the screen (*"what can you see?"*, *"what should I play?"*, etc.). If you talk again 5s later without a screen question, it reuses the recent snapshot. The idle **20s screen cycle** also refreshes that cache. **Barge-in** stops coach TTS when you talk.

**STT cost & latency** â€” `whisper-1` is ~**$0.006/minute** of audio (billed per second). Typical API wait is **~0.5â€“2s** for a short phrase plus your upload time; logs show `STT: X.Xs API`. Cheaper option: `VOICE_STT_MODEL=gpt-4o-mini-transcribe` (~$0.003/min).

**Capture monitor** â€” default `--monitor 1` is the **primary display** (where most people run games). Index `0` stitches all monitors into one image; `2+` are secondary displays. Run `python -m aicoach --list-monitors` to see indices and resolutions.

**Map intel / hard sections (osu)** â€” **one** web search per map on **song select** (`map_select`); hard-section notes are cached as MAP INTEL and reused for the whole play â€” **no web search during gameplay**. Console shows `--- Map intel (hard sections) ---` when cached. Set `WEB_SEARCH_CONTEXT_SIZE=high` for better research. Disable with `WEB_SEARCH_ENABLED=false` or `--no-web`.

**Screen reasoning:** each reply classifies the screen (`gameplay`, `map_select`, `results`, etc.) before speaking, so it won't praise a "good score" while you're on song select. Logs/print show `Screen: map_select â€” ...`.

**Session memory:** last N **spoken lines** only (not past observations) are appended to the system prompt. Tune with `MAX_HISTORY_MESSAGES` (default 12 lines).

**Personality:** friend in voice chat â€” roasts when you play badly. Tune with `COACH_TEMPERATURE` (default `0.65`).

**Better UI understanding:** set `OPENAI_MODEL=gpt-4o` in `.env` (costs more than `gpt-4o-mini` but reads menus/HUDs more reliably).

## Local engine server (desktop app sidecar)

The desktop app drives the engine through a localhost WebSocket instead of the CLI.
Install the extra and run the server:

```powershell
# from the repo root (shared .venv)
.\.venv\Scripts\python -m pip install -e "engine[service]"
.\.venv\Scripts\python -m aicoach.service --port 8765
```

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness + whether a session is running |
| `GET /games` | Supported game ids |
| `GET /monitors` | Capture monitor indices |
| `WS /ws` | Streams engine events; accepts control messages |

**Control messages** (send as JSON over the socket): `{"action": "start", "config": {"game_id": "osu"}}`,
`{"action": "stop"}`, `{"action": "set_game", "game_id": "osu"}`, `{"action": "update_config", "config": {...}}`,
`{"action": "get_state"}`.

**Events** (received as JSON): `status`, `transcript`, `advice`, `cost`, `error`, `session`, `config`
(see [`src/aicoach/events.py`](src/aicoach/events.py)). The latest `status`/`session`/`cost`/`config`
are replayed to each client on connect.

Bind is `127.0.0.1` only. Set `AICOACH_TOKEN` to require a matching `?token=` on the WebSocket.

### Use from code (for a future UI)

```python
from aicoach.config import Settings
from aicoach.runner import CoachRunner

def on_advice(advice, screenshot):
    # Push to UI, TTS, overlay, etc.
    print(advice.text)

runner = CoachRunner(Settings.from_env(), game_id="valorant", on_advice=on_advice)
runner.run()
```

## Cost (important)

Each cycle = **describe (vision)** + **coach (text)** + optional **web** + **TTS**. Cycle length depends on API latency, audio length, and `POST_SPEECH_DELAY_SECONDS` (not a fixed 10s timer).

### TTS (`tts-1`, voice `ash`)

Billed per **input character** ($15 / 1M chars for `tts-1`).

| Reply size | TTS cost (approx.) |
|------------|-------------------|
| ~60 words (~350 chars) | ~**$0.005** |
| ~100 words (~600 chars) | ~**$0.009** |

Short coaching replies keep TTS cheap. `tts-1-hd` costs **2Ã—**.

### Web search (when triggered)

OpenAI charges **~$10 / 1,000 search actions** ($0.01 per search) plus model tokens. For `gpt-4o-mini`, search content is often billed as an **~8,000 input token block** per search (~$0.0012 extra).

| Per web-augmented cycle | Approx. cost |
|-------------------------|--------------|
| Web tool (1 search) | ~**$0.01** |
| Search content + reply tokens | ~**$0.002â€“0.004** |
| **Web add-on total** | ~**$0.012â€“0.015** |

Web runs only on certain screens (not every gameplay frame). **Gameplay-only cycle** (no web): vision + TTS only.

### Combined cycle (vision + web + TTS, when web runs)

| | Approx. |
|--|--------|
| Vision (high) | ~$0.005â€“0.008 |
| Web (1 search, mini, low context) | ~$0.012â€“0.015 |
| TTS | ~$0.005 |
| **Total** | ~**$0.022â€“0.028** |

~20s per cycle â†’ ~**$4â€“5 / hour** if web fires every time; ~**$2â€“3 / hour** if only half your screens trigger web.

### Combined cycle (vision + TTS only, no web)

| `IMAGE_DETAIL` | Per cycle (ballpark) |
|----------------|---------------------|
| **high** | ~**$0.01 â€“ $0.015** |
| **low** | ~**$0.005 â€“ $0.008** |

Example: ~20s per cycle (8s speech + 4s delay + APIs) â†’ ~180 cycles/hour â†’ **~$1.80 â€“ $2.70/hour** with TTS on high detail.

The CLI prints vision + TTS cost per cycle.

### `gpt-4o-mini` + vision only

OpenAI bills images as **tokens**. For vision, `gpt-4o-mini` uses a **much higher token count per image** than `gpt-4o` so the **dollar cost per image is about the same** as the full modelâ€”not 33Ã— cheaper for screenshots.

Rough estimates (your resized ~1920px-wide desktop capture):

| `IMAGE_DETAIL` | Per call (typical) | 1 hour @ 10s | 3 hour session |
|----------------|-------------------|--------------|----------------|
| **high** (default) | ~$0.004 â€“ $0.008 | ~**$1.50 â€“ $3** | ~**$4 â€“ $9** |
| **low** (testing) | ~$0.0004 â€“ $0.001 | ~**$0.15 â€“ $0.35** | ~**$0.50 â€“ $1** |

Text (prompt + reply) adds only a fraction of a cent per callâ€”the **image dominates**.

The CLI prints **actual token usage and estimated $** after each call so you can calibrate on your monitor resolution.

### Cheaper local testing

In `.env`:

```env
IMAGE_DETAIL=low
CAPTURE_INTERVAL_SECONDS=30
```

Or: `python -m aicoach --game valorant --interval 60`

## Security

- Keep `.env` local (gitignored); never commit API keys.
- Screenshots may contain personal or sensitive information; only send them to APIs you trust.
