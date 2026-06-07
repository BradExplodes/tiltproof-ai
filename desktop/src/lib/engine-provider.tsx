import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useSyncExternalStore,
    type ReactNode,
} from "react";
import { EngineStore, INITIAL_ENGINE_SNAPSHOT } from "@/lib/engine-store";
import type { ControlMessage, EngineSnapshot, RuntimeConfig } from "@/lib/engine-types";

const RECONNECT_MS = 1500;
const HEALTH_POLL_MS = 400;
const HEALTH_TIMEOUT_MS = 30_000;

type EqualityFn<T> = (a: T, b: T) => boolean;

const EngineStoreContext = createContext<EngineStore | null>(null);

export interface EngineActions {
    start: (config?: Partial<RuntimeConfig>) => void;
    stop: () => void;
    setGame: (gameId: string) => void;
    updateConfig: (config: Partial<RuntimeConfig>) => void;
}

const EngineActionsContext = createContext<EngineActions | null>(null);

function useEngineStore(): EngineStore {
    const store = useContext(EngineStoreContext);
    if (!store) throw new Error("EngineProvider is missing");
    return store;
}

/** Subscribe to a slice; only re-renders when the selected value changes. */
export function useEngineSelector<T>(
    selector: (snap: EngineSnapshot) => T,
    isEqual: EqualityFn<T> = Object.is,
): T {
    const store = useEngineStore();
    const selectorRef = useRef(selector);
    const isEqualRef = useRef(isEqual);
    selectorRef.current = selector;
    isEqualRef.current = isEqual;

    const cache = useRef<T>(selector(INITIAL_ENGINE_SNAPSHOT));

    const getSnapshot = useCallback(() => {
        const next = selectorRef.current(store.getState());
        if (!isEqualRef.current(cache.current, next)) {
            cache.current = next;
        }
        return cache.current;
    }, [store]);

    return useSyncExternalStore(store.subscribe, getSnapshot, getSnapshot);
}

export function useEngineActions(): EngineActions {
    const actions = useContext(EngineActionsContext);
    if (!actions) throw new Error("EngineProvider is missing");
    return actions;
}

export function EngineProvider({ children }: { children: ReactNode }) {
    const storeRef = useRef<EngineStore | null>(null);
    if (!storeRef.current) storeRef.current = new EngineStore();
    const store = storeRef.current;

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const closedRef = useRef(false);

    const send = useCallback((msg: ControlMessage) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    }, []);

    const actionsRef = useRef<EngineActions>({
        start: (config) => send({ action: "start", config }),
        stop: () => send({ action: "stop" }),
        setGame: (game_id) => send({ action: "set_game", game_id }),
        updateConfig: (config) => send({ action: "update_config", config }),
    });

    useEffect(() => {
        if (typeof window === "undefined" || !window.aicoach) return;
        closedRef.current = false;
        let httpUrl = "";

        const connect = (wsUrl: string) => {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;
            ws.onopen = () => {
                store.setConnected(true, true);
                if (httpUrl) void bootstrapLists(httpUrl);
            };
            ws.onmessage = (msg) => {
                try {
                    store.applyEvent(JSON.parse(msg.data as string));
                } catch {
                    /* ignore malformed frames */
                }
            };
            ws.onclose = () => {
                store.setConnected(false);
                if (!closedRef.current) {
                    reconnectRef.current = setTimeout(() => connect(wsUrl), RECONNECT_MS);
                }
            };
            ws.onerror = () => ws.close();
        };

        const waitForHealth = async (baseUrl: string): Promise<boolean> => {
            const deadline = Date.now() + HEALTH_TIMEOUT_MS;
            while (Date.now() < deadline && !closedRef.current) {
                try {
                    const res = await fetch(`${baseUrl}/health`);
                    if (res.ok) return true;
                } catch {
                    /* engine still booting */
                }
                await new Promise((r) => setTimeout(r, HEALTH_POLL_MS));
            }
            return false;
        };

        const bootstrapLists = async (baseUrl: string) => {
            try {
                const [g, m] = await Promise.all([
                    fetch(`${baseUrl}/games`).then((r) => r.json()),
                    fetch(`${baseUrl}/monitors`).then((r) => r.json()),
                ]);
                store.setBootstrap(g.games ?? [], m.monitors ?? []);
            } catch {
                /* lists refresh on reconnect */
            }
        };

        void window.aicoach.getEngineInfo().then(async (info) => {
            httpUrl = info.httpUrl;
            const ready = await waitForHealth(httpUrl);
            if (closedRef.current) return;
            if (!ready) {
                store.setError("Engine failed to start. Try restarting the app.");
                return;
            }
            await bootstrapLists(httpUrl);
            connect(info.wsUrl);
        }).catch(() => store.setError("Engine bridge unavailable"));

        return () => {
            closedRef.current = true;
            if (reconnectRef.current) clearTimeout(reconnectRef.current);
            wsRef.current?.close();
        };
    }, [store]);

    return (
        <EngineStoreContext.Provider value={store}>
            <EngineActionsContext.Provider value={actionsRef.current}>{children}</EngineActionsContext.Provider>
        </EngineStoreContext.Provider>
    );
}
