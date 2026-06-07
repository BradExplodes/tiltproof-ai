import { memo } from "react";
import { useAuthSelector } from "@/lib/auth";
import { usageFromMe } from "@/pages/coach/shared";

export const UsagePanel = memo(function UsagePanel() {
    const me = useAuthSelector((s) => s.me);
    const { unlimited, usagePct, overQuota } = usageFromMe(me);

    return (
        <section className="rounded-xl border border-secondary bg-secondary p-4">
            <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-secondary">Usage this month</h2>
                <span className="text-sm font-medium text-primary">
                    {unlimited ? "Unlimited" : `${Math.round(usagePct)}%`}
                </span>
            </div>
            {!unlimited && (
                <div className="h-2 w-full overflow-hidden rounded-full bg-tertiary">
                    <div
                        className={`h-full rounded-full ${overQuota ? "bg-error-solid" : "bg-brand-solid"}`}
                        style={{ width: `${usagePct}%` }}
                    />
                </div>
            )}
            <p className="mt-2 text-xs text-tertiary">
                {unlimited ? "No usage cap on your account." : "Resets at the start of each month."}
            </p>
        </section>
    );
});
