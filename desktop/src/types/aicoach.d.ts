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

declare global {
    interface Window {
        aicoach: {
            getEngineInfo: () => Promise<EngineInfo>;
            getSession: () => Promise<Session | null>;
            getMe: () => Promise<MeResponse | null>;
            login: () => Promise<Session>;
            logout: () => Promise<{ ok: boolean }>;
        };
    }
}

export {};
