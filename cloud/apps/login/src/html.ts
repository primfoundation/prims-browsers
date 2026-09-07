export function landingHtml(opts: { error?: string; configured: boolean }): string {
  const err = opts.error
    ? `<p class="err" role="alert">${escapeHtml(opts.error)}</p>`
    : "";
  const btn = opts.configured
    ? `<a class="apple-btn" href="/auth/apple">Sign in with Apple</a>`
    : `<button class="apple-btn" type="button" disabled>Sign in with Apple</button>
       <p class="hint">Sign in with Apple isn’t available yet. Try again soon.</p>`;
  return `<!doctype html>
<html lang="en" data-palette="paper">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prims · Sign in</title>
<link rel="icon" href="/assets/logos/folio.svg" type="image/svg+xml">
<link rel="stylesheet" href="/kit.css">
<style>
  main { min-height: 100vh; display: grid; place-items: center; padding: 2rem 1.25rem; }
  .card { width: min(24rem, 100%); background: var(--raised); border: 1px solid var(--line); border-radius: var(--radius); padding: 2rem 1.5rem; }
  .mark { display:flex; align-items:center; gap:0.75rem; margin-bottom: 1.25rem; }
  .mark img { width: 36px; height: 36px; }
  h1 { margin: 0; font-size: 1.35rem; font-weight: 650; letter-spacing: -0.02em; }
  .lede { margin: 0.75rem 0 1.5rem; color: var(--ink-soft); font-size: 0.95rem; line-height: 1.45; }
  .apple-btn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 100%; padding: 0.7rem 1rem;
    background: var(--ink); color: var(--raised); text-decoration: none;
    border: 1px solid var(--ink); border-radius: var(--radius);
    font: 500 0.95rem var(--sans); cursor: pointer;
  }
  .apple-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .apple-btn:not(:disabled):hover { opacity: 0.85; }
  .hint { margin: 1rem 0 0; font-size: 0.9rem; color: var(--ink-soft); line-height: 1.4; }
  .err { margin: 0 0 1rem; padding: 0.6rem 0.75rem; background: var(--surface); border: 1px solid var(--line); color: var(--ink); font-size: 0.85rem; }
  .meta { margin-top: 1.5rem; font-size: 0.75rem; color: var(--subtle); }
</style>
<main>
  <div class="card">
    <div class="mark">
      <img src="/assets/logos/folio.svg" alt="">
      <h1>Prims Browsers</h1>
    </div>
    <p class="lede">Sign in to open your browser containers.</p>
    ${err}
    ${btn}
    <p class="meta">Apple only · no passwords</p>
  </div>
</main>
</html>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function json(data: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

export function html(body: string, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", ...headers },
  });
}
