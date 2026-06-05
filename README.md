# AI Coach

Real-time AI gaming coach. Captures your screen and mic locally, sends frames/audio to OpenAI
(vision, STT, TTS) through a metered backend proxy, and talks back with live coaching advice.

## Monorepo layout

| Path        | What it is |
|-------------|------------|
| `engine/`   | Python capture/OCR/voice/coach engine. Runs locally as a sidecar; also has a CLI. |
| `desktop/`  | Electron + React (Untitled UI) desktop app that drives the engine and renders the UI. |
| `backend/`  | Cloudflare Worker: Google login (allowlist), OpenAI proxy with per-user metering/quota. |
| `landing/`  | Static marketing / download page (Cloudflare Pages). |

## Architecture

- **Client (per user's PC):** Electron window + the Python engine as a bundled sidecar, talking
  over a localhost WebSocket. All cost-saving filters (OCR, screen-change detection, voice gate)
  stay local to minimize API calls.
- **Backend (serverless, scale-to-zero):** Cloudflare Workers + D1 for auth and an OpenAI proxy
  that meters usage and enforces a hard per-user quota, so the operator's API key is never shipped
  to clients and costs stay bounded. Billing (Stripe) is deferred to v2; v1 is allowlist-gated.

## Development

The Python engine uses a single shared virtualenv at the repo root (`.venv`).

```powershell
# from repo root
.\.venv\Scripts\python -m aicoach --list-games
.\.venv\Scripts\python -m aicoach --game osu
```

See [`engine/README.md`](engine/README.md) for full engine docs (config, OCR, costs, CLI flags).
