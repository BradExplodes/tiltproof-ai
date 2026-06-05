import { useEffect, useMemo, useRef } from "react";
import { LogOut01, Microphone01, Play, Globe01, VolumeMax } from "@untitledui/icons";
import { Badge, BadgeWithDot } from "@/components/base/badges/badges";
import type { BadgeColors } from "@/components/base/badges/badge-types";
import { Button } from "@/components/base/buttons/button";
import { Select } from "@/components/base/select/select";
import { Toggle } from "@/components/base/toggle/toggle";
import type { AuthApi } from "@/lib/auth";
import { type EngineState, useEngine } from "@/lib/engine";

const STATE_BADGE: Record<EngineState, { color: BadgeColors; label: string }> = {
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

// Live "reasoning" shown in the feed while the engine is mid-action.
const ACTIVITY: Partial<Record<EngineState, string>> = {
    starting: "Starting up…",
    capturing: "Reading your screen…",
    transcribing: "Transcribing your speech…",
    thinking: "Thinking…",
    speaking: "Speaking…",
};

const prettyGame = (id: string) => id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const CoachScreen = ({ auth }: { auth: AuthApi }) => {
    const engine = useEngine();
    const gameItems = useMemo(() => engine.games.map((g) => ({ id: g, label: prettyGame(g) })), [engine.games]);
    const stateInfo = STATE_BADGE[engine.state] ?? STATE_BADGE.idle;

    const ttsOn = engine.config?.tts_enabled ?? true;
    const voiceOn = engine.config?.voice_input_enabled ?? true;
    const ocrOn = engine.config?.ocr_enabled ?? true;
    const webOn = engine.config?.web_search_enabled ?? true;

    // Refresh usage as cycles accrue cost on the backend.
    const cycleCount = engine.cost?.call_count ?? 0;
    useEffect(() => {
        void auth.refreshMe();
    }, [cycleCount, auth.refreshMe]);

    const me = auth.me;
    const unlimited = me ? me.quota_usd <= 0 : false;
    const usagePct = me && me.quota_usd > 0 ? Math.min(100, (me.used_usd / me.quota_usd) * 100) : 0;
    const overQuota = !unlimited && me != null && usagePct >= 100;

    const activity = ACTIVITY[engine.state];

    // Keep the feed pinned to the newest message/activity.
    const feedEndRef = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        feedEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [engine.feed, activity]);

    return (
        <div className="flex h-dvh flex-col bg-primary text-primary">
            <header className="flex items-center justify-between border-b border-secondary px-6 py-4">
                <div className="flex items-center gap-3">
                    <span className="text-lg font-semibold">Tiltproof AI</span>
                    <BadgeWithDot type="pill-color" color={stateInfo.color} size="md">
                        {stateInfo.label}
                    </BadgeWithDot>
                </div>
                <div className="flex items-center gap-3">
                    <BadgeWithDot type="pill-color" color={engine.connected ? "success" : "gray"} size="sm">
                        {engine.connected ? "Engine connected" : "Connecting…"}
                    </BadgeWithDot>
                    {me && (
                        <span className="text-sm text-tertiary">
                            Usage{" "}
                            <span className={overQuota ? "font-medium text-error-primary" : "font-medium text-primary"}>
                                {unlimited ? "Unlimited" : `${Math.round(usagePct)}%`}
                            </span>
                        </span>
                    )}
                    <div className="flex items-center gap-2 border-l border-secondary pl-3">
                        <span className="max-w-44 truncate text-sm text-secondary" title={auth.session?.email}>
                            {auth.session?.email}
                        </span>
                        <Button
                            color="tertiary"
                            size="sm"
                            iconLeading={LogOut01}
                            isLoading={auth.busy}
                            onClick={() => void auth.logout()}
                        >
                            Sign out
                        </Button>
                    </div>
                </div>
            </header>

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 overflow-hidden p-6 lg:grid-cols-[1fr_380px]">
                {/* Main: controls + room for future panels */}
                <main className="flex min-h-0 flex-col gap-5 overflow-y-auto">
                    <section className="flex flex-wrap items-end gap-3 rounded-xl border border-secondary bg-secondary p-4">
                        <div className="min-w-56 flex-1">
                            <Select
                                label="Game"
                                placeholder="Choose a game"
                                size="md"
                                selectedKey={engine.gameId ?? undefined}
                                onSelectionChange={(key) => key && engine.setGame(String(key))}
                                items={gameItems}
                            >
                                {(item) => <Select.Item id={item.id} label={item.label} />}
                            </Select>
                        </div>
                        {engine.running ? (
                            <Button color="primary-destructive" size="md" onClick={() => engine.stop()}>
                                Stop coaching
                            </Button>
                        ) : (
                            <Button
                                color="primary"
                                size="md"
                                iconLeading={Play}
                                isDisabled={!engine.gameId || overQuota}
                                onClick={() => engine.start()}
                            >
                                Start coaching
                            </Button>
                        )}
                    </section>

                    {overQuota && (
                        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
                            You've reached this month's usage limit. It resets at the start of next month.
                        </section>
                    )}

                    <section className="rounded-xl border border-secondary bg-secondary p-4">
                        <div className="mb-2 flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-secondary">Usage this month</h2>
                            <span className="text-sm font-medium text-primary">
                                {unlimited ? "Unlimited" : `${Math.round(usagePct)}%`}
                            </span>
                        </div>
                        {!unlimited && (
                            <div className="h-2 w-full overflow-hidden rounded-full bg-tertiary">
                                <div
                                    className={`h-full rounded-full transition-all ${overQuota ? "bg-error-solid" : "bg-brand-solid"}`}
                                    style={{ width: `${usagePct}%` }}
                                />
                            </div>
                        )}
                        <p className="mt-2 text-xs text-tertiary">
                            {unlimited ? "No usage cap on your account." : "Resets at the start of each month."}
                        </p>
                    </section>

                    <section className="rounded-xl border border-secondary bg-secondary p-4">
                        <h2 className="mb-3 text-sm font-semibold text-secondary">Settings</h2>
                        <div className="flex flex-col gap-4">
                            <Toggle
                                size="sm"
                                label="Spoken coaching (TTS)"
                                isSelected={ttsOn}
                                onChange={(v) => engine.updateConfig({ tts_enabled: v })}
                            />
                            <Toggle
                                size="sm"
                                label="Voice input (mic)"
                                isSelected={voiceOn}
                                onChange={(v) => engine.updateConfig({ voice_input_enabled: v })}
                            />
                            <Toggle
                                size="sm"
                                label="Screen OCR (local)"
                                isSelected={ocrOn}
                                onChange={(v) => engine.updateConfig({ ocr_enabled: v })}
                            />
                            <p className="-mt-2 text-xs text-tertiary">
                                Turn off to skip Tesseract/OpenCV and test whether local OCR is causing lag.
                                Intervals and vision coaching still run.
                            </p>
                            <Toggle
                                size="sm"
                                label="Web research"
                                isSelected={webOn}
                                onChange={(v) => engine.updateConfig({ web_search_enabled: v })}
                            />
                            {engine.monitors.length > 1 && (
                                <Select
                                    label="Capture monitor"
                                    size="sm"
                                    selectedKey={String(engine.config?.monitor_index ?? 1)}
                                    onSelectionChange={(key) => engine.updateConfig({ monitor_index: Number(key) })}
                                    items={engine.monitors.map((m) => ({
                                        id: String(m.index),
                                        label: `${m.index}: ${m.width}×${m.height}`,
                                    }))}
                                >
                                    {(item) => <Select.Item id={item.id} label={item.label} />}
                                </Select>
                            )}
                        </div>
                        <p className="mt-4 flex items-center gap-2 text-xs text-tertiary">
                            <Microphone01 className="size-3.5" /> Mic
                            <VolumeMax className="size-3.5" /> Speech
                            <Globe01 className="size-3.5" /> Web
                            <span className="ml-auto">{engine.running ? "Changes restart the session" : ""}</span>
                        </p>
                    </section>

                    {engine.error && (
                        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
                            {engine.error}
                        </section>
                    )}
                </main>

                {/* Right: coach feed widget */}
                <aside className="flex min-h-0 flex-col rounded-xl border border-secondary bg-secondary">
                    <div className="flex items-center justify-between border-b border-secondary px-4 py-3">
                        <h2 className="text-sm font-semibold text-secondary">Coach feed</h2>
                        {activity && (
                            <span className="flex items-center gap-1.5 text-xs font-medium text-tertiary">
                                <span className="size-1.5 animate-pulse rounded-full bg-brand-solid" />
                                {activity}
                            </span>
                        )}
                    </div>
                    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
                        {engine.feed.length === 0 && !activity ? (
                            <p className="m-auto text-center text-sm text-tertiary">
                                {engine.running ? "Listening for something worth saying…" : "Pick a game and press start."}
                            </p>
                        ) : (
                            engine.feed.map((item) =>
                                item.kind === "user" ? (
                                    <div
                                        key={item.id}
                                        className={`max-w-[85%] self-end rounded-lg rounded-br-sm px-3 py-2 text-sm text-white ${
                                            item.partial ? "bg-brand-solid/80" : "bg-brand-solid"
                                        }`}
                                    >
                                        {item.text}
                                        {item.partial && (
                                            <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-white/90 align-middle" />
                                        )}
                                    </div>
                                ) : (
                                    <article
                                        key={item.id}
                                        className="max-w-[92%] self-start rounded-lg border border-secondary bg-primary p-3"
                                    >
                                        <div className="mb-1.5 flex items-center gap-2">
                                            <Badge
                                                type="color"
                                                color={item.advice.trigger === "voice" ? "brand" : "blue"}
                                                size="sm"
                                            >
                                                {item.advice.trigger === "voice" ? "Voice" : "Screen"}
                                            </Badge>
                                            {item.advice.scene && (
                                                <span className="text-xs font-medium text-tertiary">{item.advice.scene}</span>
                                            )}
                                        </div>
                                        <p className="text-md text-primary">{item.advice.text}</p>
                                    </article>
                                ),
                            )
                        )}
                        {activity && (
                            <div className="flex items-center gap-2 self-start rounded-lg border border-secondary bg-primary px-3 py-2 text-sm text-tertiary">
                                <span className="size-1.5 animate-pulse rounded-full bg-brand-solid" />
                                {activity}
                            </div>
                        )}
                        <div ref={feedEndRef} />
                    </div>
                </aside>
            </div>
        </div>
    );
};
