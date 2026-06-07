import { memo, useEffect, useRef } from "react";
import { ChevronUp } from "@untitledui/icons";
import { Badge } from "@/components/base/badges/badges";
import { useEngineSelector } from "@/lib/engine";
import type { FeedItem } from "@/lib/engine-types";
import { ACTIVITY } from "@/pages/coach/shared";

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

export const CoachFeed = memo(function CoachFeed({ onMinimize }: { onMinimize?: () => void }) {
    const shellClass =
        "flex min-h-0 flex-1 flex-col rounded-l-xl rounded-r-none border border-r-0 border-secondary bg-secondary";

    return (
        <aside className={shellClass}>
            <div className="flex items-center justify-between border-b border-secondary px-4 py-3">
                <h2 className="text-sm font-semibold text-secondary">Coach feed</h2>
                <div className="flex items-center gap-2">
                    <FeedActivityLabel />
                    {onMinimize && (
                        <button
                            type="button"
                            title="Minimize feed"
                            onClick={onMinimize}
                            className="flex size-7 items-center justify-center rounded-md text-tertiary hover:bg-primary_hover hover:text-secondary"
                        >
                            <ChevronUp className="size-4" />
                        </button>
                    )}
                </div>
            </div>
            <FeedMessages />
        </aside>
    );
});
