import { useEffect, useMemo } from "react";
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

const prettyGame = (id: string) => id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const usd = (n: number | undefined | null) => `$${(n ?? 0).toFixed(4)}`;
const usd2 = (n: number | undefined | null) => `$${(n ?? 0).toFixed(2)}`;

export const CoachScreen = ({ auth }: { auth: AuthApi }) => {
    const engine = useEngine();
    const gameItems = useMemo(() => engine.games.map((g) => ({ id: g, label: prettyGame(g) })), [engine.games]);
    const stateInfo = STATE_BADGE[engine.state] ?? STATE_BADGE.idle;

    const ttsOn = engine.config?.tts_enabled ?? true;
    const voiceOn = engine.config?.voice_input_enabled ?? true;
    const webOn = engine.config?.web_search_enabled ?? true;

    // Keep the monthly usage/quota readout fresh as cycles accrue cost on the backend.
    const cycleCount = engine.cost?.call_count ?? 0;
    useEffect(() => {
        void auth.refreshMe();
    }, [cycleCount, auth.refreshMe]);

    const me = auth.me;
    const overQuota = me ? me.quota_usd > 0 && me.used_usd >= me.quota_usd : false;

    return (
        <div className="flex h-dvh flex-col bg-primary text-primary">
            {/* Header */}
            <header className="flex items-center justify-between border-b border-secondary px-6 py-4">
                <div className="flex items-center gap-3">
                    <span className="text-lg font-semibold">AI Coach</span>
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
                            Monthly{" "}
                            <span className={overQuota ? "font-medium text-error-primary" : "font-medium text-primary"}>
                                {usd2(me.used_usd)}
                            </span>
                            {me.quota_usd > 0 && <span className="text-quaternary"> / {usd2(me.quota_usd)}</span>}
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

            <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 overflow-hidden p-6 lg:grid-cols-[1fr_320px]">
                {/* Main: controls + live feed */}
                <main className="flex min-h-0 flex-col gap-5">
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
                            You've reached this month's usage limit ({usd2(me?.quota_usd)}). It resets at the start of next month.
                        </section>
                    )}

                    <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-secondary bg-secondary">
                        <div className="border-b border-secondary px-4 py-3">
                            <h2 className="text-sm font-semibold text-secondary">Coach feed</h2>
                        </div>
                        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
                            {engine.transcript && (
                                <div className="self-end rounded-lg rounded-br-sm bg-brand-solid px-3 py-2 text-sm text-white">
                                    {engine.transcript}
                                </div>
                            )}
                            {engine.advices.length === 0 && !engine.transcript ? (
                                <p className="m-auto text-center text-sm text-tertiary">
                                    {engine.running ? "Listening for something worth saying…" : "Pick a game and press start."}
                                </p>
                            ) : (
                                engine.advices.map((a, i) => (
                                    <article key={`${a.ts}-${i}`} className="rounded-lg border border-secondary bg-primary p-3">
                                        <div className="mb-1.5 flex items-center gap-2">
                                            <Badge type="color" color={a.trigger === "voice" ? "brand" : "blue"} size="sm">
                                                {a.trigger === "voice" ? "Voice" : "Screen"}
                                            </Badge>
                                            {a.scene && (
                                                <span className="text-xs font-medium text-tertiary">{a.scene}</span>
                                            )}
                                        </div>
                                        <p className="text-md text-primary">{a.text}</p>
                                    </article>
                                ))
                            )}
                        </div>
                    </section>
                </main>

                {/* Sidebar: cost + settings */}
                <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto">
                    <section className="rounded-xl border border-secondary bg-secondary p-4">
                        <h2 className="mb-3 text-sm font-semibold text-secondary">Cost</h2>
                        <p className="text-display-xs font-semibold text-primary">{usd(engine.cost?.session_usd)}</p>
                        <p className="mb-3 text-xs text-tertiary">{engine.cost?.call_count ?? 0} cycles this session</p>
                        <dl className="flex flex-col gap-1.5 text-sm">
                            {[
                                ["Last cycle", engine.cost?.cycle_usd],
                                ["Vision", engine.cost?.breakdown.vision_usd],
                                ["Voice (STT)", engine.cost?.breakdown.stt_usd],
                                ["Speech (TTS)", engine.cost?.breakdown.tts_usd],
                                ["Web", engine.cost?.breakdown.web_usd],
                            ].map(([label, value]) => (
                                <div key={label as string} className="flex justify-between">
                                    <dt className="text-tertiary">{label}</dt>
                                    <dd className="font-medium text-secondary">{usd(value as number)}</dd>
                                </div>
                            ))}
                        </dl>
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
                                    items={engine.monitors.map((m) => ({ id: String(m.index), label: `${m.index}: ${m.width}×${m.height}` }))}
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
                </aside>
            </div>
        </div>
    );
};
