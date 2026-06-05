import { useCallback, useEffect, useState } from "react";

export type UpdateState = "idle" | "checking" | "available" | "downloading" | "ready" | "error" | "none";

export interface UpdateStatus {
    state: UpdateState;
    version?: string;
    percent?: number;
    message?: string;
}

const INITIAL: UpdateStatus = { state: "idle" };

export interface UpdaterApi extends UpdateStatus {
    available: boolean;
    install: () => void;
    check: () => void;
}

export function useUpdater(): UpdaterApi {
    const [status, setStatus] = useState<UpdateStatus>(INITIAL);
    const available = typeof window !== "undefined" && Boolean(window.aicoach?.onUpdateStatus);

    useEffect(() => {
        if (!window.aicoach?.onUpdateStatus) return;
        return window.aicoach.onUpdateStatus((next) => setStatus(next));
    }, []);

    const install = useCallback(() => {
        void window.aicoach?.installUpdate?.();
    }, []);

    const check = useCallback(() => {
        void window.aicoach?.checkForUpdates?.();
    }, []);

    return { ...status, available, install, check };
}
