import { memo, useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ChevronLeft, MessageChatSquare } from "@untitledui/icons";
import { CoachFeed } from "@/pages/coach/coach-feed";

const STORAGE_WIDTH = "coach-feed-width";
const STORAGE_MINIMIZED = "coach-feed-minimized";
const DEFAULT_WIDTH = 380;
const MIN_WIDTH = 260;
const MAX_WIDTH = 560;
const MINIMIZED_WIDTH = 44;

const readWidth = (): number => {
    if (typeof window === "undefined") return DEFAULT_WIDTH;
    const raw = localStorage.getItem(STORAGE_WIDTH);
    const n = raw ? Number(raw) : DEFAULT_WIDTH;
    return Number.isFinite(n) ? Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, n)) : DEFAULT_WIDTH;
};

const readMinimized = (): boolean => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(STORAGE_MINIMIZED) === "1";
};

export const CoachFeedSidebar = memo(function CoachFeedSidebar() {
    const [width, setWidth] = useState(readWidth);
    const [minimized, setMinimized] = useState(readMinimized);
    const dragging = useRef(false);
    const startX = useRef(0);
    const startWidth = useRef(DEFAULT_WIDTH);

    useEffect(() => {
        localStorage.setItem(STORAGE_WIDTH, String(width));
    }, [width]);

    useEffect(() => {
        localStorage.setItem(STORAGE_MINIMIZED, minimized ? "1" : "0");
    }, [minimized]);

    const onResizeMove = useCallback((e: MouseEvent) => {
        if (!dragging.current) return;
        const delta = startX.current - e.clientX;
        const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta));
        setWidth(next);
    }, []);

    const onResizeEnd = useCallback(() => {
        dragging.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("mousemove", onResizeMove);
        window.removeEventListener("mouseup", onResizeEnd);
    }, [onResizeMove]);

    const onResizeStart = useCallback(
        (e: ReactMouseEvent) => {
            e.preventDefault();
            dragging.current = true;
            startX.current = e.clientX;
            startWidth.current = width;
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
            window.addEventListener("mousemove", onResizeMove);
            window.addEventListener("mouseup", onResizeEnd);
        },
        [width, onResizeMove, onResizeEnd],
    );

    useEffect(() => () => onResizeEnd(), [onResizeEnd]);

    if (minimized) {
        return (
            <aside
                style={{ width: MINIMIZED_WIDTH }}
                className="flex shrink-0 flex-col items-center border-l border-secondary bg-secondary py-3"
            >
                <button
                    type="button"
                    title="Expand coach feed"
                    onClick={() => setMinimized(false)}
                    className="flex size-8 items-center justify-center rounded-md text-tertiary hover:bg-primary_hover hover:text-secondary"
                >
                    <ChevronLeft className="size-4" />
                </button>
                <MessageChatSquare className="mt-3 size-4 text-tertiary" />
                <span
                    className="mt-2 text-[10px] font-medium tracking-wide text-tertiary uppercase"
                    style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
                >
                    Feed
                </span>
            </aside>
        );
    }

    return (
        <aside style={{ width }} className="relative flex shrink-0 min-h-0">
            <div
                role="separator"
                aria-orientation="vertical"
                title="Drag to resize"
                onMouseDown={onResizeStart}
                className="absolute top-0 bottom-0 left-0 z-10 w-1.5 cursor-col-resize hover:bg-brand-solid/30 active:bg-brand-solid/50"
            />
            <div className="flex min-h-0 min-w-0 flex-1 flex-col pl-1.5">
                <CoachFeed onMinimize={() => setMinimized(true)} />
            </div>
        </aside>
    );
});
