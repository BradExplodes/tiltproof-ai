import { memo, useCallback, useEffect, useState } from "react";
import { BookOpen01, RefreshCw01, Trash01, XClose } from "@untitledui/icons";
import { Dialog, DialogTrigger, Modal, ModalOverlay } from "@/components/application/modals/modal";
import { Button } from "@/components/base/buttons/button";
import { clearMemory, fetchMemory } from "@/lib/engine-api";
import type { MemoryEntry } from "@/lib/engine-types";
import { prettyGame } from "@/pages/coach/shared";

export const MemoryButton = memo(function MemoryButton() {
    const [open, setOpen] = useState(false);
    const [entries, setEntries] = useState<MemoryEntry[] | null>(null);
    const [loading, setLoading] = useState(false);
    const [clearing, setClearing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setEntries(await fetchMemory());
        } catch (e) {
            setError(e instanceof Error ? e.message : "Failed to load memory");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (open) void load();
    }, [open, load]);

    const handleClear = useCallback(async () => {
        setClearing(true);
        setError(null);
        try {
            await clearMemory();
            setEntries([]);
        } catch (e) {
            setError(e instanceof Error ? e.message : "Failed to clear memory");
        } finally {
            setClearing(false);
        }
    }, []);

    const isEmpty = !loading && !error && entries !== null && entries.length === 0;

    return (
        <DialogTrigger isOpen={open} onOpenChange={setOpen}>
            <Button color="secondary" size="sm" iconLeading={BookOpen01}>
                View coach memory
            </Button>
            <ModalOverlay>
                <Modal className="max-w-lg">
                    <Dialog>
                        {({ close }) => (
                            <div className="flex max-h-[70vh] w-full flex-col overflow-hidden rounded-2xl border border-secondary bg-primary shadow-xl">
                                <div className="flex items-start justify-between gap-3 border-b border-secondary p-4">
                                    <div>
                                        <h2 className="text-md font-semibold text-primary">Coach long-term memory</h2>
                                        <p className="mt-0.5 text-xs text-tertiary">
                                            Durable facts the AI has chosen to remember about you across sessions.
                                        </p>
                                    </div>
                                    <Button color="tertiary" size="sm" iconLeading={XClose} aria-label="Close" onClick={close} />
                                </div>

                                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                                    {loading && <p className="text-sm text-tertiary">Loading…</p>}
                                    {error && <p className="text-sm text-error-primary">{error}</p>}
                                    {isEmpty && (
                                        <p className="text-sm text-tertiary">
                                            Nothing remembered yet. As you play, the coach notes durable facts (your style,
                                            recurring mistakes, goals) here.
                                        </p>
                                    )}
                                    {!loading && !error && entries && entries.length > 0 && (
                                        <ul className="flex flex-col gap-2">
                                            {entries
                                                .slice()
                                                .reverse()
                                                .map((entry, i) => (
                                                    <li
                                                        key={`${entry.ts}-${i}`}
                                                        className="rounded-lg border border-secondary bg-secondary p-3 text-sm text-primary"
                                                    >
                                                        {entry.text}
                                                        {entry.game_id && (
                                                            <span className="mt-1 block text-xs text-tertiary">{prettyGame(entry.game_id)}</span>
                                                        )}
                                                    </li>
                                                ))}
                                        </ul>
                                    )}
                                </div>

                                <div className="flex items-center justify-between gap-2 border-t border-secondary p-4">
                                    <Button color="tertiary" size="sm" iconLeading={RefreshCw01} isLoading={loading} onClick={() => void load()}>
                                        Refresh
                                    </Button>
                                    <Button
                                        color="primary-destructive"
                                        size="sm"
                                        iconLeading={Trash01}
                                        isLoading={clearing}
                                        isDisabled={!entries || entries.length === 0}
                                        onClick={() => void handleClear()}
                                    >
                                        Clear all
                                    </Button>
                                </div>
                            </div>
                        )}
                    </Dialog>
                </Modal>
            </ModalOverlay>
        </DialogTrigger>
    );
});
