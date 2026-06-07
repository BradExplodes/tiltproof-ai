import { memo, useMemo } from "react";
import { Check } from "@untitledui/icons";
import { Badge } from "@/components/base/badges/badges";
import { TILTPROOF_ICON_URL } from "@/lib/branding";
import { getGameInfo } from "@/lib/games";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import { useCoachNav } from "@/pages/coach/coach-nav";

const GameCard = memo(function GameCard({
    gameId,
    selected,
    onSelect,
}: {
    gameId: string;
    selected: boolean;
    onSelect: () => void;
}) {
    const info = getGameInfo(gameId);

    return (
        <button
            type="button"
            onClick={onSelect}
            className={`group flex w-full flex-col overflow-hidden rounded-xl border text-left transition duration-100 ${
                selected
                    ? "border-brand-solid ring-1 ring-brand-solid"
                    : "border-secondary bg-secondary hover:border-primary hover:bg-primary_hover"
            }`}
        >
            <div className="relative aspect-[3/4] w-full overflow-hidden bg-primary">
                {info.thumbnail ? (
                    <img
                        src={info.thumbnail}
                        alt={info.name}
                        className="size-full object-cover transition duration-200 group-hover:scale-[1.02]"
                    />
                ) : (
                    <div className="flex size-full flex-col items-center justify-center gap-2 bg-secondary px-4 text-center">
                        <img src={TILTPROOF_ICON_URL} alt="" className="size-12 object-contain opacity-60" />
                        <span className="text-sm font-semibold text-secondary">{info.name}</span>
                    </div>
                )}
                {!selected && (
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/45 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                        <span className="rounded-lg bg-brand-solid px-4 py-2 text-sm font-semibold text-white shadow-sm">
                            Select game
                        </span>
                    </div>
                )}
                {selected && (
                    <div className="absolute top-2 right-2 flex size-7 items-center justify-center rounded-full bg-brand-solid text-white shadow-sm">
                        <Check className="size-4" />
                    </div>
                )}
            </div>
            <div className="flex flex-col gap-1 border-t border-secondary p-3">
                <div className="flex items-center justify-between gap-2">
                    <h3 className="truncate text-sm font-semibold text-primary">{info.name}</h3>
                    {selected && (
                        <Badge type="color" color="brand" size="sm">
                            Selected
                        </Badge>
                    )}
                </div>
                <p className="line-clamp-2 text-xs text-tertiary">{info.tagline}</p>
            </div>
        </button>
    );
});

export const GamesTab = memo(function GamesTab() {
    const actions = useEngineActions();
    const { goToCoach } = useCoachNav();
    const gameId = useEngineSelector((s) => s.gameId);
    const engineGames = useEngineSelector((s) => s.games);
    const games = useMemo(() => [...engineGames].sort(), [engineGames]);

    const selectGame = (id: string) => {
        actions.setGame(id);
        goToCoach();
    };

    return (
        <div className="mx-auto flex w-full max-w-5xl min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
            <div>
                <h2 className="text-md font-semibold text-primary">Games</h2>
                <p className="mt-1 text-sm text-tertiary">Pick the game you're playing — you'll return to Coach to continue setup.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {games.map((id) => (
                    <GameCard
                        key={id}
                        gameId={id}
                        selected={gameId === id}
                        onSelect={() => selectGame(id)}
                    />
                ))}
            </div>
        </div>
    );
});
