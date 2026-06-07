import { memo } from "react";
import { Settings01, Microphone01, User01, Grid01 } from "@untitledui/icons";
import { Tabs } from "@/components/application/tabs/tabs";
import { CoachNavProvider, useCoachNav, type AppTab } from "@/pages/coach/coach-nav";
import { CoachFeedSidebar } from "@/pages/coach/coach-feed-sidebar";
import { CoachHeader } from "@/pages/coach/coach-header";
import { CoachTab } from "@/pages/coach/coach-tab";
import { GamesTab } from "@/pages/coach/games-tab";
import { SettingsTab } from "@/pages/coach/settings-tab";
import { UsageRefresh } from "@/pages/coach/usage-refresh";
import { VoicesTab } from "@/pages/coach/voices-tab";

const TAB_ITEMS: { id: AppTab; label: string; icon: typeof Microphone01 }[] = [
    { id: "coach", label: "Coach", icon: Microphone01 },
    { id: "games", label: "Games", icon: Grid01 },
    { id: "voices", label: "Voice", icon: User01 },
    { id: "settings", label: "Settings", icon: Settings01 },
];

const CoachScreenContent = memo(function CoachScreenContent() {
    const { tab, setTab } = useCoachNav();

    return (
        <div className="flex h-dvh flex-col bg-primary pt-4 text-primary">
            <UsageRefresh />
            <CoachHeader />
            <div className="flex min-h-0 flex-1 overflow-hidden">
                <Tabs
                    selectedKey={tab}
                    onSelectionChange={(key) => setTab(key as AppTab)}
                    className="flex min-h-0 min-w-0 flex-1 flex-col"
                >
                    <div className="flex min-h-0 min-w-0 flex-1">
                        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                            <div className="shrink-0 border-b border-secondary px-6 pt-3">
                                <Tabs.List type="underline" size="sm" className="max-w-4xl">
                                    {TAB_ITEMS.map((item) => (
                                        <Tabs.Item key={item.id} id={item.id} icon={item.icon}>
                                            {item.label}
                                        </Tabs.Item>
                                    ))}
                                </Tabs.List>
                            </div>
                            <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-6">
                                <Tabs.Panel id="coach" className="flex min-h-0 flex-1 flex-col outline-none">
                                    <CoachTab />
                                </Tabs.Panel>
                                <Tabs.Panel id="games" className="flex min-h-0 flex-1 flex-col outline-none">
                                    <GamesTab />
                                </Tabs.Panel>
                                <Tabs.Panel id="voices" className="flex min-h-0 flex-1 flex-col outline-none">
                                    <VoicesTab />
                                </Tabs.Panel>
                                <Tabs.Panel id="settings" className="flex min-h-0 flex-1 flex-col outline-none">
                                    <SettingsTab />
                                </Tabs.Panel>
                            </div>
                        </div>
                    </div>
                </Tabs>
                <CoachFeedSidebar />
            </div>
        </div>
    );
});

/** Layout shell — tab state in CoachNavProvider; engine/auth subscriptions live in leaf panels. */
export const CoachScreen = memo(function CoachScreen() {
    return (
        <CoachNavProvider>
            <CoachScreenContent />
        </CoachNavProvider>
    );
});
