import { useCallback, useEffect, useState } from "react";
import type { MeResponse, Session } from "@/types/aicoach";

export interface AuthApi {
    /** True once the initial session check has finished. */
    ready: boolean;
    /** True when running inside the Electron shell (the bridge exists). */
    available: boolean;
    session: Session | null;
    me: MeResponse | null;
    busy: boolean;
    error: string | null;
    login: () => Promise<void>;
    logout: () => Promise<void>;
    refreshMe: () => Promise<void>;
}

export function useAuth(): AuthApi {
    const available = typeof window !== "undefined" && Boolean(window.aicoach?.login);
    const [ready, setReady] = useState(false);
    const [session, setSession] = useState<Session | null>(null);
    const [me, setMe] = useState<MeResponse | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refreshMe = useCallback(async () => {
        if (!available) return;
        const m = await window.aicoach.getMe();
        setMe(m);
        if (!m) setSession(null);
    }, [available]);

    useEffect(() => {
        if (!available) {
            setReady(true);
            return;
        }
        let cancelled = false;
        void (async () => {
            const s = await window.aicoach.getSession();
            if (cancelled) return;
            setSession(s);
            if (s) {
                const m = await window.aicoach.getMe();
                if (cancelled) return;
                setMe(m);
                if (!m) setSession(null);
            }
            setReady(true);
        })();
        return () => {
            cancelled = true;
        };
    }, [available]);

    const login = useCallback(async () => {
        if (!available) return;
        setBusy(true);
        setError(null);
        try {
            const s = await window.aicoach.login();
            setSession(s);
            setMe(await window.aicoach.getMe());
        } catch (e) {
            setError(e instanceof Error ? e.message : "Sign-in failed.");
        } finally {
            setBusy(false);
        }
    }, [available]);

    const logout = useCallback(async () => {
        if (!available) return;
        setBusy(true);
        try {
            await window.aicoach.logout();
        } finally {
            setSession(null);
            setMe(null);
            setBusy(false);
        }
    }, [available]);

    return { ready, available, session, me, busy, error, login, logout, refreshMe };
}
