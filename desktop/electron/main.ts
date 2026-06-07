import { spawn, type ChildProcess } from "node:child_process";
import crypto from "node:crypto";
import path from "node:path";
import { app, BrowserWindow, ipcMain } from "electron";
import { autoUpdater } from "electron-updater";
import { BACKEND_BASE, fetchMe, loadSession, login, logout } from "./auth";

const ENGINE_PORT = Number(process.env.AICOACH_PORT ?? 8765);
const ENGINE_TOKEN = crypto.randomBytes(16).toString("hex");
const DEV_URL = process.env.VITE_DEV_SERVER_URL;

let engine: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;

function appIconPath(): string {
    if (DEV_URL) {
        return path.join(__dirname, "..", "public", "tiltproof-icon.png");
    }
    return path.join(process.resourcesPath, "tiltproof-icon.png");
}

/** Where to find the engine server: repo venv in dev, bundled exe in prod. */
function resolveEngineCommand(): { cmd: string; args: string[] } {
    const args = ["--port", String(ENGINE_PORT), "--token", ENGINE_TOKEN];
    if (DEV_URL) {
        // dev: desktop/dist-electron -> repo root is two levels up.
        const repoRoot = path.resolve(__dirname, "..", "..");
        const python =
            process.platform === "win32"
                ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
                : path.join(repoRoot, ".venv", "bin", "python");
        return { cmd: python, args: ["-m", "aicoach.service", ...args] };
    }
    const exe = process.platform === "win32" ? "aicoach-server.exe" : "aicoach-server";
    return { cmd: path.join(process.resourcesPath, "engine", exe), args };
}

function startEngine(): void {
    const { cmd, args } = resolveEngineCommand();
    // Route OpenAI calls through the backend proxy using the signed-in user's
    // session token. Without a session the engine boots (lists games/monitors)
    // but cannot run a coaching session.
    const session = loadSession();
    const env: NodeJS.ProcessEnv = { ...process.env };
    env.AICOACH_DATA_DIR = path.join(app.getPath("userData"), "engine");
    env.PYTHONUTF8 = "1";
    env.PYTHONIOENCODING = "utf-8";
    env.OCR_SAVE_SCREENSHOTS = "false";
    env.VOICE_REALTIME_ENABLED = "false";
    env.PERF_LOG = "1";
    if (session) {
        env.AICOACH_OPENAI_BASE_URL = `${BACKEND_BASE}/openai/v1`;
        env.AICOACH_ELEVENLABS_BASE_URL = `${BACKEND_BASE}/elevenlabs/v1`;
        env.AICOACH_PROXY_TOKEN = session.token;
        env.TTS_PROVIDER = "elevenlabs";
    } else {
        delete env.AICOACH_OPENAI_BASE_URL;
        delete env.AICOACH_ELEVENLABS_BASE_URL;
        delete env.AICOACH_PROXY_TOKEN;
    }
    try {
        engine = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], env });
    } catch (err) {
        console.error("[engine] failed to spawn:", err);
        return;
    }
    engine.stdout?.on("data", (d: Buffer) => console.log("[engine]", d.toString().trim()));
    engine.stderr?.on("data", (d: Buffer) => console.error("[engine]", d.toString().trim()));
    engine.on("exit", (code) => console.log("[engine] exited with code", code));
}

function stopEngine(): void {
    if (engine && !engine.killed) engine.kill();
    engine = null;
}

/** Relaunch the engine so it picks up a changed session (login/logout). */
function restartEngine(): void {
    stopEngine();
    startEngine();
}

ipcMain.handle("engine:info", () => ({
    wsUrl: `ws://127.0.0.1:${ENGINE_PORT}/ws?token=${ENGINE_TOKEN}`,
    httpUrl: `http://127.0.0.1:${ENGINE_PORT}`,
    token: ENGINE_TOKEN,
    platform: process.platform,
}));

ipcMain.handle("auth:session", () => loadSession());

ipcMain.handle("auth:me", () => fetchMe());

ipcMain.handle("auth:login", async () => {
    const session = await login();
    restartEngine();
    return session;
});

ipcMain.handle("auth:logout", async () => {
    await logout();
    restartEngine();
    return { ok: true };
});

async function createWindow(): Promise<void> {
    mainWindow = new BrowserWindow({
        title: "Tiltproof AI",
        width: 1100,
        height: 740,
        minWidth: 880,
        minHeight: 560,
        backgroundColor: "#0c0e12",
        icon: appIconPath(),
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    if (DEV_URL) {
        await mainWindow.loadURL(DEV_URL);
        mainWindow.webContents.openDevTools({ mode: "detach" });
    } else {
        await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
    }

    mainWindow.on("closed", () => {
        mainWindow = null;
    });
}

type UpdateState = "idle" | "checking" | "available" | "downloading" | "ready" | "error" | "none";

interface UpdateStatusPayload {
    state: UpdateState;
    version?: string;
    percent?: number;
    message?: string;
}

function sendUpdateStatus(status: UpdateStatusPayload): void {
    mainWindow?.webContents.send("update:status", status);
}

/** Missing release assets on GitHub is common before the first CI publish — not a hard error. */
function normalizeUpdateError(message: string): UpdateStatusPayload {
    const lower = message.toLowerCase();
    if (
        lower.includes("unable to find latest version") ||
        lower.includes("cannot parse releases feed") ||
        lower.includes("no published versions")
    ) {
        return { state: "none" };
    }
    const short = message.length > 140 ? `${message.slice(0, 140)}…` : message;
    return { state: "error", message: short };
}

/** Check GitHub Releases; download in background; user installs via in-app banner. */
function setupAutoUpdate(): void {
    if (DEV_URL) return;

    let pendingVersion: string | undefined;

    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = false;

    autoUpdater.on("checking-for-update", () => {
        sendUpdateStatus({ state: "checking" });
    });

    autoUpdater.on("update-available", (info) => {
        pendingVersion = info.version;
        sendUpdateStatus({ state: "available", version: info.version });
    });

    autoUpdater.on("update-not-available", () => {
        sendUpdateStatus({ state: "none" });
    });

    autoUpdater.on("download-progress", (progress) => {
        sendUpdateStatus({
            state: "downloading",
            percent: progress.percent,
            version: pendingVersion,
        });
    });

    autoUpdater.on("update-downloaded", (info) => {
        console.log("[updater] update ready:", info.version);
        sendUpdateStatus({ state: "ready", version: info.version });
    });

    autoUpdater.on("error", (err) => {
        console.error("[updater]", err);
        sendUpdateStatus(normalizeUpdateError(err.message));
    });

    void autoUpdater.checkForUpdates().catch((err) => {
        console.error("[updater] check failed", err);
        sendUpdateStatus(normalizeUpdateError(String(err)));
    });
}

ipcMain.handle("update:check", async () => {
    if (DEV_URL) return { ok: false, reason: "dev" };
    try {
        await autoUpdater.checkForUpdates();
        return { ok: true };
    } catch (err) {
        return { ok: false, reason: String(err) };
    }
});

ipcMain.handle("update:install", () => {
    if (DEV_URL) return { ok: false };
    // Silent in-place upgrade: /S + --updated (electron-updater NSIS defaults).
    autoUpdater.quitAndInstall(true, true);
    return { ok: true };
});

ipcMain.handle("app:version", () => app.getVersion());

app.whenReady().then(() => {
    startEngine();
    void createWindow();
    setupAutoUpdate();
    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) void createWindow();
    });
});

app.on("window-all-closed", () => {
    stopEngine();
    if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", stopEngine);
