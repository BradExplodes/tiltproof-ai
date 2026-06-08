import type { BadgeColors } from "@/components/base/badges/badge-types";
import type { EngineState, PerfEvent, RuntimeConfig } from "@/lib/engine-types";

export const STATE_BADGE: Record<EngineState, { color: BadgeColors; label: string }> = {
    idle: { color: "gray", label: "Idle" },
    starting: { color: "blue", label: "Starting" },
    listening: { color: "success", label: "Listening" },
    capturing: { color: "blue", label: "Reading screen" },
    transcribing: { color: "indigo", label: "Transcribing" },
    thinking: { color: "warning", label: "Thinking" },
    speaking: { color: "brand", label: "Speaking" },
    stopped: { color: "gray", label: "Stopped" },
    error: { color: "error", label: "Error" },
};

export const ACTIVITY: Partial<Record<EngineState, string>> = {
    starting: "Starting up…",
    capturing: "Reading your screen…",
    transcribing: "Transcribing your speech…",
    thinking: "Thinking…",
    speaking: "Speaking…",
};

export const prettyGame = (id: string) => id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const configEqual = (a: RuntimeConfig | null, b: RuntimeConfig | null): boolean => {
    if (a === b) return true;
    if (!a || !b) return false;
    return (
        a.game_id === b.game_id &&
        a.monitor_index === b.monitor_index &&
        a.interval_seconds === b.interval_seconds &&
        a.tts_enabled === b.tts_enabled &&
        a.tts_voice_id === b.tts_voice_id &&
        a.voice_input_enabled === b.voice_input_enabled &&
        a.ocr_enabled === b.ocr_enabled &&
        a.web_search_enabled === b.web_search_enabled &&
        a.player_name === b.player_name
    );
};

export const perfEqual = (a: PerfEvent | null, b: PerfEvent | null): boolean => {
    if (a === b) return true;
    if (!a || !b) return false;
    return a.phase === b.phase && a.duration_ms === b.duration_ms && a.grab_ms === b.grab_ms && a.encode_ms === b.encode_ms;
};

export const isCoachReady = (gameId: string | null, voiceId: string | null | undefined): boolean =>
    Boolean(gameId && voiceId);

export const usageFromMe = (me: { used_usd: number; quota_usd: number } | null) => {
    const unlimited = me ? me.quota_usd <= 0 : false;
    const usagePct = me && me.quota_usd > 0 ? Math.min(100, (me.used_usd / me.quota_usd) * 100) : 0;
    const overQuota = !unlimited && me != null && usagePct >= 100;
    return { unlimited, usagePct, overQuota };
};
