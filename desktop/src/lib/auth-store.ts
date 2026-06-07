import type { MeResponse, Session } from "@/types/aicoach";

export interface AuthSnapshot {
    ready: boolean;
    available: boolean;
    session: Session | null;
    me: MeResponse | null;
    busy: boolean;
    error: string | null;
}

export const INITIAL_AUTH_SNAPSHOT: AuthSnapshot = {
    ready: false,
    available: false,
    session: null,
    me: null,
    busy: false,
    error: null,
};

type Listener = () => void;

export class AuthStore {
    private _state: AuthSnapshot = INITIAL_AUTH_SNAPSHOT;
    private _listeners = new Set<Listener>();

    readonly subscribe = (listener: Listener): (() => void) => {
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    };

    getState = (): AuthSnapshot => this._state;

    private emit(): void {
        for (const listener of this._listeners) listener();
    }

    private replace(next: AuthSnapshot): void {
        this._state = next;
        this.emit();
    }

    patch(mutator: (prev: AuthSnapshot) => AuthSnapshot | null): void {
        const next = mutator(this._state);
        if (next !== null && next !== this._state) {
            this.replace(next);
        }
    }

    setAvailable(available: boolean): void {
        this.patch((prev) => (prev.available === available ? null : { ...prev, available }));
    }

    setReady(ready: boolean): void {
        this.patch((prev) => (prev.ready === ready ? null : { ...prev, ready }));
    }

    setSession(session: Session | null): void {
        this.patch((prev) => (prev.session === session ? null : { ...prev, session }));
    }

    setMe(me: MeResponse | null): void {
        this.patch((prev) => {
            if (prev.me === me) return null;
            if (prev.me && me && prev.me.used_usd === me.used_usd && prev.me.quota_usd === me.quota_usd) {
                return null;
            }
            return { ...prev, me };
        });
    }

    setBusy(busy: boolean): void {
        this.patch((prev) => (prev.busy === busy ? null : { ...prev, busy }));
    }

    setError(error: string | null): void {
        this.patch((prev) => (prev.error === error ? null : { ...prev, error }));
    }
}
