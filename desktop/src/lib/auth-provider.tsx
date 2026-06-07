import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useSyncExternalStore,
    type ReactNode,
} from "react";
import { AuthStore, INITIAL_AUTH_SNAPSHOT, type AuthSnapshot } from "@/lib/auth-store";

type EqualityFn<T> = (a: T, b: T) => boolean;

const AuthStoreContext = createContext<AuthStore | null>(null);

export interface AuthActions {
    login: () => Promise<void>;
    logout: () => Promise<void>;
    refreshMe: () => Promise<void>;
}

const AuthActionsContext = createContext<AuthActions | null>(null);

function useAuthStore(): AuthStore {
    const store = useContext(AuthStoreContext);
    if (!store) throw new Error("AuthProvider is missing");
    return store;
}

export function useAuthSelector<T>(selector: (snap: AuthSnapshot) => T, isEqual: EqualityFn<T> = Object.is): T {
    const store = useAuthStore();
    const selectorRef = useRef(selector);
    const isEqualRef = useRef(isEqual);
    selectorRef.current = selector;
    isEqualRef.current = isEqual;

    const cache = useRef<T>(selector(INITIAL_AUTH_SNAPSHOT));

    const getSnapshot = useCallback(() => {
        const next = selectorRef.current(store.getState());
        if (!isEqualRef.current(cache.current, next)) {
            cache.current = next;
        }
        return cache.current;
    }, [store]);

    return useSyncExternalStore(store.subscribe, getSnapshot, getSnapshot);
}

export function useAuthActions(): AuthActions {
    const actions = useContext(AuthActionsContext);
    if (!actions) throw new Error("AuthProvider is missing");
    return actions;
}

// Re-export for typing in login-screen legacy prop
export type { AuthSnapshot } from "@/lib/auth-store";

export function AuthProvider({ children }: { children: ReactNode }) {
    const storeRef = useRef<AuthStore | null>(null);
    if (!storeRef.current) storeRef.current = new AuthStore();
    const store = storeRef.current;

    const available = typeof window !== "undefined" && Boolean(window.aicoach?.login);

    useEffect(() => {
        store.setAvailable(available);
    }, [available, store]);

    const refreshMe = useCallback(async () => {
        if (!available) return;
        const m = await window.aicoach.getMe();
        store.setMe(m);
        if (!m) store.setSession(null);
    }, [available, store]);

    const actionsRef = useRef<AuthActions>({
        login: async () => {
            if (!available) return;
            store.setBusy(true);
            store.setError(null);
            try {
                const s = await window.aicoach.login();
                store.setSession(s);
                store.setMe(await window.aicoach.getMe());
            } catch (e) {
                store.setError(e instanceof Error ? e.message : "Sign-in failed.");
            } finally {
                store.setBusy(false);
            }
        },
        logout: async () => {
            if (!available) return;
            store.setBusy(true);
            try {
                await window.aicoach.logout();
            } finally {
                store.setSession(null);
                store.setMe(null);
                store.setBusy(false);
            }
        },
        refreshMe,
    });
    actionsRef.current.refreshMe = refreshMe;

    useEffect(() => {
        if (!available) {
            store.setReady(true);
            return;
        }
        let cancelled = false;
        void (async () => {
            const s = await window.aicoach.getSession();
            if (cancelled) return;
            store.setSession(s);
            if (s) {
                const m = await window.aicoach.getMe();
                if (cancelled) return;
                store.setMe(m);
                if (!m) store.setSession(null);
            }
            store.setReady(true);
        })();
        return () => {
            cancelled = true;
        };
    }, [available, store]);

    return (
        <AuthStoreContext.Provider value={store}>
            <AuthActionsContext.Provider value={actionsRef.current}>{children}</AuthActionsContext.Provider>
        </AuthStoreContext.Provider>
    );
}
