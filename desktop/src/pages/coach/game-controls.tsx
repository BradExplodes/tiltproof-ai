import { memo, useMemo } from "react";
import { Play } from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import { Select } from "@/components/base/select/select";
import { useAuthSelector } from "@/lib/auth";
import { useEngineActions, useEngineSelector } from "@/lib/engine";
import { prettyGame, usageFromMe } from "@/pages/coach/shared";

export const GameControls = memo(function GameControls() {
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
