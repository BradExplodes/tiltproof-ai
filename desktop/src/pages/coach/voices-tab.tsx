import { memo, useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { Check, Play, VolumeMax } from "@untitledui/icons";
import { Badge } from "@/components/base/badges/badges";
import { Button } from "@/components/base/buttons/button";
import { fetchVoicePreview, fetchVoices } from "@/lib/engine-api";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import type { ElevenLabsVoice } from "@/lib/engine-types";
import { useCoachNav } from "@/pages/coach/coach-nav";
import { configEqual } from "@/pages/coach/shared";

const VoiceCard = memo(function VoiceCard({
    voice,
    selected,
    previewing,
    onSelect,
    onPreview,
}: {
    voice: ElevenLabsVoice;
    selected: boolean;
    previewing: boolean;
    onSelect: () => void;
    onPreview: () => void;
}) {
    const accent = voice.labels.accent;
    const gender = voice.labels.gender;
    const useCase = voice.labels.use_case;

    return (
        <div
            role="button"
            tabIndex={0}
            onClick={onSelect}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect();
                }
            }}
            className={`flex w-full cursor-pointer flex-col gap-3 rounded-xl border p-4 text-left transition duration-100 ${
                selected
                    ? "border-brand-solid bg-brand-primary_alt ring-1 ring-brand-solid"
                    : "border-secondary bg-secondary hover:border-primary hover:bg-primary_hover"
            }`}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-primary">{voice.name}</h3>
                        {selected && <Check className="size-4 shrink-0 text-fg-brand-secondary" />}
                    </div>
                    {voice.description && <p className="mt-1 line-clamp-2 text-sm text-tertiary">{voice.description}</p>}
                </div>
                <Button
                    color="secondary"
                    size="sm"
                    iconLeading={previewing ? VolumeMax : Play}
                    isLoading={previewing}
                    onClick={(e: MouseEvent) => {
                        e.stopPropagation();
                        onPreview();
                    }}
                >
                    Preview
                </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
                {voice.category && (
                    <Badge type="color" color="gray" size="sm">
                        {voice.category}
                    </Badge>
                )}
                {accent && (
                    <Badge type="color" color="blue" size="sm">
                        {accent}
                    </Badge>
                )}
                {gender && (
                    <Badge type="color" color="indigo" size="sm">
                        {gender}
                    </Badge>
                )}
                {useCase && (
                    <Badge type="color" color="brand" size="sm">
                        {useCase}
                    </Badge>
                )}
            </div>
        </div>
    );
});

export const VoicesTab = memo(function VoicesTab() {
    const actions = useEngineActions();
    const { goToCoach } = useCoachNav();
    const config = useEngineSelector((s) => s.config, configEqual);
    const running = useEngineSelector((s) => s.running);
    const selectedVoiceId = config?.tts_voice_id ?? null;

    const [voices, setVoices] = useState<ElevenLabsVoice[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [previewingId, setPreviewingId] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setError(null);
        void fetchVoices()
            .then((list) => {
                if (!cancelled) setVoices(list);
            })
            .catch((e) => {
                if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load voices");
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const stopPreview = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        setPreviewingId(null);
    }, []);

    useEffect(() => () => stopPreview(), [stopPreview]);

    const handlePreview = useCallback(
        async (voiceId: string) => {
            stopPreview();
            setPreviewingId(voiceId);
            try {
                const blob = await fetchVoicePreview(voiceId);
                const url = URL.createObjectURL(blob);
                const audio = new Audio(url);
                audioRef.current = audio;
                audio.onended = () => {
                    URL.revokeObjectURL(url);
                    setPreviewingId(null);
                    audioRef.current = null;
                };
                audio.onerror = () => {
                    URL.revokeObjectURL(url);
                    setPreviewingId(null);
                    audioRef.current = null;
                };
                await audio.play();
            } catch (e) {
                setPreviewingId(null);
                setError(e instanceof Error ? e.message : "Preview failed");
            }
        },
        [stopPreview],
    );

    const handleSelect = useCallback(
        (voiceId: string) => {
            if (selectedVoiceId !== voiceId) {
                actions.updateConfig({ tts_voice_id: voiceId });
            }
            goToCoach();
        },
        [actions, selectedVoiceId, goToCoach],
    );

    return (
        <div className="mx-auto flex w-full max-w-4xl min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
            <div>
                <h2 className="text-md font-semibold text-primary">Coach voice</h2>
                <p className="mt-1 text-sm text-tertiary">
                    Choose an ElevenLabs voice for spoken coaching. {running ? "Changing voice restarts the session." : ""}
                </p>
            </div>

            {loading && <p className="text-sm text-tertiary">Loading voices…</p>}
            {error && (
                <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
                    {error}
                </section>
            )}

            {!loading && !error && voices.length === 0 && (
                <p className="text-sm text-tertiary">No voices available.</p>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
                {voices.map((voice) => (
                    <VoiceCard
                        key={voice.voice_id}
                        voice={voice}
                        selected={selectedVoiceId === voice.voice_id}
                        previewing={previewingId === voice.voice_id}
                        onSelect={() => handleSelect(voice.voice_id)}
                        onPreview={() => void handlePreview(voice.voice_id)}
                    />
                ))}
            </div>
        </div>
    );
});
