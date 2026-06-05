import { Download01, RefreshCw01 } from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import type { UpdaterApi } from "@/lib/updater";

export const UpdateBanner = ({ updater }: { updater: UpdaterApi }) => {
    if (!updater.available) return null;

    const { state, version, percent, message } = updater;

    if (state === "idle" || state === "none" || state === "checking") return null;

    if (state === "error") {
        return (
            <div className="flex items-center justify-between gap-3 border-b border-error_subtle bg-error-primary px-4 py-2.5 text-sm text-error-primary">
                <span>Update check failed{message ? `: ${message}` : ""}</span>
                <Button color="tertiary" size="sm" iconLeading={RefreshCw01} onClick={updater.check}>
                    Retry
                </Button>
            </div>
        );
    }

    if (state === "available" || state === "downloading") {
        const label =
            state === "downloading" && percent != null
                ? `Downloading update v${version}… ${Math.round(percent)}%`
                : `Update v${version} available. Downloading…`;
        return (
            <div className="flex items-center justify-between gap-3 border-b border-brand bg-brand-secondary px-4 py-2.5 text-sm text-brand-secondary">
                <span className="flex items-center gap-2">
                    <Download01 className="size-4 shrink-0" />
                    {label}
                </span>
            </div>
        );
    }

    if (state === "ready") {
        return (
            <div className="flex items-center justify-between gap-3 border-b border-brand bg-brand-secondary px-4 py-2.5 text-sm text-brand-secondary">
                <span>
                    <strong className="font-semibold">Update v{version} is ready.</strong> Restart to install the latest
                    version.
                </span>
                <Button color="primary" size="sm" onClick={updater.install}>
                    Install & restart
                </Button>
            </div>
        );
    }

    return null;
};
