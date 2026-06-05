export interface EngineInfo {
    wsUrl: string;
    httpUrl: string;
    token: string;
    platform: string;
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

declare global {
    interface Window {
        aicoach: {
            getEngineInfo: () => Promise<EngineInfo>;
            getSession: () => Promise<Session | null>;
            getMe: () => Promise<MeResponse | null>;
            login: () => Promise<Session>;
            logout: () => Promise<{ ok: boolean }>;
            getAppVersion: () => Promise<string>;
            checkForUpdates: () => Promise<{ ok: boolean; reason?: string }>;
            installUpdate: () => Promise<{ ok: boolean }>;
            onUpdateStatus: (callback: (status: UpdateStatus) => void) => () => void;
        };
    }
}

export {};
