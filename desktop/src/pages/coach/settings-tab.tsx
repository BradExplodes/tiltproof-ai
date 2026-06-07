import { memo } from "react";
import { SettingsPanel } from "@/pages/coach/settings-panel";
import { UsagePanel } from "@/pages/coach/usage-panel";

export const SettingsTab = memo(function SettingsTab() {
    return (
        <div className="mx-auto flex w-full max-w-2xl min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
            <UsagePanel />
            <SettingsPanel />
        </div>
    );
});
