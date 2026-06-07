import { memo } from "react";
import { OverQuotaBanner } from "@/pages/coach/over-quota-banner";
import { CoachFeed } from "@/pages/coach/coach-feed";
import { EngineErrorBanner } from "@/pages/coach/engine-error-banner";
import { GameControls } from "@/pages/coach/game-controls";

export const CoachTab = memo(function CoachTab() {
    return (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
            <main className="flex min-h-0 flex-col gap-5 overflow-y-auto">
                <GameControls />
                <OverQuotaBanner />
                <EngineErrorBanner />
            </main>
            <CoachFeed />
        </div>
    );
});
