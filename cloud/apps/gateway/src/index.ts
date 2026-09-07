import { readCookie, verifySession } from "../../../shared/session.ts";
import {
  findContainer,
  html,
  homePage,
  notFoundPage,
  parseContainers,
  windowPage,
  type Container,
} from "./ui.ts";

export interface Env {
  SESSION_SECRET?: string;
  LOGIN_URL: string;
  COOKIE_NAME: string;
  COOKIE_DOMAIN: string;
  /** JSON array of {id, machine, tenant, label, url} — empty unless explicitly configured. */
  CONTAINERS?: string;
  ASSETS: { fetch(request: Request): Promise<Response> };
}

async function requireSession(
  req: Request,
  env: Env,
): Promise<Response | { sub: string; email?: string; name?: string }> {
  if (!env.SESSION_SECRET || env.SESSION_SECRET.length < 16) {
    return html("<!doctype html><title>Unavailable</title><p>Browser sign-in is unavailable. Please try again later.</p>", 503);
  }

  const raw = readCookie(req, env.COOKIE_NAME || "prims_session");
  const session = await verifySession(raw, env.SESSION_SECRET);
  if (!session) {
    return Response.redirect(env.LOGIN_URL, 302);
  }
  return { sub: session.sub, email: session.email, name: session.name };
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

    if (path === "/logout" && req.method === "POST") {
      const headers = new Headers({ Location: env.LOGIN_URL });
      headers.append(
        "Set-Cookie",
        `${env.COOKIE_NAME}=; Path=/; ${env.COOKIE_DOMAIN ? `Domain=${env.COOKIE_DOMAIN}; ` : ""}HttpOnly; Secure; SameSite=Lax; Max-Age=0`,
      );
      return new Response(null, { status: 302, headers });
    }

    const auth = await requireSession(req, env);
    if (auth instanceof Response) return auth;

    const containers: Container[] = parseContainers(env.CONTAINERS);

    // /w/<machine>/<tenant> (or /w/<machine>/<container-id>) — deep link that
    // hops to the container's machine host and opens the headed window there.
    const wMatch = path.match(/^\/w\/([^/]+)\/([^/]+)\/?$/);
    if (wMatch && req.method === "GET") {
      let machine: string, tenant: string;
      try { machine = decodeURIComponent(wMatch[1]); tenant = decodeURIComponent(wMatch[2]); }
      catch { return new Response("Invalid path", { status: 400 }); }
      const c = findContainer(containers, machine, tenant);
      if (!c) return html(notFoundPage(`${machine}/${tenant}`), 404);
      return html(windowPage(c, auth.email || auth.sub));
    }

    if (path === "/" && req.method === "GET") {
      return html(homePage(containers, auth.email || auth.sub));
    }

    if (path === "/containers" && req.method === "GET") {
      return new Response(JSON.stringify({ containers }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ error: "not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
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
