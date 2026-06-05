import { Button } from "@/components/base/buttons/button";
import type { AuthApi } from "@/lib/auth";

const GoogleMark = (props: { className?: string }) => (
    <svg viewBox="0 0 18 18" className={props.className} aria-hidden="true">
        <path
            fill="#4285F4"
            d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
        />
        <path
            fill="#34A853"
            d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.34A9 9 0 0 0 9 18z"
        />
        <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.94H.96a9 9 0 0 0 0 8.12l3.01-2.34z" />
        <path
            fill="#EA4335"
            d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.94l3.01 2.34C4.68 5.16 6.66 3.58 9 3.58z"
        />
    </svg>
);

export const LoginScreen = ({ auth }: { auth: AuthApi }) => {
    return (
        <div className="flex h-dvh flex-col items-center justify-center bg-primary px-6 text-center text-primary">
            <div className="flex w-full max-w-sm flex-col items-center gap-6 rounded-2xl border border-secondary bg-secondary p-8">
                <div className="flex flex-col items-center gap-2">
                    <h1 className="text-display-xs font-semibold text-primary">AI Coach</h1>
                    <p className="text-md text-tertiary">Sign in to start your coaching session.</p>
                </div>

                <Button
                    color="secondary"
                    size="lg"
                    className="w-full"
                    isLoading={auth.busy}
                    iconLeading={GoogleMark}
                    onClick={() => void auth.login()}
                >
                    Sign in with Google
                </Button>

                {auth.error && <p className="text-sm text-error-primary">{auth.error}</p>}

                <p className="text-xs text-tertiary">
                    Access is invite-only right now. If your account isn't approved, ask the operator to add your email.
                </p>
            </div>
        </div>
    );
};
