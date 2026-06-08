import type { ElevenLabsVoice, MemoryEntry } from "@/lib/engine-types";

let httpUrlCache: string | null = null;

function formatApiError(status: number, body: string): string {
    try {
        const json = JSON.parse(body) as { detail?: string; error?: { message?: string } };
        const rawDetail = json.detail ?? json.error?.message;
        const detail =
            typeof rawDetail === "string"
                ? rawDetail
                : rawDetail && typeof rawDetail === "object" && "message" in rawDetail
                  ? String((rawDetail as { message?: string }).message ?? rawDetail)
                  : null;
        if (detail) {
            try {
                const nested = JSON.parse(detail) as { errors?: { title?: string; detail?: string }[] };
                const err = nested.errors?.[0];
                if (err?.title) return `${err.title}${err.detail ? `: ${err.detail}` : ""}`;
            } catch {
                /* plain string detail */
            }
            if (detail.length > 200) return `${detail.slice(0, 200)}…`;
            return detail;
        }
    } catch {
        /* not json */
    }
    return body || `Request failed (${status})`;
}

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
        throw new Error(formatApiError(res.status, detail));
    }
    const data = (await res.json()) as { voices: ElevenLabsVoice[] };
    return data.voices ?? [];
}

export async function fetchMemory(): Promise<MemoryEntry[]> {
    const res = await fetch(`${await baseUrl()}/memory`);
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(formatApiError(res.status, detail));
    }
    const data = (await res.json()) as { entries: MemoryEntry[] };
    return data.entries ?? [];
}

export async function clearMemory(): Promise<void> {
    const res = await fetch(`${await baseUrl()}/memory`, { method: "DELETE" });
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(formatApiError(res.status, detail));
    }
}

export async function fetchVoicePreview(voiceId: string, text?: string): Promise<Blob> {
    const res = await fetch(`${await baseUrl()}/tts/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: voiceId, text }),
    });
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(formatApiError(res.status, detail));
    }
    return res.blob();
}
