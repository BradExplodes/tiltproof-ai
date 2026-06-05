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
};

contextBridge.exposeInMainWorld("aicoach", api);

export type AicoachBridge = typeof api;
