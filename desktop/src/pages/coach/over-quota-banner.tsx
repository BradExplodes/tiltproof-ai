import { memo } from "react";
import { useAuthSelector } from "@/lib/auth";
import { usageFromMe } from "@/pages/coach/shared";

export const OverQuotaBanner = memo(function OverQuotaBanner() {
    const me = useAuthSelector((s) => s.me);
    const { overQuota } = usageFromMe(me);
    if (!overQuota) return null;
    return (
        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
            You've reached this month's usage limit. It resets at the start of next month.
        </section>
    );
});
