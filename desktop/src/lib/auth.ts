import type { MeResponse, Session } from "@/types/aicoach";

/** Prefer AuthProvider + useAuthSelector for UI that must not repaint unrelated regions. */
export type { AuthActions } from "@/lib/auth-provider";
export { AuthProvider, useAuthActions, useAuthSelector } from "@/lib/auth-provider";
export type { AuthSnapshot } from "@/lib/auth-store";

import { useAuthActions, useAuthSelector } from "@/lib/auth-provider";

/** @deprecated Prefer useAuthSelector / useAuthActions in leaf components. */
export interface AuthApi {
    ready: boolean;
    available: boolean;
    session: Session | null;
    me: MeResponse | null;
    busy: boolean;
    error: string | null;
    login: () => Promise<void>;
    logout: () => Promise<void>;
    refreshMe: () => Promise<void>;
}

/** Subscribes to the full auth snapshot — only use on login / app shell routing. */
export function useAuth(): AuthApi {
    const ready = useAuthSelector((s) => s.ready);
    const available = useAuthSelector((s) => s.available);
    const session = useAuthSelector((s) => s.session);
    const me = useAuthSelector((s) => s.me);
    const busy = useAuthSelector((s) => s.busy);
    const error = useAuthSelector((s) => s.error);
    const { login, logout, refreshMe } = useAuthActions();
    return { ready, available, session, me, busy, error, login, logout, refreshMe };
}
