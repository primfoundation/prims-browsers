/** Container registry rendering. A "container" is a headed Prim Chromium jar
 *  that lives on a machine and is served at its own gateway URL
 *  (e.g. browser.example.test), Authentik-gated like the
 *  paseo-<cell> hosts. Logging in here shows the fleet; the gate at open is
 *  the container's Authentik group (that is what "linked" means). */

export type Container = {
  id: string; // service id, e.g. "browser-example"
  machine: string; // machine id, e.g. "e1" (hostkey)
  tenant: string; // tenant/cell, e.g. "example"
  label: string; // human label, e.g. "Example"
  url: string; // gateway URL (https://browser.example.test/)
};

// Deployments provide their own fleet; invalid configuration exposes no containers.
export const DEFAULT_CONTAINERS: Container[] = [];
export function parseContainers(raw: string | undefined): Container[] {
  if (!raw || raw.length > 65536) return [];
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data) || data.length > 100) return [];
    const identities = new Set<string>();
    for (const c of data) {
      if (!c || ["id", "machine", "tenant", "label", "url"].some((key) =>
          typeof c[key] !== "string" || !c[key] || c[key].length > 2048)) return [];
      const target = new URL(c.url);
      if (target.protocol !== "https:" || target.username || target.password) return [];
      for (const slug of new Set([c.id, c.tenant])) {
        const identity = `${c.machine.toLowerCase()}/${slug.toLowerCase()}`;
        if (identities.has(identity)) return [];
        identities.add(identity);
      }
    }
    return data as Container[];
  } catch { return []; }
}

/** Look up by /w/<machine>/<tenant> or /w/<machine>/<id>. */
export function findContainer(
  containers: Container[],
  machine: string,
  slug: string,
): Container | null {
  const m = machine.toLowerCase();
  const s = slug.toLowerCase();
  return (
    containers.find(
      (c) =>
        c.machine.toLowerCase() === m &&
        (c.tenant.toLowerCase() === s || c.id.toLowerCase() === s),
    ) || null
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

const shell = (title: string, body: string) => `<!doctype html>
<html lang="en" data-palette="paper">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<link rel="icon" href="/assets/logos/folio.svg" type="image/svg+xml">
<link rel="stylesheet" href="/kit.css">
<style>
  body { min-height: 100vh; }
  header.app {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.85rem 1.25rem; border-bottom: 1px solid var(--line);
  }
  header.app .brand { display: flex; align-items: center; gap: 0.6rem; font-weight: 650; letter-spacing: -0.02em; }
  header.app img { width: 28px; height: 28px; }
  header.app nav { display: flex; gap: 0.75rem; align-items: center; font-size: 0.85rem; color: var(--ink-soft); font-family: var(--mono); }
  header.app a { color: var(--ink); text-decoration: none; }
  header.app a:hover { text-decoration: underline; }
  main { max-width: 44rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
  h1 { font-size: 1.5rem; font-weight: 650; letter-spacing: -0.02em; margin: 0 0 0.35rem; }
  .lede { color: var(--ink-soft); margin: 0 0 1.75rem; line-height: 1.45; }
  .cards { list-style: none; padding: 0; margin: 0 0 1.5rem; display: grid; gap: 0.75rem; }
  .card {
    display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    padding: 1rem 1.1rem; background: var(--raised); border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .card .who { display: grid; gap: 0.2rem; min-width: 0; }
  .card .who .name { font-weight: 600; letter-spacing: -0.01em; }
  .card .who .meta { font-family: var(--mono); font-size: 0.75rem; color: var(--ink-soft); }
  .card a.open {
    flex: 0 0 auto; background: var(--ink); color: var(--bg); text-decoration: none;
    border-radius: var(--radius); padding: 0.55rem 0.9rem; font: 500 0.9rem var(--sans);
  }
  .card a.open:hover { opacity: 0.9; }
  .empty { color: var(--ink-soft); font-size: 0.9rem; margin: 0 0 1.25rem; }
  .note {
    margin-top: 2rem; padding: 0.75rem 0.9rem; border: 1px dashed var(--line);
    font-size: 0.8rem; color: var(--ink-soft); font-family: var(--mono); line-height: 1.4;
  }
  .window-card { padding: 1.5rem; background: var(--raised); border: 1px solid var(--line); border-radius: var(--radius); }
  .window-card h2 { margin: 0 0 0.5rem; font-size: 1.15rem; }
  .window-card p { margin: 0.35rem 0; color: var(--ink-soft); }
  .window-card .go { display: block; margin-top: 1.25rem; text-align: center;
    background: var(--ink); color: var(--bg); text-decoration: none; border-radius: var(--radius);
    padding: 0.7rem 1rem; font: 500 1rem var(--sans); }
  .window-card .go:hover { opacity: 0.9; }
  .window-card .back { display: inline-block; margin-top: 1.1rem; font-size: 0.85rem; }
</style>
<header class="app">
  <div class="brand"><img src="/assets/logos/folio.svg" alt="">Prims Browsers</div>
  <nav>
    <a href="/">Browsers</a>
    <form method="post" action="/logout" style="margin:0"><button type="submit" style="font:inherit;background:none;border:none;color:var(--ink);cursor:pointer;padding:0;font-family:var(--mono);font-size:0.85rem">Log out</button></form>
  </nav>
</header>
<main>${body}</main>
</html>`;

export function homePage(containers: Container[], who?: string): string {
  const list =
    containers.length === 0
      ? `<p class="empty">No browser containers registered yet.</p>`
      : `<ul class="cards">${containers
          .map(
            (c) => `<li class="card">
          <div class="who">
            <span class="name">${escapeHtml(c.label)} browser</span>
            <span class="meta">${escapeHtml(c.machine)} · ${escapeHtml(
              c.tenant,
            )} · ${escapeHtml(c.id)}</span>
          </div>
          <a class="open" href="/w/${encodeURIComponent(
            c.machine,
          )}/${encodeURIComponent(c.tenant)}">Open window</a>
        </li>`,
          )
          .join("")}</ul>`;

  const whoLine = who
    ? `<p class="meta" style="margin-bottom:1rem;font-family:var(--mono);font-size:0.8rem;color:var(--ink-soft)">Signed in · ${escapeHtml(
        who,
      )}</p>`
    : "";

  return shell(
    "Prims Browsers",
    `${whoLine}
    <h1>Your browsers</h1>
    <p class="lede">Headed containers that live on your machines — like Paseo cells, but with a window you can see and drive. Open one to watch and take the mouse.</p>
    ${list}
    <p class="note">Each container opens on its own machine host (${containers
      .map((c) => escapeHtml(c.machine))
      .filter((v, i, a) => a.indexOf(v) === i)
      .join(", ")}). The first open asks for your Eidos sign-in (Authentik) — the same gate as the paseo-<i>cell</i> hosts. That gate decides who is linked to which container.</p>`,
  );
}

export function windowPage(c: Container, who?: string): string {
  const target = escapeAttr(c.url);
  return shell(
    `${c.label} browser`,
    `<div class="window-card">
      <h2>${escapeHtml(c.label)} browser</h2>
      <p>Container <strong>${escapeHtml(c.id)}</strong> on machine <strong>${escapeHtml(
        c.machine,
      )}</strong> (tenant ${escapeHtml(c.tenant)}).</p>
      <p>Opening the window on the machine host…</p>
      <meta http-equiv="refresh" content="0; url=${target}">
      <script>
        window.location.replace(${JSON.stringify(c.url)});
      </script>
      <a class="go" href="${target}">Open window</a>
      <p class="meta" style="font-family:var(--mono);font-size:0.75rem">${escapeHtml(
        c.url,
      )}</p>
      <a class="back" href="/">← All browsers</a>
    </div>`,
  );
}

export function notFoundPage(slug: string): string {
  return shell(
    "Not found",
    `<div class="window-card">
      <h2>No such browser container</h2>
      <p><strong>${escapeHtml(slug)}</strong> is not in the registry on this machine. A jar may not be stood up for that tenant yet.</p>
      <a class="back" href="/">← All browsers</a>
    </div>`,
  );
}

export function html(body: string, status = 200, headers: HeadersInit = {}): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", ...headers },
  });
}
