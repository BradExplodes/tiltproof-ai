import { memo, useEffect, useState } from "react";
import { Check, ChevronRight, Grid01, Settings01, User01 } from "@untitledui/icons";
import { Badge } from "@/components/base/badges/badges";
import { TILTPROOF_ICON_URL } from "@/lib/branding";
import { fetchVoices } from "@/lib/engine-api";
import { getGameInfo } from "@/lib/games";
import { useEngineSelector } from "@/lib/engine";
import { useCoachNav, type AppTab } from "@/pages/coach/coach-nav";
import { configEqual, isCoachReady } from "@/pages/coach/shared";

const SetupRow = memo(function SetupRow({
    icon: Icon,
    label,
    value,
    hint,
    complete,
    thumbnail,
    onClick,
}: {
    icon: typeof Grid01;
    label: string;
    value: string;
    hint?: string;
    complete: boolean;
    thumbnail?: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="flex w-full items-center gap-3 rounded-xl border border-secondary bg-secondary p-4 text-left transition duration-100 hover:border-primary hover:bg-primary_hover"
        >
            <div
                className={`flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg ${
                    complete ? "bg-brand-primary_alt text-fg-brand-secondary" : "bg-primary text-tertiary"
                }`}
            >
                {thumbnail ? (
                    <img src={thumbnail} alt="" className="size-full object-cover" />
                ) : complete ? (
                    <Check className="size-5" />
                ) : (
                    <Icon className="size-5" />
                )}
            </div>
            <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-secondary">{label}</p>
                <p className="truncate text-sm font-semibold text-primary">{value}</p>
                {hint && <p className="mt-0.5 text-xs text-tertiary">{hint}</p>}
            </div>
            <ChevronRight className="size-5 shrink-0 text-tertiary" />
        </button>
    );
});

export const CoachSetup = memo(function CoachSetup() {
    const { setTab } = useCoachNav();
    const gameId = useEngineSelector((s) => s.gameId);
    const config = useEngineSelector((s) => s.config, configEqual);
    const voiceId = config?.tts_voice_id ?? null;
    const ready = isCoachReady(gameId, voiceId);

    const [voiceName, setVoiceName] = useState<string | null>(null);

    useEffect(() => {
        if (!voiceId) {
            setVoiceName(null);
            return;
        }
        let cancelled = false;
        void fetchVoices()
            .then((list) => {
                if (cancelled) return;
                setVoiceName(list.find((v) => v.voice_id === voiceId)?.name ?? null);
            })
            .catch(() => {
                if (!cancelled) setVoiceName(null);
            });
        return () => {
            cancelled = true;
        };
    }, [voiceId]);

    const game = gameId ? getGameInfo(gameId) : null;
    const go = (tab: AppTab) => () => setTab(tab);

    const gameThumb = game?.thumbnail ?? (gameId ? TILTPROOF_ICON_URL : undefined);

    const settingsSummary = [
        config?.tts_enabled !== false && "Speech",
        config?.voice_input_enabled !== false && "Mic",
        config?.ocr_enabled !== false && "OCR",
    ]
        .filter(Boolean)
        .join(" · ");

    return (
        <section className="mx-auto flex w-full max-w-2xl flex-col gap-4">
            <div>
                <h2 className="text-md font-semibold text-primary">Get ready to coach</h2>
                <p className="mt-1 text-sm text-tertiary">
                    Set up your game and voice, then start a session from the coach feed.
                </p>
            </div>

            {ready && (
                <div className="flex items-center gap-2 rounded-xl border border-brand-subtle bg-brand-primary_alt px-4 py-3">
                    <Badge type="color" color="brand" size="sm">
                        Ready
                    </Badge>
                    <p className="text-sm text-secondary">You're set — press Start coaching in the feed.</p>
                </div>
            )}

            <div className="flex flex-col gap-2">
                <SetupRow
                    icon={Grid01}
                    label="Game"
                    value={game?.name ?? "Select a game"}
                    hint={game ? game.tagline : "Choose what you're playing"}
                    complete={Boolean(gameId)}
                    thumbnail={gameThumb}
                    onClick={go("games")}
                />

                <SetupRow
                    icon={User01}
                    label="Coach voice"
                    value={voiceName ?? (voiceId ? "Voice selected" : "Select a voice")}
                    hint={voiceId ? "ElevenLabs voice for spoken coaching" : "Pick how your coach sounds"}
                    complete={Boolean(voiceId)}
                    onClick={go("voices")}
                />

                <SetupRow
                    icon={Settings01}
                    label="Settings"
                    value={settingsSummary || "Default coaching options"}
                    hint="Monitor, speech, mic, and OCR"
                    complete
                    onClick={go("settings")}
                />
            </div>
        </section>
    );
});
