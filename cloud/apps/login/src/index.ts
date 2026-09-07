import {
  appleAuthorizeUrl,
  verifyAppleIdToken,
  exchangeAppleCode,
  requireAppleConfig,
} from "./apple.ts";
import { html, json, landingHtml } from "./html.ts";
import {
  readCookie,
  signSession,
  verifySession,
  type SessionPayload,
} from "../../../shared/session.ts";

export interface Env {
  APPLE_CLIENT_ID?: string;
  APPLE_TEAM_ID?: string;
  APPLE_KEY_ID?: string;
  APPLE_PRIVATE_KEY?: string;
  SESSION_SECRET?: string;
  APPLE_REDIRECT_URI: string;
  POST_LOGIN_REDIRECT: string;
  COOKIE_NAME: string;
  COOKIE_DOMAIN: string;
  ASSETS: { fetch(request: Request): Promise<Response> };
}

const STATE_COOKIE = "prims_oauth_state";
const SESSION_TTL = 60 * 60 * 24 * 14; // 14d

/** Workers require absolute URLs for Response.redirect. */
function redirect(reqUrl: URL, pathAndQuery: string, status = 302): Response {
  return Response.redirect(new URL(pathAndQuery, reqUrl.origin).toString(), status);
}

function setSessionCookie(headers: Headers, env: Env, value: string, clear = false) {
  const name = env.COOKIE_NAME || "prims_session";
  const parts = [
    `${name}=${clear ? "" : value}`,
    "Path=/",
    ...(env.COOKIE_DOMAIN ? [`Domain=${env.COOKIE_DOMAIN}`] : []),
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    clear ? "Max-Age=0" : `Max-Age=${SESSION_TTL}`,
  ];
  headers.append("Set-Cookie", parts.join("; "));
}

type AppleCallback = {
  code: string | null;
  state: string | null;
  error: string | null;
  user: string | null;
};

/** Finish the Apple round trip: state check → token exchange → session. */
async function completeAppleCallback(
  req: Request,
  url: URL,
  env: Env,
  cb: AppleCallback,
): Promise<Response> {
  const missing = requireAppleConfig(env);
  if (missing || (!env.SESSION_SECRET || env.SESSION_SECRET.length < 16)) {
    return html(
      landingHtml({
        error: "Sign in with Apple is unavailable. Please try again later.",
        configured: false,
      }),
      503,
    );
  }
  if (cb.error) {
    return redirect(url, `/?error=${encodeURIComponent(cb.error)}`);
  }
  const expected = readCookie(req, STATE_COOKIE);
  if (!cb.code || !cb.state || !expected || cb.state !== expected) {
    return redirect(
      url,
      `/?error=${encodeURIComponent("Invalid OAuth state or missing code")}`,
    );
  }

  let tokens;
  try {
    tokens = await exchangeAppleCode(env, cb.code);
  } catch {
    return redirect(url, "/?error=Sign-in%20could%20not%20be%20completed");
  }
  if (!tokens.id_token) {
    return redirect(url, "/?error=Sign-in%20could%20not%20be%20completed");
  }

  let claims;
  try { claims = await verifyAppleIdToken(env, tokens.id_token, cb.state); }
  catch { return redirect(url, "/?error=Sign-in%20could%20not%20be%20verified"); }
  const sub = typeof claims?.sub === "string" ? claims.sub : null;
  if (!sub) {
    return redirect(
      url,
      `/?error=${encodeURIComponent("Apple id_token missing sub")}`,
    );
  }

  // form_post first sign-in carries user JSON: {"name":{"firstName","lastName"},"email"}
  let name: string | undefined;
  if (cb.user) {
    try {
      const user = JSON.parse(cb.user) as {
        name?: { firstName?: string; lastName?: string };
      };
      const full = `${user?.name?.firstName ?? ""} ${user?.name?.lastName ?? ""}`.trim();
      if (full) name = full;
    } catch {
      // name is optional — ignore malformed payloads
    }
  }

  const now = Math.floor(Date.now() / 1000);
  const payload: SessionPayload = {
    sub,
    email: typeof claims?.email === "string" ? claims.email : undefined,
    ...(name ? { name } : {}),
    iat: now,
    exp: now + SESSION_TTL,
  };
  const token = await signSession(payload, env.SESSION_SECRET);
  const headers = new Headers({ Location: env.POST_LOGIN_REDIRECT });
  setSessionCookie(headers, env, token);
  headers.append(
    "Set-Cookie",
    `${STATE_COOKIE}=; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=0`,
  );
  return new Response(null, { status: 302, headers });
}

const worker = {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname;

    if (
      path === "/kit.css" ||
      path === "/folio.svg" ||
      path === "/favicon.svg" ||
      path.startsWith("/assets/")
    ) {
      return env.ASSETS.fetch(req);
    }

    if (path === "/" && req.method === "GET") {
      const err = url.searchParams.get("error") || undefined;
      const configured = !requireAppleConfig(env) && (!!env.SESSION_SECRET && env.SESSION_SECRET.length >= 16);
      return html(landingHtml({ error: err, configured }));
    }

    if (path === "/auth/apple" && req.method === "GET") {
      const missing = requireAppleConfig(env);
      if (missing || (!env.SESSION_SECRET || env.SESSION_SECRET.length < 16)) {
        // Soft user message — never leak env/secret names on the product card.
        return redirect(url, `/?error=${encodeURIComponent("Sign in with Apple isn’t available yet.")}`);
      }
      const state = crypto.randomUUID();
      const location = appleAuthorizeUrl(env, state);
      const headers = new Headers({ Location: location });
      // SameSite=None is required: Apple's form_post callback is a CROSS-SITE
      // top-level POST from appleid.apple.com — Lax cookies are not sent on
      // cross-site POSTs (Safari never; Chrome only for <2-min-old cookies).
      headers.append(
        "Set-Cookie",
        `${STATE_COOKIE}=${state}; Path=/; HttpOnly; Secure; SameSite=None; Max-Age=600`,
      );
      return new Response(null, { status: 302, headers });
    }

    // response_mode=form_post: Apple POSTs code/state/error as a form body
    // (query mode with name/email scope is rejected by Apple).
    if (path === "/auth/apple/callback" && req.method === "POST") {
      if (!req.headers.get("content-type")?.toLowerCase().startsWith("application/x-www-form-urlencoded"))
        return json({ error: "Invalid callback format" }, 415);
      const reader = req.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 32768) { await reader.cancel(); return json({ error: "Callback too large" }, 413); }
          chunks.push(value);
        }
      }
      const body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
      const form = new URLSearchParams(new TextDecoder().decode(body));
      const str = (v: unknown): string | null =>
        typeof v === "string" && v.length ? v : null;
      return completeAppleCallback(req, url, env, {
        code: str(form.get("code")),
        state: str(form.get("state")),
        error: str(form.get("error")),
        user: str(form.get("user")),
      });
    }

    // Legacy GET fallback (some Apple error redirects arrive as query params).
    if (path === "/auth/apple/callback" && req.method === "GET") {
      return completeAppleCallback(req, url, env, {
        code: url.searchParams.get("code"),
        state: url.searchParams.get("state"),
        error: url.searchParams.get("error"),
        user: null,
      });
    }

    if (path === "/me" && req.method === "GET") {
      if ((!env.SESSION_SECRET || env.SESSION_SECRET.length < 16)) {
        return json({ error: "Sign-in unavailable" }, 503);
      }
      const raw = readCookie(req, env.COOKIE_NAME || "prims_session");
      const session = await verifySession(raw, env.SESSION_SECRET);
      if (!session) return json({ error: "unauthorized" }, 401);
      return json({ ok: true, session });
    }

    if (path === "/logout" && (req.method === "POST" || req.method === "GET")) {
      if (req.method === "GET") {
        const headers = new Headers({ Location: "/" });
        setSessionCookie(headers, env, "", true);
        return new Response(null, { status: 302, headers });
      }
      const headers = new Headers({ "Content-Type": "application/json" });
      setSessionCookie(headers, env, "", true);
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    return json({ error: "not found", path }, 404);
  },
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const response = await worker.fetch(req, env);
    const path = new URL(req.url).pathname;
    if (path.startsWith("/assets/") || ["/kit.css", "/folio.svg", "/favicon.svg"].includes(path)) return response;
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "no-store");
    headers.set("Referrer-Policy", "no-referrer");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(response.body, { status: response.status, headers });
  },
};
