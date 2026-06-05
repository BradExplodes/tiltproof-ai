import { useAuth } from "@/lib/auth";
import { CoachScreen } from "@/pages/coach-screen";
import { LoginScreen } from "@/pages/login-screen";

export const App = () => {
    const auth = useAuth();

    if (!auth.available) {
        return (
            <div className="flex h-dvh flex-col items-center justify-center gap-2 bg-primary px-6 text-center">
                <h1 className="text-display-xs font-semibold text-primary">Open the desktop app</h1>
                <p className="max-w-md text-md text-tertiary">
                    This UI runs inside the AI Coach desktop shell. Launch it with{" "}
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

    if (!auth.session) return <LoginScreen auth={auth} />;

    return <CoachScreen auth={auth} />;
};
