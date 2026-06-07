import { memo } from "react";
import { useEngineSelector } from "@/lib/engine";

export const EngineErrorBanner = memo(function EngineErrorBanner() {
    const error = useEngineSelector((s) => s.error);
    if (!error) return null;
    return (
        <section className="rounded-xl border border-error_subtle bg-error-primary p-3 text-sm text-error-primary">
            {error}
        </section>
    );
});
