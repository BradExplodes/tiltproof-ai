import { memo } from "react";
import { LogOut01 } from "@untitledui/icons";
import { BadgeWithDot } from "@/components/base/badges/badges";
import { Button } from "@/components/base/buttons/button";
import { useAuthActions, useAuthSelector } from "@/lib/auth";
import { TILTPROOF_LOGO_URL } from "@/lib/branding";
import { useEngineSelector } from "@/lib/engine";
import { STATE_BADGE, usageFromMe } from "@/pages/coach/shared";

const EngineStateBadge = memo(function EngineStateBadge() {
    const state = useEngineSelector((s) => s.state);
    const info = STATE_BADGE[state] ?? STATE_BADGE.idle;
    return (
        <BadgeWithDot type="pill-color" color={info.color} size="md">
            {info.label}
        </BadgeWithDot>
    );
});

const EngineConnectionBadge = memo(function EngineConnectionBadge() {
    const connected = useEngineSelector((s) => s.connected);
    return (
        <BadgeWithDot type="pill-color" color={connected ? "success" : "gray"} size="sm">
            {connected ? "Engine connected" : "Connecting…"}
        </BadgeWithDot>
    );
});

const UsageHeaderLabel = memo(function UsageHeaderLabel() {
    const me = useAuthSelector((s) => s.me);
    const { unlimited, usagePct, overQuota } = usageFromMe(me);
    if (!me) return null;
    return (
        <span className="text-sm text-tertiary">
            Usage{" "}
            <span className={overQuota ? "font-medium text-error-primary" : "font-medium text-primary"}>
                {unlimited ? "Unlimited" : `${Math.round(usagePct)}%`}
            </span>
        </span>
    );
});

const AccountControls = memo(function AccountControls() {
    const email = useAuthSelector((s) => s.session?.email ?? null);
    const busy = useAuthSelector((s) => s.busy);
    const { logout } = useAuthActions();

    return (
        <div className="flex items-center gap-2 border-l border-secondary pl-3">
            <span className="max-w-44 truncate text-sm text-secondary" title={email ?? undefined}>
                {email}
            </span>
            <Button color="tertiary" size="sm" iconLeading={LogOut01} isLoading={busy} onClick={() => void logout()}>
                Sign out
            </Button>
        </div>
    );
});

export const CoachHeader = memo(function CoachHeader() {
    return (
        <header className="flex items-center justify-between border-b border-secondary px-6 pt-2 pb-4">
            <div className="flex items-center gap-3">
                <div className="flex items-center gap-2.5">
                    <img
                        src={TILTPROOF_LOGO_URL}
                        alt=""
                        width={32}
                        height={32}
                        className="size-8 shrink-0 object-contain"
                    />
                    <span className="text-lg font-semibold text-primary">Tiltproof AI</span>
                </div>
                <EngineStateBadge />
            </div>
            <div className="flex items-center gap-3">
                <EngineConnectionBadge />
                <UsageHeaderLabel />
                <AccountControls />
            </div>
        </header>
    );
});
