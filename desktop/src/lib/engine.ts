import { useCallback, useEffect, useRef, useState } from "react";

/** Event + control vocabulary shared with the Python engine (see engine/src/aicoach/events.py). */

export type EngineState =
    | "idle"
    | "starting"
    | "listening"
    | "capturing"
    | "transcribing"
    | "thinking"
    | "speaking"
    | "stopped"
    | "error";

export interface CostBreakdown {
    vision_usd: number;
    web_usd: number;
    tts_usd: number;
    stt_usd: number;
    cycle_usd: number;
}

export interface CostEvent {
    type: "cost";
    ts: string;
    breakdown: CostBreakdown;
    cycle_usd: number;
    session_usd: number;
    call_count: number;
    timings: Record<string, unknown>;
}

export interface AdviceEvent {
    type: "advice";
    ts: string;
    text: string;
    model: string;
    game_id: string;
    scene: string;
    skip: boolean;
    trigger: "screen" | "voice" | string;
    screen_description: string;
    ocr_preview: string;
    screen_read_method: string;
    map_intel_name: string;
    map_intel_notes: string;
    user_said: string;
    captured_at: string | null;
    monitor_index: number | null;
}

export interface RuntimeConfig {
    game_id: string | null;
    monitor_index: number;
    interval_seconds: number | null;
    tts_enabled: boolean | null;
    voice_input_enabled: boolean | null;
    web_search_enabled: boolean | null;
}

export interface EngineSnapshot {
    connected: boolean;
    state: EngineState;
    statusDetail: string;
    running: boolean;
    gameId: string | null;
    config: RuntimeConfig | null;
    transcript: string;
    advices: AdviceEvent[];
    cost: CostEvent | null;
    error: string | null;
    games: string[];
    monitors: { index: number; label: string; width: number; height: number }[];
}

type ControlMessage =
    | { action: "start"; config?: Partial<RuntimeConfig> }
    | { action: "stop" }
    | { action: "set_game"; game_id: string }
    | { action: "update_config"; config: Partial<RuntimeConfig> }
    | { action: "get_state" };

const MAX_ADVICES = 100;
const RECONNECT_MS = 1500;

const INITIAL: EngineSnapshot = {
    connected: false,
    state: "idle",
    statusDetail: "",
    running: false,
    gameId: null,
    config: null,
    transcript: "",
    advices: [],
    cost: null,
    error: null,
    games: [],
    monitors: [],
};

export interface EngineApi extends EngineSnapshot {
    available: boolean;
    start: (config?: Partial<RuntimeConfig>) => void;
    stop: () => void;
    setGame: (gameId: string) => void;
    updateConfig: (config: Partial<RuntimeConfig>) => void;
}

export function useEngine(): EngineApi {
    const [snap, setSnap] = useState<EngineSnapshot>(INITIAL);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const closedRef = useRef(false);
    const available = typeof window !== "undefined" && Boolean(window.aicoach);

    const send = useCallback((msg: ControlMessage) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    }, []);

    useEffect(() => {
        if (!available) return;
        closedRef.current = false;
        let httpUrl = "";

        const apply = (event: Record<string, unknown>) => {
            const type = event.type as string;
            setSnap((prev) => {
                switch (type) {
                    case "status":
                        return { ...prev, state: event.state as EngineState, statusDetail: (event.detail as string) ?? "" };
                    case "session":
                        return { ...prev, running: Boolean(event.running), gameId: (event.game_id as string) ?? prev.gameId };
                    case "config":
                        return { ...prev, config: event as unknown as RuntimeConfig, gameId: (event.game_id as string) ?? prev.gameId };
                    case "transcript":
                        return { ...prev, transcript: event.text as string };
                    case "advice":
                        return { ...prev, advices: [event as unknown as AdviceEvent, ...prev.advices].slice(0, MAX_ADVICES) };
                    case "cost":
                        return { ...prev, cost: event as unknown as CostEvent };
                    case "error":
                        return { ...prev, error: event.message as string };
                    default:
                        return prev;
                }
            });
        };

        const connect = (wsUrl: string) => {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;
            ws.onopen = () => setSnap((prev) => ({ ...prev, connected: true, error: null }));
            ws.onmessage = (msg) => {
                try {
                    apply(JSON.parse(msg.data as string));
                } catch {
                    /* ignore malformed frames */
                }
            };
            ws.onclose = () => {
                setSnap((prev) => ({ ...prev, connected: false }));
                if (!closedRef.current) {
                    reconnectRef.current = setTimeout(() => connect(wsUrl), RECONNECT_MS);
                }
            };
            ws.onerror = () => ws.close();
        };

        window.aicoach
            .getEngineInfo()
            .then(async (info) => {
                httpUrl = info.httpUrl;
                // Bootstrap static lists (best-effort).
                try {
                    const [g, m] = await Promise.all([
                        fetch(`${httpUrl}/games`).then((r) => r.json()),
                        fetch(`${httpUrl}/monitors`).then((r) => r.json()),
                    ]);
                    setSnap((prev) => ({ ...prev, games: g.games ?? [], monitors: m.monitors ?? [] }));
                } catch {
                    /* engine may still be starting; lists arrive on retry */
                }
                connect(info.wsUrl);
            })
            .catch(() => setSnap((prev) => ({ ...prev, error: "Engine bridge unavailable" })));

        return () => {
            closedRef.current = true;
            if (reconnectRef.current) clearTimeout(reconnectRef.current);
            wsRef.current?.close();
        };
    }, [available]);

    const start = useCallback((config?: Partial<RuntimeConfig>) => send({ action: "start", config }), [send]);
    const stop = useCallback(() => send({ action: "stop" }), [send]);
    const setGame = useCallback((game_id: string) => send({ action: "set_game", game_id }), [send]);
    const updateConfig = useCallback((config: Partial<RuntimeConfig>) => send({ action: "update_config", config }), [send]);

    return { ...snap, available, start, stop, setGame, updateConfig };
}
