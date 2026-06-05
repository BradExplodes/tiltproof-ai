# Releasing AI Coach (desktop installer + auto-update)

The release pipeline builds the Python engine into a standalone sidecar, bundles
it inside the Electron app, produces a Windows installer, and publishes it to
**GitHub Releases**. Installed apps auto-update from those releases.

```
GitHub Actions (windows-latest)
  ├─ PyInstaller  → engine/dist/aicoach-server/aicoach-server.exe (+ deps)
  ├─ Vite + tsc   → desktop/dist (renderer) + desktop/dist-electron (main)
  └─ electron-builder
        ├─ bundles the engine folder as an app resource (resources/engine/)
        ├─ builds "AI Coach-Setup-<version>.exe" (NSIS)
        └─ uploads installer + latest.yml to the GitHub Release for the tag
```

At runtime, `electron-updater` checks the same repo's releases on launch,
downloads a newer version in the background, and installs it on quit.

---

## One-time setup

### 1. Put the code on GitHub (two repos)

To keep auto-update token-free, the main repo is **public**. To keep the
proprietary server logic closed, `backend/` is excluded from it (see root
`.gitignore`) and lives in its own **private** repo.

**Public repo** (engine + desktop + landing) — from the repo root:

```powershell
git init
git add .                # backend/ is gitignored, so it won't be included
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/BradExplodes/tiltproof-ai.git   # PUBLIC repo
git push -u origin main
```

**Private backend repo** — from `backend/`:

```powershell
cd backend
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/BradExplodes/tiltproof-ai-backend.git   # PRIVATE repo
git push -u origin main
```

> Nothing secret lives in the public repo: the backend URL (`api.tiltproof.net`)
> is public, and all keys/secrets live in Cloudflare. Even so, the server code
> that does proxying/metering/auth stays private in the second repo.

### 2. Point the build at your repo

Already configured in `desktop/package.json` → `build.publish` to publish to and
auto-update from the public repo:

```json
"publish": [{ "provider": "github", "owner": "BradExplodes", "repo": "tiltproof-ai" }]
```

### 3. Secrets

Nothing to add — the workflow uses the built-in `GITHUB_TOKEN`, which already has
permission to create releases in its own repo.

> Note on code signing: the installer is **unsigned** for v1, so Windows
> SmartScreen will show a "Windows protected your PC" warning on first run (click
> *More info → Run anyway*). To remove it later, buy a code-signing certificate
> and add `CSC_LINK` / `CSC_KEY_PASSWORD` secrets; electron-builder will sign
> automatically. Auto-update works fine without signing.

---

## Cutting a release

The git tag must match the version in `desktop/package.json` (prefixed with `v`).

1. Bump the version in `desktop/package.json` (e.g. `0.1.0` → `0.1.1`).
2. Commit it.
3. Tag and push:

```powershell
git commit -am "Release v0.1.1"
git tag v0.1.1
git push origin main --tags
```

Pushing the tag triggers `.github/workflows/release.yml`. When it finishes,
the installer is attached to the GitHub Release for `v0.1.1`.

You can also run the workflow manually from the Actions tab (it builds but
publishes against whatever version is in `package.json`).

---

## How auto-update behaves

- On launch (packaged builds only) the app checks the GitHub repo for a release
  newer than the running version.
- If found, it downloads in the background and installs when the user quits.
- Dev runs (`npm run dev`) never check for updates.

To test it: install `v0.1.0`, then release `v0.1.1`. Relaunch the installed app —
it should fetch and apply the update on the next quit.

### Auto-update says "Unable to find latest version"

Git **tags** alone are not enough — the release must include **`latest.yml`**
and the **`Tiltproof AI-Setup-<version>.exe`** installer as GitHub Release
assets. Check https://github.com/BradExplodes/tiltproof-ai/releases — you should
see downloadable files, not "There aren't any releases here".

If tags exist but releases are empty, re-publish with a fixed workflow:

1. Push the workflow fix to `main`.
2. GitHub → Actions → **Release** → **Run workflow** → set `tag_name` to e.g.
   `v0.1.3` (or cut a new tag `v0.1.4`).
3. Confirm the release page shows the `.exe` and `latest.yml`.

---

## Building locally (optional sanity check)

```powershell
# 1) Build the engine sidecar
cd engine
pip install -e ".[service]" pyinstaller
pyinstaller aicoach-server.spec --noconfirm --clean

# 2) Build the installer (no publish)
cd ../desktop
npm run dist
```

The unpacked app and installer land in `desktop/release/`.

---

## macOS / Linux

The pipeline targets Windows only for v1 (matches the audience and the engine's
Windows OCR path). Adding macOS later means a `macos` job on `macos-latest`, a
`dmg`/`zip` target, and Apple notarization secrets — straightforward to bolt on
when needed.
