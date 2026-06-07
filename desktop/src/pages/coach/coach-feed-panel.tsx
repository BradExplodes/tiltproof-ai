import { memo, useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ChevronDown } from "@untitledui/icons";
import { CoachFeed } from "@/pages/coach/coach-feed";

const STORAGE_HEIGHT = "coach-feed-height";
const STORAGE_MINIMIZED = "coach-feed-minimized";
const DEFAULT_HEIGHT = 240;
const MIN_HEIGHT = 120;
const MAX_HEIGHT = 480;
const MINIMIZED_HEIGHT = 40;

const readHeight = (): number => {
    if (typeof window === "undefined") return DEFAULT_HEIGHT;
    const raw = localStorage.getItem(STORAGE_HEIGHT);
    const n = raw ? Number(raw) : DEFAULT_HEIGHT;
    return Number.isFinite(n) ? Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, n)) : DEFAULT_HEIGHT;
};

const readMinimized = (): boolean => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(STORAGE_MINIMIZED) === "1";
};

export const CoachFeedPanel = memo(function CoachFeedPanel() {
    const [height, setHeight] = useState(readHeight);
    const [minimized, setMinimized] = useState(readMinimized);
    const dragging = useRef(false);
    const startY = useRef(0);
    const startHeight = useRef(DEFAULT_HEIGHT);

    useEffect(() => {
        localStorage.setItem(STORAGE_HEIGHT, String(height));
    }, [height]);

    useEffect(() => {
        localStorage.setItem(STORAGE_MINIMIZED, minimized ? "1" : "0");
    }, [minimized]);

    const onResizeMove = useCallback((e: MouseEvent) => {
        if (!dragging.current) return;
        const delta = e.clientY - startY.current;
        const next = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeight.current + delta));
        setHeight(next);
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
            startY.current = e.clientY;
            startHeight.current = height;
            document.body.style.cursor = "row-resize";
            document.body.style.userSelect = "none";
            window.addEventListener("mousemove", onResizeMove);
            window.addEventListener("mouseup", onResizeEnd);
        },
        [height, onResizeMove, onResizeEnd],
    );

    useEffect(() => () => onResizeEnd(), [onResizeEnd]);

    if (minimized) {
        return (
            <div className="shrink-0 pl-6">
                <aside
                    style={{ height: MINIMIZED_HEIGHT }}
                    className="flex items-center justify-between rounded-l-xl border border-r-0 border-secondary bg-secondary px-4"
                >
                    <span className="text-sm font-semibold text-secondary">Coach feed</span>
                    <button
                        type="button"
                        title="Expand coach feed"
                        onClick={() => setMinimized(false)}
                        className="flex size-7 items-center justify-center rounded-md text-tertiary hover:bg-primary_hover hover:text-secondary"
                    >
                        <ChevronDown className="size-4" />
                    </button>
                </aside>
            </div>
        );
    }

    return (
        <div className="relative shrink-0 pl-6">
            <div style={{ height }} className="flex min-h-0 flex-col">
                <CoachFeed onMinimize={() => setMinimized(true)} />
            </div>
            <div
                role="separator"
                aria-orientation="horizontal"
                title="Drag to resize"
                onMouseDown={onResizeStart}
                className="h-1.5 cursor-row-resize hover:bg-brand-solid/30 active:bg-brand-solid/50"
            />
        </div>
    );
});
