import { memo } from "react";
import { OverQuotaBanner } from "@/pages/coach/over-quota-banner";
import { EngineErrorBanner } from "@/pages/coach/engine-error-banner";
import { GameControls } from "@/pages/coach/game-controls";

export const CoachTab = memo(function CoachTab() {
    return (
        <main className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
            <GameControls />
            <OverQuotaBanner />
            <EngineErrorBanner />
        </main>
    );
});
