import { contextBridge, ipcRenderer } from "electron";

export interface EngineInfo {
    wsUrl: string;
    httpUrl: string;
    token: string;
    platform: NodeJS.Platform;
}

export interface Session {
    token: string;
    email: string;
}

export interface MeResponse {
    email: string;
    name: string;
    period: string;
    used_usd: number;
    quota_usd: number;
}

export type UpdateState = "idle" | "checking" | "available" | "downloading" | "ready" | "error" | "none";

export interface UpdateStatus {
    state: UpdateState;
    version?: string;
    percent?: number;
    message?: string;
}

const api = {
    /** Resolve the local engine's WebSocket/HTTP endpoints and auth token. */
    getEngineInfo: (): Promise<EngineInfo> => ipcRenderer.invoke("engine:info"),
    /** Locally stored session, or null if signed out. */
    getSession: (): Promise<Session | null> => ipcRenderer.invoke("auth:session"),
    /** Account + usage from the backend, or null if the session is invalid. */
    getMe: (): Promise<MeResponse | null> => ipcRenderer.invoke("auth:me"),
    /** Run the Google sign-in flow; resolves once a session is captured. */
    login: (): Promise<Session> => ipcRenderer.invoke("auth:login"),
    /** Revoke and clear the session. */
    logout: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("auth:logout"),
    /** Installed app version from package.json. */
    getAppVersion: (): Promise<string> => ipcRenderer.invoke("app:version"),
    /** Ask the main process to check GitHub Releases for a newer build. */
    checkForUpdates: (): Promise<{ ok: boolean; reason?: string }> => ipcRenderer.invoke("update:check"),
    /** Download complete — quit and install the pending update. */
    installUpdate: (): Promise<{ ok: boolean }> => ipcRenderer.invoke("update:install"),
    /** Subscribe to update lifecycle events from the main process. */
    onUpdateStatus: (callback: (status: UpdateStatus) => void): (() => void) => {
        const handler = (_event: Electron.IpcRendererEvent, status: UpdateStatus) => callback(status);
        ipcRenderer.on("update:status", handler);
        return () => ipcRenderer.removeListener("update:status", handler);
    },
};

contextBridge.exposeInMainWorld("aicoach", api);

export type AicoachBridge = typeof api;
