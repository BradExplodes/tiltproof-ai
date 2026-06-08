import { memo, useCallback, useEffect, useState } from "react";
import { Microphone01, Globe01, User01, VolumeMax } from "@untitledui/icons";
import { Input } from "@/components/base/input/input";
import { Select } from "@/components/base/select/select";
import { Slider } from "@/components/base/slider/slider";
import { Toggle } from "@/components/base/toggle/toggle";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import { configEqual } from "@/pages/coach/shared";
import { MemoryButton } from "@/pages/coach/memory-modal";

const MIN_INTERVAL = 10;
const MAX_INTERVAL = 120;
const DEFAULT_INTERVAL = 20;

const clampInterval = (value: number) => Math.min(MAX_INTERVAL, Math.max(MIN_INTERVAL, Math.round(value)));

const formatInterval = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const rem = seconds % 60;
    return rem === 0 ? `${mins}m` : `${mins}m ${rem}s`;
};

export const SettingsPanel = memo(function SettingsPanel() {
    const actions = useEngineActions();
    const config = useEngineSelector((s) => s.config, configEqual);
    const monitors = useEngineSelector((s) => s.monitors);
    const running = useEngineSelector((s) => s.running);

    const ttsOn = config?.tts_enabled ?? true;
    const voiceOn = config?.voice_input_enabled ?? true;
    const ocrOn = config?.ocr_enabled ?? true;
    const webOn = config?.web_search_enabled ?? true;

    const savedName = config?.player_name ?? "";
    const [name, setName] = useState(savedName);
    useEffect(() => setName(savedName), [savedName]);

    const commitName = useCallback(() => {
        const trimmed = name.trim();
        if (trimmed !== savedName) actions.updateConfig({ player_name: trimmed });
    }, [name, savedName, actions]);

    const savedInterval = clampInterval(config?.interval_seconds ?? DEFAULT_INTERVAL);
    const [interval, setIntervalValue] = useState(savedInterval);
    useEffect(() => setIntervalValue(savedInterval), [savedInterval]);

    const commitInterval = useCallback(
        (value: number) => {
            const next = clampInterval(value);
            if (next !== savedInterval) actions.updateConfig({ interval_seconds: next });
        },
        [savedInterval, actions],
    );

    return (
        <section className="rounded-xl border border-secondary bg-secondary p-4">
            <h2 className="mb-3 text-sm font-semibold text-secondary">Coaching</h2>
            <div className="flex flex-col gap-4">
                <Input
                    size="sm"
                    icon={User01}
                    label="Your name"
                    placeholder="What should the coach call you?"
                    value={name}
                    onChange={setName}
                    onBlur={commitName}
                    hint="The coach will use this to refer to you."
                />

                <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-secondary">Update frequency</span>
                        <span className="font-mono text-sm text-primary">{formatInterval(interval)}</span>
                    </div>
                    <Slider
                        aria-label="Update frequency"
                        minValue={MIN_INTERVAL}
                        maxValue={MAX_INTERVAL}
                        step={5}
                        value={interval}
                        onChange={(v) => setIntervalValue(clampInterval(v as number))}
                        onChangeEnd={(v) => commitInterval(v as number)}
                    />
                    <p className="text-xs text-tertiary">How often the coach reads your screen when idle (10s–2m).</p>
                </div>

                <Toggle size="sm" label="Spoken coaching (ElevenLabs)" isSelected={ttsOn} onChange={(v) => actions.updateConfig({ tts_enabled: v })} />
                <Toggle size="sm" label="Voice input (mic)" isSelected={voiceOn} onChange={(v) => actions.updateConfig({ voice_input_enabled: v })} />
                <Toggle size="sm" label="Screen OCR (local)" isSelected={ocrOn} onChange={(v) => actions.updateConfig({ ocr_enabled: v })} />
                <p className="-mt-2 text-xs text-tertiary">
                    Local text recognition for voice questions and drift checks between interval captures.
                </p>
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

                <div className="flex flex-col gap-1.5 border-t border-secondary pt-4">
                    <span className="text-sm font-medium text-secondary">Coach memory</span>
                    <p className="text-xs text-tertiary">See what the AI has remembered about you over time.</p>
                    <div className="mt-1">
                        <MemoryButton />
                    </div>
                </div>
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
