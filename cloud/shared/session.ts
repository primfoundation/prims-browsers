/**
 * Shared Prims Browsers cloud-session contract.
 *
 * Provenance: byte-equivalent source logic existed in both
 * primfoundation/logins-prims-sh and primfoundation/browsers-prims-sh as
 * src/session.ts (Git blob 3010933e8ad30a35e58660ff0425303ed288807d).
 *
 * This consolidation does not rotate SESSION_SECRET or change cookie names,
 * domains, payload fields, algorithms, expiry semantics, or production routes.
 */

export type SessionPayload = {
  sub: string;
  email?: string;
  name?: string;
  iat: number;
  exp: number;
};

const enc = new TextEncoder();

function b64url(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): ArrayBuffer {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function signSession(
  payload: SessionPayload,
  secret: string,
): Promise<string> {
  if (!secret || secret.length < 16) {
    throw new Error("SESSION_SECRET missing or too short");
  }
  const body = b64url(enc.encode(JSON.stringify(payload)));
  const key = await hmacKey(secret);
  const sig = b64url(await crypto.subtle.sign("HMAC", key, enc.encode(body)));
  return `${body}.${sig}`;
}

export async function verifySession(
  token: string | null | undefined,
  secret: string,
): Promise<SessionPayload | null> {
  if (!token || token.length > 8192 || !secret || secret.length < 16) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 2 || parts.some((p) => !/^[A-Za-z0-9_-]+$/.test(p))) return null;
    const [body, sig] = parts;
    const key = await hmacKey(secret);
    const ok = await crypto.subtle.verify("HMAC", key, b64urlDecode(sig), enc.encode(body));
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(b64urlDecode(body)));
    const now = Math.floor(Date.now() / 1000);
    if (!payload || typeof payload !== "object" ||
        typeof payload.sub !== "string" || !payload.sub ||
        !Number.isSafeInteger(payload.iat) || !Number.isSafeInteger(payload.exp) ||
        payload.exp <= now || payload.iat > now + 60 || payload.exp <= payload.iat ||
        (payload.email !== undefined && typeof payload.email !== "string") ||
        (payload.name !== undefined && typeof payload.name !== "string")) return null;
    return payload as SessionPayload;
  } catch {
    return null;
  }
}

export function readCookie(req: Request, name: string): string | null {
  const raw = req.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=") || null;
  }
  return null;
}
