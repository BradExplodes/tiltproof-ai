import { memo } from "react";
import { Microphone01, Globe01, VolumeMax } from "@untitledui/icons";
import { Select } from "@/components/base/select/select";
import { Toggle } from "@/components/base/toggle/toggle";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import { configEqual, perfEqual } from "@/pages/coach/shared";

export const SettingsPanel = memo(function SettingsPanel() {
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
            <h2 className="mb-3 text-sm font-semibold text-secondary">Coaching</h2>
            <div className="flex flex-col gap-4">
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
                {lastPerf && (
                    <p className="font-mono text-xs text-tertiary">
                        Perf: {lastPerf.phase} {lastPerf.duration_ms}ms
                        {lastPerf.backend != null ? ` [${String(lastPerf.backend)}]` : ""}
                        {lastPerf.grab_ms != null ? ` (grab ${lastPerf.grab_ms}ms encode ${lastPerf.encode_ms}ms)` : ""}
                    </p>
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
