import type { ElevenLabsVoice } from "@/lib/engine-types";

let httpUrlCache: string | null = null;

async function baseUrl(): Promise<string> {
    if (httpUrlCache) return httpUrlCache;
    if (typeof window === "undefined" || !window.aicoach) {
        throw new Error("Engine bridge unavailable");
    }
    const info = await window.aicoach.getEngineInfo();
    httpUrlCache = info.httpUrl;
    return httpUrlCache;
}

export async function fetchVoices(): Promise<ElevenLabsVoice[]> {
    const res = await fetch(`${await baseUrl()}/voices`);
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Failed to load voices (${res.status})`);
    }
    const data = (await res.json()) as { voices: ElevenLabsVoice[] };
    return data.voices ?? [];
}

export async function fetchVoicePreview(voiceId: string, text?: string): Promise<Blob> {
    const res = await fetch(`${await baseUrl()}/tts/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: voiceId, text }),
    });
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `Preview failed (${res.status})`);
    }
    return res.blob();
}
