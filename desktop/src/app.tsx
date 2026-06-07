import type { ReactNode } from "react";
import { UpdateBanner } from "@/components/update-banner";
import { AuthProvider, useAuth } from "@/lib/auth";
import { EngineProvider } from "@/lib/engine";
import { useUpdater } from "@/lib/updater";
import { CoachScreen } from "@/pages/coach-screen";
import { LoginScreen } from "@/pages/login-screen";

const AppRoutes = () => {
    const auth = useAuth();
    const updater = useUpdater();

    if (!auth.available) {
        return (
            <div className="flex h-dvh flex-col items-center justify-center gap-2 bg-primary px-6 text-center">
                <h1 className="text-display-xs font-semibold text-primary">Open the desktop app</h1>
                <p className="max-w-md text-md text-tertiary">
                    This UI runs inside the Tiltproof AI desktop shell. Launch it with{" "}
                    <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-sm">npm run dev</code> from{" "}
                    <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-sm">desktop/</code>.
                </p>
            </div>
        );
    }

    if (!auth.ready) {
        return (
            <div className="flex h-dvh items-center justify-center bg-primary">
                <span className="text-md text-tertiary">Loading…</span>
            </div>
        );
    }

    const shell = (content: ReactNode) => (
        <div className="flex h-dvh flex-col">
            <UpdateBanner updater={updater} />
            <div className="min-h-0 flex-1">{content}</div>
        </div>
    );

    if (!auth.session) return shell(<LoginScreen auth={auth} />);

    return shell(
        <EngineProvider>
            <CoachScreen />
        </EngineProvider>,
    );
};

export const App = () => (
    <AuthProvider>
        <AppRoutes />
    </AuthProvider>
);
