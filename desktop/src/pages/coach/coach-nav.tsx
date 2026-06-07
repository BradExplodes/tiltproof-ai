import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type AppTab = "coach" | "games" | "voices" | "settings";

interface CoachNavContextValue {
    tab: AppTab;
    setTab: (tab: AppTab) => void;
    goToCoach: () => void;
}

const CoachNavContext = createContext<CoachNavContextValue | null>(null);

export function CoachNavProvider({ children }: { children: ReactNode }) {
    const [tab, setTab] = useState<AppTab>("coach");
    const goToCoach = useCallback(() => setTab("coach"), []);

    const value = useMemo(() => ({ tab, setTab, goToCoach }), [tab, goToCoach]);

    return <CoachNavContext.Provider value={value}>{children}</CoachNavContext.Provider>;
}

export function useCoachNav(): CoachNavContextValue {
    const ctx = useContext(CoachNavContext);
    if (!ctx) throw new Error("useCoachNav must be used within CoachNavProvider");
    return ctx;
}
