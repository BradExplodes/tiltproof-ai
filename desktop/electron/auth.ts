import { createServer } from "node:http";
import fs from "node:fs";
import path from "node:path";
import { AddressInfo } from "node:net";
import { app, safeStorage, shell } from "electron";

/** Backend base URL. Override for local dev with AICOACH_BACKEND_URL=http://localhost:8787 */
export const BACKEND_BASE = (process.env.AICOACH_BACKEND_URL ?? "https://api.tiltproof.net").replace(/\/$/, "");

export interface Session {
    token: string;
    email: string;
}

const LOGIN_TIMEOUT_MS = 5 * 60 * 1000;

function sessionFile(): string {
    return path.join(app.getPath("userData"), "session.bin");
}

let cached: Session | null | undefined;

/** Load the persisted session (decrypting if the OS keychain is available). */
export function loadSession(): Session | null {
    if (cached !== undefined) return cached;
    try {
        const raw = fs.readFileSync(sessionFile());
        const json = safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(raw) : raw.toString("utf8");
        cached = JSON.parse(json) as Session;
    } catch {
        cached = null;
    }
    return cached;
}

function persist(session: Session | null): void {
    cached = session;
    try {
        if (!session) {
            fs.rmSync(sessionFile(), { force: true });
            return;
        }
        const json = JSON.stringify(session);
        const data = safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(json) : Buffer.from(json, "utf8");
        fs.writeFileSync(sessionFile(), data);
    } catch (err) {
        console.error("[auth] failed to persist session:", err);
    }
}

/**
 * Run the loopback OAuth dance: spin up a one-shot 127.0.0.1 server, send the
 * user to the backend (which bounces to Google), and capture the session token
 * the backend redirects back with.
 */
export function login(): Promise<Session> {
    return new Promise<Session>((resolve, reject) => {
        const server = createServer((req, res) => {
            const url = new URL(req.url ?? "/", "http://127.0.0.1");
            if (url.pathname !== "/callback") {
                res.writeHead(404).end();
                return;
            }
            const token = url.searchParams.get("token");
            const email = url.searchParams.get("email") ?? "";
            res.writeHead(token ? 200 : 400, { "content-type": "text/html" });
            res.end(resultPage(Boolean(token)));
            cleanup();
            if (token) {
                const session: Session = { token, email };
                persist(session);
                resolve(session);
            } else {
                reject(new Error("No token returned from backend."));
            }
        });

        const timer = setTimeout(() => {
            cleanup();
            reject(new Error("Login timed out."));
        }, LOGIN_TIMEOUT_MS);

        function cleanup(): void {
            clearTimeout(timer);
            server.close();
        }

        server.on("error", (err) => {
            cleanup();
            reject(err);
        });

        server.listen(0, "127.0.0.1", () => {
            const port = (server.address() as AddressInfo).port;
            void shell.openExternal(`${BACKEND_BASE}/auth/start?port=${port}`);
        });
    });
}

/** Revoke the session server-side (best-effort) and clear it locally. */
export async function logout(): Promise<void> {
    const session = loadSession();
    if (session) {
        try {
            await fetch(`${BACKEND_BASE}/auth/logout`, {
                method: "POST",
                headers: { authorization: `Bearer ${session.token}` },
            });
        } catch {
            /* offline logout still clears local token */
        }
    }
    persist(null);
}

export interface MeResponse {
    email: string;
    name: string;
    period: string;
    used_usd: number;
    quota_usd: number;
}

/** Fetch current account + usage; null means the session is invalid/expired. */
export async function fetchMe(): Promise<MeResponse | null> {
    const session = loadSession();
    if (!session) return null;
    try {
        const res = await fetch(`${BACKEND_BASE}/me`, { headers: { authorization: `Bearer ${session.token}` } });
        if (res.status === 401) {
            persist(null);
            return null;
        }
        if (!res.ok) return null;
        return (await res.json()) as MeResponse;
    } catch {
        return null;
    }
}

function resultPage(ok: boolean): string {
    const msg = ok
        ? "You're signed in. You can close this tab and return to Tiltproof AI."
        : "Sign-in failed. Please return to Tiltproof AI and try again.";
    return `<!doctype html><html><head><meta charset="utf-8"><title>Tiltproof AI</title>
<style>body{font-family:system-ui,sans-serif;background:#0c0e12;color:#e5e7eb;display:flex;height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}div{max-width:30rem;padding:2rem}h1{font-size:1.25rem}</style>
</head><body><div><h1>${ok ? "Signed in" : "Sign-in failed"}</h1><p>${msg}</p></div></body></html>`;
}
