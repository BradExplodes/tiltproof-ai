# Build aicoach.exe into dist/
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot       # engine/
$RepoRoot = Split-Path -Parent $Root           # monorepo root (holds the shared .venv)
$Venv = Join-Path $RepoRoot ".venv"
Set-Location $Root

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    python -m venv $Venv
}

& (Join-Path $Venv "Scripts\pip.exe") install -e . -q
& (Join-Path $Venv "Scripts\pip.exe") install pyinstaller -q
& (Join-Path $Venv "Scripts\pyinstaller.exe") aicoach.spec --noconfirm --clean

$Exe = Join-Path $Root "dist\aicoach.exe"
if (-not (Test-Path $Exe)) {
    throw "Build failed: $Exe not found"
}

# Always refresh dist/.env from project root (or example) so new settings apply
$DistEnv = Join-Path $Root "dist\.env"
$RootEnv = Join-Path $Root ".env"
if (Test-Path $RootEnv) {
    Copy-Item $RootEnv $DistEnv -Force
} else {
    Copy-Item (Join-Path $Root ".env.example") $DistEnv -Force
}

function Write-LauncherBat($Name, $Game) {
    @(
        '@echo off',
        'cd /d "%~dp0"',
        'if not exist .env (',
        '  echo Missing .env - copy from project root or .env.example',
        '  pause',
        '  exit /b 1',
        ')',
        'echo AI Coach - %GAME% ^(TTS + speech delay from .env^)',
        'aicoach.exe --game %GAME%',
        'pause'
    ) -replace '%GAME%', $Game | Set-Content -Encoding ASCII (Join-Path $Root "dist\run-$Name.bat")
}

Write-LauncherBat "league-of-legends" "league-of-legends"

Write-LauncherBat "valorant" "valorant"
Write-LauncherBat "deadlock" "deadlock"
Write-LauncherBat "osu" "osu"

Write-Host ""
Write-Host "Built: $Exe"
Write-Host "Also in dist/: run-*.bat launchers (place .env beside aicoach.exe)"
