import { memo, useEffect, useMemo, useRef } from "react";
import { LogOut01, Microphone01, Play, Globe01, VolumeMax } from "@untitledui/icons";
import { Badge, BadgeWithDot } from "@/components/base/badges/badges";
import type { BadgeColors } from "@/components/base/badges/badge-types";
import { Button } from "@/components/base/buttons/button";
import { Select } from "@/components/base/select/select";
import { Toggle } from "@/components/base/toggle/toggle";
import { useAuthActions, useAuthSelector } from "@/lib/auth";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import type { EngineState, FeedItem, PerfEvent, RuntimeConfig } from "@/lib/engine-types";

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

const ACTIVITY: Partial<Record<EngineState, string>> = {
    starting: "Starting up…",
    capturing: "Reading your screen…",
    transcribing: "Transcribing your speech…",
    thinking: "Thinking…",
    speaking: "Speaking…",
};

const prettyGame = (id: string) => id.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const configEqual = (a: RuntimeConfig | null, b: RuntimeConfig | null): boolean => {
    if (a === b) return true;
    if (!a || !b) return false;
    return (
        a.game_id === b.game_id &&
        a.monitor_index === b.monitor_index &&
        a.interval_seconds === b.interval_seconds &&
        a.tts_enabled === b.tts_enabled &&
        a.voice_input_enabled === b.voice_input_enabled &&
        a.ocr_enabled === b.ocr_enabled &&
        a.web_search_enabled === b.web_search_enabled
    );
};

const perfEqual = (a: PerfEvent | null, b: PerfEvent | null): boolean => {
    if (a === b) return true;
    if (!a || !b) return false;
    return a.phase === b.phase && a.duration_ms === b.duration_ms && a.grab_ms === b.grab_ms && a.encode_ms === b.encode_ms;
};

const usageFromMe = (me: { used_usd: number; quota_usd: number } | null) => {
    const unlimited = me ? me.quota_usd <= 0 : false;
    const usagePct = me && me.quota_usd > 0 ? Math.min(100, (me.used_usd / me.quota_usd) * 100) : 0;
    const overQuota = !unlimited && me != null && usagePct >= 100;
    return { unlimited, usagePct, overQuota };
};

const FeedBubble = memo(function FeedBubble({ item }: { item: FeedItem }) {
    if (item.kind === "user") {
        return (
            <div className="max-w-[85%] self-end rounded-lg rounded-br-sm bg-brand-solid px-3 py-2 text-sm text-white">
                {item.text}
            </div>
        );
    }
    return (
        <article className="max-w-[92%] self-start rounded-lg border border-secondary bg-primary p-3">
            <div className="mb-1.5 flex items-center gap-2">
                <Badge type="color" color={item.advice.trigger === "voice" ? "brand" : "blue"} size="sm">
                    {item.advice.trigger === "voice" ? "Voice" : "Screen"}
                </Badge>
                {item.advice.scene && <span className="text-xs font-medium text-tertiary">{item.advice.scene}</span>}
            </div>
            <p className="text-md text-primary">{item.advice.text}</p>
        </article>
    );
});

const EngineStateBadge = memo(function EngineStateBadge() {
    const state = useEngineSelector((s) => s.state);
    const info = STATE_BADGE[state] ?? STATE_BADGE.idle;
    return (
        <BadgeWithDot type="pill-color" color={info.color} size="md">
            {info.label}
        </BadgeWithDot>
    );
});

const EngineConnectionBadge = memo(function EngineConnectionBadge() {
    const connected = useEngineSelector((s) => s.connected);
    return (
        <BadgeWithDot type="pill-color" color={connected ? "success" : "gray"} size="sm">
            {connected ? "Engine connected" : "Connecting…"}
        </BadgeWithDot>
    );
});

const UsageHeaderLabel = memo(function UsageHeaderLabel() {
    const me = useAuthSelector((s) => s.me);
    const { unlimited, usagePct, overQuota } = usageFromMe(me);
    if (!me) return null;
    return (
        <span className="text-sm text-tertiary">
            Usage{" "}
            <span className={overQuota ? "font-medium text-error-primary" : "font-medium text-primary"}>
                {unlimited ? "Unlimited" : `${Math.round(usagePct)}%`}
            </span>
        </span>
    );
});

const AccountControls = memo(function AccountControls() {
    const email = useAuthSelector((s) => s.session?.email ?? null);
    const busy = useAuthSelector((s) => s.busy);
    const { logout } = useAuthActions();

    return (
        <div className="flex items-center gap-2 border-l border-secondary pl-3">
            <span className="max-w-44 truncate text-sm text-secondary" title={email ?? undefined}>
                {email}
            </span>
            <Button color="tertiary" size="sm" iconLeading={LogOut01} isLoading={busy} onClick={() => void logout()}>
                Sign out
            </Button>
        </div>
    );
});

const CoachHeader = memo(function CoachHeader() {
    return (
        <header className="flex items-center justify-between border-b border-secondary px-6 py-4">
            <div className="flex items-center gap-3">
                <span className="text-lg font-semibold">Tiltproof AI</span>
                <EngineStateBadge />
            </div>
            <div className="flex items-center gap-3">
                <EngineConnectionBadge />
                <UsageHeaderLabel />
                <AccountControls />
            </div>
        </header>
    );
});

const OverQuotaBanner = memo(function OverQuotaBanner() {
    const me = useAuthSelector((s) => s.me);
    const { overQuota } = usageFromMe(me);
    if (!overQuota) return null;
    return (
        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
            You've reached this month's usage limit. It resets at the start of next month.
        </section>
    );
});

const UsagePanel = memo(function UsagePanel() {
    const me = useAuthSelector((s) => s.me);
    const { unlimited, usagePct, overQuota } = usageFromMe(me);

    return (
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
                        className={`h-full rounded-full ${overQuota ? "bg-error-solid" : "bg-brand-solid"}`}
                        style={{ width: `${usagePct}%` }}
                    />
                </div>
            )}
            <p className="mt-2 text-xs text-tertiary">
                {unlimited ? "No usage cap on your account." : "Resets at the start of each month."}
            </p>
        </section>
    );
});

const GameControls = memo(function GameControls() {
    const actions = useEngineActions();
    const gameId = useEngineSelector((s) => s.gameId);
    const running = useEngineSelector((s) => s.running);
    const games = useEngineSelector((s) => s.games);
    const me = useAuthSelector((s) => s.me);
    const { overQuota } = usageFromMe(me);
    const gameItems = useMemo(() => games.map((g) => ({ id: g, label: prettyGame(g) })), [games]);

    return (
        <section className="flex flex-wrap items-end gap-3 rounded-xl border border-secondary bg-secondary p-4">
            <div className="min-w-56 flex-1">
                <Select
                    label="Game"
                    placeholder="Choose a game"
                    size="md"
                    selectedKey={gameId ?? undefined}
                    onSelectionChange={(key) => key && actions.setGame(String(key))}
                    items={gameItems}
                >
                    {(item) => <Select.Item id={item.id} label={item.label} />}
                </Select>
            </div>
            {running ? (
                <Button color="primary-destructive" size="md" onClick={() => actions.stop()}>
                    Stop coaching
                </Button>
            ) : (
                <Button
                    color="primary"
                    size="md"
                    iconLeading={Play}
                    isDisabled={!gameId || overQuota}
                    onClick={() => actions.start()}
                >
                    Start coaching
                </Button>
            )}
        </section>
    );
});

const SettingsPanel = memo(function SettingsPanel() {
    const actions = useEngineActions();
    const config = useEngineSelector((s) => s.config, configEqual);
    const monitors = useEngineSelector((s) => s.monitors);
    const lastPerf = useEngineSelector((s) => s.lastPerf, perfEqual);
    const running = useEngineSelector((s) => s.running);

    const ttsOn = config?.tts_enabled ?? true;
    const voiceOn = config?.voice_input_enabled ?? true;
    const ocrOn = config?.ocr_enabled ?? true;
    const webOn = config?.web_search_enabled ?? true;

    return (
        <section className="rounded-xl border border-secondary bg-secondary p-4">
            <h2 className="mb-3 text-sm font-semibold text-secondary">Settings</h2>
            <div className="flex flex-col gap-4">
                <Toggle size="sm" label="Spoken coaching (TTS)" isSelected={ttsOn} onChange={(v) => actions.updateConfig({ tts_enabled: v })} />
                <Toggle size="sm" label="Voice input (mic)" isSelected={voiceOn} onChange={(v) => actions.updateConfig({ voice_input_enabled: v })} />
                <Toggle size="sm" label="Screen OCR (local)" isSelected={ocrOn} onChange={(v) => actions.updateConfig({ ocr_enabled: v })} />
                <p className="-mt-2 text-xs text-tertiary">
                    Local text recognition for voice questions and drift checks between interval captures.
                </p>
                {lastPerf && (
                    <p className="font-mono text-xs text-tertiary">
                        Perf: {lastPerf.phase} {lastPerf.duration_ms}ms
                        {lastPerf.backend != null ? ` [${String(lastPerf.backend)}]` : ""}
                        {lastPerf.grab_ms != null ? ` (grab ${lastPerf.grab_ms}ms encode ${lastPerf.encode_ms}ms)` : ""}
                    </p>
                )}
                <Toggle size="sm" label="Web research" isSelected={webOn} onChange={(v) => actions.updateConfig({ web_search_enabled: v })} />
                {monitors.length > 1 && (
                    <Select
                        label="Capture monitor"
                        size="sm"
                        selectedKey={String(config?.monitor_index ?? 1)}
                        onSelectionChange={(key) => actions.updateConfig({ monitor_index: Number(key) })}
                        items={monitors.map((m) => ({
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
                <span className="ml-auto">{running ? "Changes restart the session" : ""}</span>
            </p>
        </section>
    );
});

const EngineErrorBanner = memo(function EngineErrorBanner() {
    const error = useEngineSelector((s) => s.error);
    if (!error) return null;
    return (
        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
            {error}
        </section>
    );
});

const FeedActivityLabel = memo(function FeedActivityLabel() {
    const state = useEngineSelector((s) => s.state);
    const activity = ACTIVITY[state];
    if (!activity) return null;
    return (
        <span className="flex items-center gap-1.5 text-xs font-medium text-tertiary">
            <span className="size-1.5 rounded-full bg-brand-solid" />
            {activity}
        </span>
    );
});

const FeedMessages = memo(function FeedMessages() {
    const feed = useEngineSelector((s) => s.feed);
    const state = useEngineSelector((s) => s.state);
    const running = useEngineSelector((s) => s.running);
    const activity = ACTIVITY[state];
    const feedEndRef = useRef<HTMLDivElement | null>(null);
    const prevLenRef = useRef(0);

    useEffect(() => {
        if (feed.length !== prevLenRef.current) {
            prevLenRef.current = feed.length;
            feedEndRef.current?.scrollIntoView({ block: "end" });
        }
    }, [feed.length]);

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
            {feed.length === 0 && !activity ? (
                <p className="m-auto text-center text-sm text-tertiary">
                    {running ? "Listening for something worth saying…" : "Pick a game and press start."}
                </p>
            ) : (
                feed.map((item) => <FeedBubble key={item.id} item={item} />)
            )}
            {activity && (
                <div className="flex items-center gap-2 self-start rounded-lg border border-secondary bg-primary px-3 py-2 text-sm text-tertiary">
                    <span className="size-1.5 rounded-full bg-brand-solid" />
                    {activity}
                </div>
            )}
            <div ref={feedEndRef} />
        </div>
    );
});

const CoachFeed = memo(function CoachFeed() {
    return (
        <aside className="flex min-h-0 flex-col rounded-xl border border-secondary bg-secondary">
            <div className="flex items-center justify-between border-b border-secondary px-4 py-3">
                <h2 className="text-sm font-semibold text-secondary">Coach feed</h2>
                <FeedActivityLabel />
            </div>
            <FeedMessages />
        </aside>
    );
});

const UsageRefresh = memo(function UsageRefresh() {
    const cycleCount = useEngineSelector((s) => s.cost?.call_count ?? 0);
    const { refreshMe } = useAuthActions();
    useEffect(() => {
        void refreshMe();
    }, [cycleCount, refreshMe]);
    return null;
});

/** Layout shell only — no hooks, no engine/auth subscriptions. */
export const CoachScreen = memo(function CoachScreen() {
    return (
        <div className="flex h-dvh flex-col bg-primary text-primary">
            <UsageRefresh />
            <CoachHeader />
            <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 overflow-hidden p-6 lg:grid-cols-[1fr_380px]">
                <main className="flex min-h-0 flex-col gap-5 overflow-y-auto">
                    <GameControls />
                    <OverQuotaBanner />
                    <UsagePanel />
                    <SettingsPanel />
                    <EngineErrorBanner />
                </main>
                <CoachFeed />
            </div>
        </div>
    );
});
