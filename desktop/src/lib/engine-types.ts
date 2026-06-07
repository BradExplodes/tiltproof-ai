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

export type FeedItem =
    | { kind: "user"; id: string; ts: string; text: string; partial?: boolean; item_id?: string }
    | { kind: "advice"; id: string; ts: string; advice: AdviceEvent };

export interface RuntimeConfig {
    game_id: string | null;
    monitor_index: number;
    interval_seconds: number | null;
    tts_enabled: boolean | null;
    tts_voice_id: string | null;
    voice_input_enabled: boolean | null;
    ocr_enabled: boolean | null;
    web_search_enabled: boolean | null;
}

export interface ElevenLabsVoice {
    voice_id: string;
    name: string;
    description: string;
    category: string;
    preview_url: string | null;
    labels: Record<string, string>;
}

export interface PerfEvent {
    phase: string;
    state: string;
    duration_ms: number;
    grab_ms?: number;
    encode_ms?: number;
    [key: string]: unknown;
}

export interface EngineSnapshot {
    connected: boolean;
    state: EngineState;
    statusDetail: string;
    running: boolean;
    gameId: string | null;
    config: RuntimeConfig | null;
    feed: FeedItem[];
    cost: CostEvent | null;
    error: string | null;
    games: string[];
    monitors: { index: number; label: string; width: number; height: number }[];
    lastPerf: PerfEvent | null;
}

export type ControlMessage =
    | { action: "start"; config?: Partial<RuntimeConfig> }
    | { action: "stop" }
    | { action: "set_game"; game_id: string }
    | { action: "update_config"; config: Partial<RuntimeConfig> }
    | { action: "get_state" };
