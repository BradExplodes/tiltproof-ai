import type {
    AdviceEvent,
    CostEvent,
    EngineSnapshot,
    EngineState,
    FeedItem,
    PerfEvent,
    RuntimeConfig,
} from "@/lib/engine-types";

export type { EngineSnapshot } from "@/lib/engine-types";

const MAX_FEED = 200;

const newId = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

export const INITIAL_ENGINE_SNAPSHOT: EngineSnapshot = {
    connected: false,
    state: "idle",
    statusDetail: "",
    running: false,
    gameId: null,
    config: null,
    feed: [],
    cost: null,
    error: null,
    games: [],
    monitors: [],
    lastPerf: null,
};

type Listener = () => void;

export class EngineStore {
    private _state: EngineSnapshot = INITIAL_ENGINE_SNAPSHOT;
    private _listeners = new Set<Listener>();

    readonly subscribe = (listener: Listener): (() => void) => {
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    };

    getState = (): EngineSnapshot => this._state;

    private emit(): void {
        for (const listener of this._listeners) listener();
    }

    private replace(next: EngineSnapshot): void {
        this._state = next;
        this.emit();
    }

    patch(mutator: (prev: EngineSnapshot) => EngineSnapshot | null): void {
        const next = mutator(this._state);
        if (next !== null && next !== this._state) {
            this.replace(next);
        }
    }

    setConnected(connected: boolean, clearError = false): void {
        this.patch((prev) => {
            if (prev.connected === connected && !(clearError && prev.error)) return null;
            return { ...prev, connected, error: clearError ? null : prev.error };
        });
    }

    setBootstrap(games: string[], monitors: EngineSnapshot["monitors"]): void {
        this.patch((prev) => {
            if (prev.games === games && prev.monitors === monitors) return null;
            return { ...prev, games, monitors };
        });
    }

    setError(error: string): void {
        this.patch((prev) => (prev.error === error ? null : { ...prev, error }));
    }

    applyEvent(event: Record<string, unknown>): void {
        const type = event.type as string;
        switch (type) {
            case "status":
                this.patch((prev) => {
                    const state = event.state as EngineState;
                    const statusDetail = (event.detail as string) ?? "";
                    if (prev.state === state && prev.statusDetail === statusDetail) return null;
                    return { ...prev, state, statusDetail };
                });
                break;
            case "session":
                this.patch((prev) => {
                    const running = Boolean(event.running);
                    const gameId = (event.game_id as string) ?? prev.gameId;
                    if (prev.running === running && prev.gameId === gameId) return null;
                    return { ...prev, running, gameId };
                });
                break;
            case "config": {
                const config = event as unknown as RuntimeConfig;
                this.patch((prev) => {
                    const gameId = config.game_id ?? prev.gameId;
                    const sameConfig =
                        prev.config !== null &&
                        prev.config.game_id === config.game_id &&
                        prev.config.monitor_index === config.monitor_index &&
                        prev.config.interval_seconds === config.interval_seconds &&
                        prev.config.tts_enabled === config.tts_enabled &&
                        prev.config.voice_input_enabled === config.voice_input_enabled &&
                        prev.config.ocr_enabled === config.ocr_enabled &&
                        prev.config.web_search_enabled === config.web_search_enabled;
                    if (sameConfig && prev.gameId === gameId) return null;
                    return { ...prev, config, gameId };
                });
                break;
            }
            case "transcript": {
                const text = ((event.text as string) ?? "").trim();
                if (!text || Boolean(event.partial)) return;
                const ts = (event.ts as string) ?? "";
                const item: FeedItem = { kind: "user", id: newId(), ts, text };
                this.patch((prev) => ({ ...prev, feed: [...prev.feed, item].slice(-MAX_FEED) }));
                break;
            }
            case "perf": {
                const lastPerf = event as unknown as PerfEvent;
                this.patch((prev) => {
                    const p = prev.lastPerf;
                    if (
                        p &&
                        p.phase === lastPerf.phase &&
                        p.duration_ms === lastPerf.duration_ms &&
                        p.grab_ms === lastPerf.grab_ms &&
                        p.encode_ms === lastPerf.encode_ms
                    ) {
                        return null;
                    }
                    return { ...prev, lastPerf };
                });
                break;
            }
            case "advice": {
                const advice = event as unknown as AdviceEvent;
                if (advice.skip || !advice.text?.trim()) return;
                const item: FeedItem = { kind: "advice", id: newId(), ts: advice.ts ?? "", advice };
                this.patch((prev) => ({ ...prev, feed: [...prev.feed, item].slice(-MAX_FEED) }));
                break;
            }
            case "cost": {
                const cost = event as unknown as CostEvent;
                this.patch((prev) => {
                    const c = prev.cost;
                    if (
                        c &&
                        c.call_count === cost.call_count &&
                        c.session_usd === cost.session_usd &&
                        c.cycle_usd === cost.cycle_usd
                    ) {
                        return null;
                    }
                    return { ...prev, cost };
                });
                break;
            }
            case "error":
                this.patch((prev) => {
                    const message = event.message as string;
                    return prev.error === message ? null : { ...prev, error: message };
                });
                break;
            default:
                break;
        }
    }
}
