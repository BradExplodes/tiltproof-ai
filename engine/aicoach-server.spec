# PyInstaller spec for the desktop sidecar server.
# Build (from engine/):  pyinstaller aicoach-server.spec --noconfirm --clean
# Output:               dist/aicoach-server/aicoach-server.exe  (+ bundled deps)
#
# onedir (not onefile): far faster startup and more reliable with heavy native
# deps (numpy, opencv, sounddevice, uvicorn). Electron ships the whole folder as
# an extra resource and launches aicoach-server.exe from it.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
root = Path(SPECPATH)
src = root / "src"
prompts = src / "aicoach" / "prompts"

# Dynamically-loaded modules PyInstaller can't see by static analysis.
hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("openai")
    + [
        "fastapi",
        "starlette",
        "anyio",
        "websockets",
        "websocket",
        "httptools",
        "sounddevice",
        "winocr",
        "cv2",
        "numpy",
        "pytesseract",
        "PIL",
        "PIL.Image",
        "mss",
        "dxcam",
        "comtypes",
        "dotenv",
    ]
)

# Native libraries bundled with some packages (e.g. PortAudio for sounddevice).
binaries = collect_dynamic_libs("sounddevice")

datas = [(str(prompts), "aicoach/prompts")] + collect_data_files("sounddevice")

a = Analysis(
    [str(root / "scripts" / "server_entry.py")],
    pathex=[str(src)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aicoach-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="aicoach-server",
)
