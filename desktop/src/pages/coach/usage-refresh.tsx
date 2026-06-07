import { memo, useEffect } from "react";
import { useAuthActions } from "@/lib/auth";
import { useEngineSelector } from "@/lib/engine";

export const UsageRefresh = memo(function UsageRefresh() {
    const cycleCount = useEngineSelector((s) => s.cost?.call_count ?? 0);
    const { refreshMe } = useAuthActions();
    useEffect(() => {
        void refreshMe();
    }, [cycleCount, refreshMe]);
    return null;
});
