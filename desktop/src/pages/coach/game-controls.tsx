import { memo } from "react";
import { Play } from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import { useAuthSelector } from "@/lib/auth";
import { getGameInfo } from "@/lib/games";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import { usageFromMe } from "@/pages/coach/shared";

export const GameControls = memo(function GameControls() {
    const actions = useEngineActions();
    const gameId = useEngineSelector((s) => s.gameId);
    const running = useEngineSelector((s) => s.running);
    const me = useAuthSelector((s) => s.me);
    const { overQuota } = usageFromMe(me);
    const selected = gameId ? getGameInfo(gameId) : null;

    return (
        <section className="flex flex-wrap items-end gap-3 rounded-xl border border-secondary bg-secondary p-4">
            <div className="min-w-56 flex-1">
                <p className="mb-1 text-sm font-medium text-secondary">Game</p>
                {selected ? (
                    <div className="flex items-center gap-3">
                        {selected.thumbnail ? (
                            <img
                                src={selected.thumbnail}
                                alt=""
                                className="size-10 rounded-md object-cover"
                            />
                        ) : (
                            <img src="/tiltproof-icon.png" alt="" className="size-10 object-contain" />
                        )}
                        <div>
                            <p className="text-sm font-semibold text-primary">{selected.name}</p>
                            <p className="text-xs text-tertiary">Change game on the Games tab</p>
                        </div>
                    </div>
                ) : (
                    <p className="text-sm text-tertiary">Choose a game on the Games tab</p>
                )}
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
