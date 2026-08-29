const rail = document.getElementById("rail");
const title = document.getElementById("title");
const meta = document.getElementById("meta");
const empty = document.getElementById("empty");
const browser = document.getElementById("browser");
const glass = document.getElementById("glass");
const watch = document.getElementById("watch");
const closeBtn = document.getElementById("close");
const sourceEl = document.getElementById("source");
const tabsEl = document.getElementById("tabs");
const urlEl = document.getElementById("url");
const backBtn = document.getElementById("back");
const fwdBtn = document.getElementById("fwd");
const handsWho = document.getElementById("hands-who");
const takeoverBtn = document.getElementById("takeover");
const continueBtn = document.getElementById("continue");
const workBtn = document.getElementById("work-btn");
const vaultBtn = document.getElementById("vault-btn");
const vaultEl = document.getElementById("vault");
const vaultTitle = document.getElementById("vault-title");
const vaultList = document.getElementById("vault-list");
const vaultForm = document.getElementById("vault-form");
const vaultEmpty = document.getElementById("vault-empty");
const MASK = "••••••••";
const autos = Object.create(null);
const askEl = document.getElementById("login-ask");
const askTitle = document.getElementById("ask-title");
const askCopy = document.getElementById("ask-copy");
const askList = document.getElementById("ask-list");
const askSave = document.getElementById("ask-save");
const askApprove = document.getElementById("ask-approve");
let pendingAsk = null;
let askChosen = "";
const queuedAsks = Object.create(null);
const omnibox = document.getElementById("omnibox");
const pageSend = document.getElementById("page-send");
const pageText = document.getElementById("page-text");
const pageSendBtn = document.getElementById("page-send-btn");
const ghostCursor = document.getElementById("ghost-cursor");
const glassWrap = document.getElementById("glass-wrap");

const HOLD_MS = 15000;
let selected = null;
let tenants = [];
let touches = Object.create(null);
let gates = Object.create(null);
let driveTimer = null;

function hasGlass(row) {
  return Boolean(row && row.glass && row.glass.vnc);
}

function glassUrl(vnc) {
  const u = new URL(vnc, window.location.href);
  u.searchParams.set("resize", "scale");
  u.searchParams.set("reconnect", "false");
  return u.toString();
}

function bindGlass(url) {
  if (glass.dataset.bound === url) return;
  glass.dataset.bound = url;
  glass.src = url;
}

function unbindGlass() {
  if (!glass.dataset.bound && (!glass.src || glass.src === "about:blank")) return;
  delete glass.dataset.bound;
  glass.src = "about:blank";
}

function pruneTouches() {
  const now = Date.now();
  for (const id of Object.keys(touches)) {
    if (now - touches[id].at >= HOLD_MS) delete touches[id];
  }
  for (const id of Object.keys(autos)) {
    if (now - autos[id].at >= HOLD_MS) delete autos[id];
  }
}

function hardWait(g) {
  return Boolean(g && g.reason !== "consent");
}

function paintDrive() {
  if (driveTimer) {
    clearTimeout(driveTimer);
    driveTimer = null;
  }
  pruneTouches();
  document.querySelectorAll(".nav-row").forEach((b) => {
    const id = b.dataset.id;
    const waiting = hardWait(gates[id]);
    const working = Boolean(touches[id]) && !waiting;
    b.classList.toggle("is-gated", waiting);
    b.classList.toggle("is-steering", working);
    const lede = b.querySelector(".nav-row__lede");
    if (lede) {
      if (waiting) lede.textContent = gates[id].label || "needs you";
      else if (autos[id] && Date.now() - autos[id].at < HOLD_MS) lede.textContent = "filling as " + autos[id].login;
      else if (working) lede.textContent = touches[id].host || "working";
      else lede.textContent = "";
    }
  });
  const gsel = selected ? gates[selected] : null;
  const waiting = Boolean(gsel && hardWait(gsel));
  const mine = selected && touches[selected] && !waiting;
  if (browser) {
    browser.classList.toggle("is-steering", Boolean(mine));
    browser.classList.toggle("is-gated", Boolean(waiting));
  }
  if (handsWho) {
    if (waiting) handsWho.textContent = "Needs you · " + ((gsel && gsel.label) || "prove you're human");
    else if (selected && autos[selected] && Date.now() - autos[selected].at < HOLD_MS)
      handsWho.textContent = "Filling as " + autos[selected].login;
    else if (mine) handsWho.textContent = "AI driving · " + (mine.verb || "steer");
    else handsWho.textContent = "You drive this glass";
  }
  if (continueBtn) continueBtn.hidden = !waiting;
  if ((!mine || waiting) && ghostCursor) ghostCursor.hidden = true;
  const waits = [
    ...Object.values(touches).map((t) => HOLD_MS - (Date.now() - t.at)),
    ...Object.values(autos).map((t) => HOLD_MS - (Date.now() - t.at)),
  ];
  if (waits.length) {
    driveTimer = setTimeout(paintDrive, Math.max(50, Math.min(...waits)));
  }
}

function setHands(steer) {
  if (!steer || !steer.id) return;
  if (steer.on === false) {
    delete touches[steer.id];
    paintDrive();
    return;
  }
  if (steer.on || steer.last_touch) {
    let at = Date.now();
    if (steer.last_touch) {
      const ts = Number(steer.last_touch) * 1000;
      if (ts > Date.now() - HOLD_MS) at = Math.max(at - 1, ts);
    }
    const prev = touches[steer.id];
    touches[steer.id] = {
      at,
      verb: steer.verb || (prev && prev.verb) || "steer",
      host: steer.host || (prev && prev.host) || "",
    };
  }
  if (steer.mouse) placeCursor(steer.mouse);
  paintDrive();
}

function placeCursor(mouse) {
  if (!ghostCursor || !glassWrap || !mouse || !selected || !touches[selected]) {
    if (ghostCursor) ghostCursor.hidden = true;
    return;
  }
  const w = glassWrap.clientWidth || 1;
  const h = glassWrap.clientHeight || 1;
  ghostCursor.style.left = ((mouse.x || 0) / 1280) * w + "px";
  ghostCursor.style.top = ((mouse.y || 0) / 800) * h + "px";
  ghostCursor.hidden = false;
}

function paintChrome(data) {
  if (!data || data.id !== selected) return;
  const tabs = data.tabs || [];
  tabsEl.replaceChildren();
  for (const tab of tabs) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tab";
    b.dataset.tab = tab.id;
    b.dataset.kind = tab.kind || "other";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", tab.id === data.active || tab.front ? "true" : "false");
    b.title = tab.url || "";
    const title = document.createElement("span");
    title.className = "tab__title";
    title.textContent = tab.title || tab.host || "tab";
    const host = document.createElement("span");
    host.className = "tab__host";
    host.textContent = tab.host || "";
    b.append(title, host);
    b.addEventListener("click", () => {
      logAction("tab", { tab: tab.id, host: tab.host, kind: tab.kind });
      chromeAction("activate", { tab: tab.id });
    });
    tabsEl.appendChild(b);
  }
  if (document.activeElement !== urlEl) {
    urlEl.value = data.url || "";
  }
  backBtn.disabled = !data.canBack;
  fwdBtn.disabled = !data.canForward;
  if (data.steering) setHands(data.steering);
  if (data.gate) {
    if (data.gate.gated) gates[data.id] = { reason: data.gate.reason, label: data.gate.label || "needs you" };
    else delete gates[data.id];
    paintDrive();
  }
  if (data.mouse) placeCursor(data.mouse);
  if (data.loginAsk) showLoginAsk(data.loginAsk, true);
}

async function loadChrome() {
  if (!selected) return;
  try {
    const res = await fetch("/api/chrome?id=" + encodeURIComponent(selected));
    if (!res.ok) return;
    paintChrome(await res.json());
  } catch {
    /* desk may be mid-reload */
  }
}

async function chromeAction(action, extra) {
  if (!selected) return;
  try {
    await fetch("/api/chrome", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected, action, ...(extra || {}) }),
    });
  } catch {
    /* ignore */
  }
  await loadChrome();
}

function setStage(row) {
  selected = row ? row.id : null;
  for (const b of rail.querySelectorAll("button")) {
    b.setAttribute("aria-current", b.dataset.id === selected ? "true" : "false");
  }
  if (!row) {
    title.textContent = tenants.length <= 1 ? "Your browser" : "Pick a browser";
    meta.textContent = "";
    empty.classList.remove("off");
    empty.textContent =
      tenants.length <= 1
        ? "Add glass to tenants.json so this desk has a jar."
        : "Choose a jar from the list.";
    browser.hidden = true;
    glass.classList.remove("on");
    unbindGlass();
    watch.hidden = true;
    closeBtn.hidden = true;
    if (vaultBtn) vaultBtn.hidden = true;
    if (workBtn) workBtn.hidden = true;
    paintDrive();
    return;
  }
  title.textContent = row.label;
  meta.textContent = "";
  watch.hidden = !hasGlass(row);
  closeBtn.hidden = false;
  if (vaultBtn) vaultBtn.hidden = false;
  if (workBtn) workBtn.hidden = !hasGlass(row);
  if (queuedAsks[row.id]) {
    const queued = queuedAsks[row.id];
    delete queuedAsks[row.id];
    showLoginAsk(queued, true);
  }
  if (hasGlass(row)) {
    empty.classList.add("off");
    browser.hidden = false;
    glass.classList.add("on");
    bindGlass(glassUrl(row.glass.vnc));
    paintDrive();
    loadChrome();
  } else {
    empty.classList.remove("off");
    empty.textContent = `${row.label} is a name on this desk. No Chromium yet.`;
    browser.hidden = true;
    glass.classList.remove("on");
    unbindGlass();
    paintDrive();
  }
}

function render(data) {
  tenants = data.tenants || [];
  const n = tenants.length;
  sourceEl.textContent =
    n <= 1
      ? `source=${data.source || "file"} · one tenant`
      : `source=${data.source || "file"} · ${n} tenants`;
  document.body.classList.toggle("solo-tenant", n <= 1);
  rail.replaceChildren();
  for (const row of tenants) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = row.id;
    btn.className = "nav-row";
    btn.innerHTML = `<span class="nav-row__mark" aria-hidden="true"><img class="nav-row__folio" src="/brand/assets/logos/folio-cream.svg" alt=""><span class="nav-row__drive"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2a8.8 8.8 0 1 1-7.4 4" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/></svg></span><span class="nav-row__gate"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2 22 20.5H2Z" fill="currentColor"/><rect x="11.1" y="9.2" width="1.8" height="6.2" rx="0.6" fill="#0c0c0e"/><rect x="11.1" y="16.6" width="1.8" height="1.8" rx="0.6" fill="#0c0c0e"/></svg></span></span><span class="nav-row__text"><span class="nav-row__title">${row.label}</span><span class="nav-row__lede"></span></span>`;
    btn.addEventListener("click", () => setStage(row));
    li.appendChild(btn);
    rail.appendChild(li);
  }
}

watch.addEventListener("click", () => {
  const row = tenants.find((t) => t.id === selected);
  if (hasGlass(row)) window.open(glassUrl(row.glass.vnc), "prims-glass-" + row.id);
});

closeBtn.addEventListener("click", () => setStage(null));

backBtn.addEventListener("click", () => chromeAction("back"));
fwdBtn.addEventListener("click", () => chromeAction("forward"));
omnibox.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const next = (urlEl.value || "").trim();
  if (!next) return;
  const url = /^https?:\/\//i.test(next) ? next : "https://" + next;
  chromeAction("nav", { url });
});
if (pageSend) {
  pageSend.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = (pageText && pageText.value) || "";
    if (!selected || !text) return;
    logAction("insert", { n: text.length });
    if (pageSendBtn) pageSendBtn.disabled = true;
    let res = {};
    try {
      const r = await fetch("/api/chrome", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: selected, action: "insert", text }),
      });
      res = await r.json().catch(() => ({}));
      if (!r.ok || res.ok === false) {
        logAction("insert.error", { error: res.error || r.status, n: text.length });
        if (pageText) pageText.placeholder = res.error || "send failed";
        return;
      }
      if (pageText) {
        pageText.value = "";
        pageText.placeholder = "Click a field on the page, then type here";
      }
      logAction("insert.result", { n: res.n, via: res.via });
      try {
        glass.contentWindow && glass.contentWindow.focus();
      } catch {
        glass.focus();
      }
    } catch (e) {
      logAction("insert.error", { error: String(e) });
      if (pageText) pageText.placeholder = "send failed";
    } finally {
      if (pageSendBtn) pageSendBtn.disabled = false;
      await loadChrome();
    }
  });
}
function logAction(kind, extra) {
  fetch("/api/log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, id: selected, gated: Boolean(selected && gates[selected]), ...(extra || {}) }),
  }).catch(() => {});
}

if (continueBtn) {
  continueBtn.addEventListener("click", async () => {
    logAction("continue", { host: selected && touches[selected] && touches[selected].host });
    if (!selected) return;
    let res = {};
    try {
      const r = await fetch("/api/continue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: selected }),
      });
      res = await r.json();
      logAction("continue.result", res);
    } catch (e) {
      logAction("continue.error", { error: String(e) });
    }
    delete gates[selected];
    paintDrive();
    loadChrome();
  });
}

takeoverBtn.addEventListener("click", async () => {
  logAction("takeover");
  fetch("/api/login-deny", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: selected }) });
  delete autos[selected];
  await chromeAction("takeover");
  try {
    glass.contentWindow && glass.contentWindow.focus();
  } catch {
    glass.focus();
  }
});

const html = document.documentElement;
const folio = document.getElementById("folio");
const favicon = document.getElementById("favicon");
const PALETTE_KEY = "prims-browsers.palette";

function darkSystem() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function folioSrc(palette) {
  const ink = palette === "ink" || (palette === "system" && darkSystem());
  return ink
    ? "/brand/assets/logos/folio-gold.svg"
    : "/brand/assets/logos/folio-ink.svg";
}

function applyPalette(palette) {
  html.setAttribute("data-palette", palette);
  const src = folioSrc(palette);
  if (folio) folio.src = src;
  if (favicon) favicon.href = src;
  const theme = document.querySelector('meta[name="theme-color"]');
  if (theme) theme.setAttribute("content", palette === "paper" || (palette === "system" && !darkSystem()) ? "#f4f3ef" : "#0c0c0e");
  document.querySelectorAll(".pal button").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.p === palette ? "true" : "false");
  });
  try {
    localStorage.setItem(PALETTE_KEY, palette);
  } catch {
    /* ignore */
  }
}

document.querySelectorAll(".pal button").forEach((b) => {
  b.addEventListener("click", () => applyPalette(b.dataset.p));
});

let start = "paper";
try {
  start = localStorage.getItem(PALETTE_KEY) || "paper";
} catch {
  start = "paper";
}
applyPalette(start);

fetch("/tenants.json")
  .then((res) => res.json())
  .then((data) => {
    render(data);
    const params = new URLSearchParams(window.location.search);
    const want = params.get("id");
    const row =
      (want && tenants.find((t) => t.id === want)) ||
      (tenants.length === 1 ? tenants[0] : null);
    if (row) {
      setStage(row);
      if (params.has("vault")) openVault();
    } else {
      setStage(null);
    }
  });

function onSteerEvent(data) {
  setHands(data);
  if (data && data.on && data.id === selected) loadChrome();
}

function bindReveal(btn, input) {
  if (!btn || !input) return;
  btn.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.textContent = show ? "Hide" : "Show";
    btn.setAttribute("aria-pressed", show ? "true" : "false");
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
}

async function toggleRowSecret(rid, secretEl, btn) {
  if (secretEl.dataset.open === "1") {
    secretEl.textContent = MASK;
    delete secretEl.dataset.open;
    btn.textContent = "Show";
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", "Show password");
    return;
  }
  btn.disabled = true;
  try {
    const res = await fetch(
      "/api/vault/secret?id=" + encodeURIComponent(selected) + "&record=" + encodeURIComponent(rid)
    );
    const data = await res.json();
    if (!res.ok) {
      secretEl.textContent = "Can’t reveal";
      return;
    }
    secretEl.textContent = data.password || "";
    secretEl.dataset.open = "1";
    btn.textContent = "Hide";
    btn.setAttribute("aria-pressed", "true");
    btn.setAttribute("aria-label", "Hide password");
    logAction("vault.reveal", { record: rid, host: data.host });
  } catch {
    secretEl.textContent = "Can’t reveal";
  } finally {
    btn.disabled = false;
  }
}

function secretLine(rid, host) {
  const line = document.createElement("div");
  line.className = "secret-line";
  const secretEl = document.createElement("code");
  secretEl.textContent = MASK;
  const show = document.createElement("button");
  show.type = "button";
  show.textContent = "Show";
  show.setAttribute("aria-pressed", "false");
  show.setAttribute("aria-label", "Show password" + (host ? " for " + host : ""));
  show.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    toggleRowSecret(rid, secretEl, show);
  });
  line.append(secretEl, show);
  return line;
}

function vaultRow(r) {
  const li = document.createElement("li");
  const main = document.createElement("div");
  main.className = "vault-row";
  const site = document.createElement("div");
  site.className = "vault-row__site";
  site.textContent = r.host || "site";
  const user = document.createElement("div");
  user.className = "vault-row__user";
  const where = r.vault_label || r.vault || "System";
  user.textContent = (r.login || "") + " · " + where;
  main.append(site, user);
  if (r.has_password !== false) main.appendChild(secretLine(r.id, r.host));
  const acts = document.createElement("div");
  acts.className = "vault-row__acts";
  const del = document.createElement("button");
  del.type = "button";
  del.textContent = "Remove";
  del.addEventListener("click", async () => {
    logAction("vault.remove", { record: r.id, host: r.host });
    await fetch("/api/vault", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected, remove: true, record: r.id }),
    });
    loadVault();
  });
  acts.appendChild(del);
  li.append(main, acts);
  return li;
}

async function loadVault() {
  if (!selected || !vaultList) return;
  const res = await fetch("/api/vault?id=" + encodeURIComponent(selected));
  const data = await res.json();
  const rows = data.records || [];
  vaultList.replaceChildren();
  if (vaultEmpty) vaultEmpty.hidden = rows.length > 0;
  for (const r of rows) vaultList.appendChild(vaultRow(r));
  if (vaultTitle) {
    const label = (tenants.find((t) => t.id === selected) || {}).label || selected;
    vaultTitle.textContent = rows.length
      ? "Vault · " + label + " · " + rows.length
      : "Vault · " + label;
  }
}

function openVault() {
  if (!selected) return;
  if (vaultTitle) vaultTitle.textContent = "Vault · " + (tenants.find((t) => t.id === selected) || {}).label;
  if (vaultEl) vaultEl.hidden = false;
  loadVault();
}

function askPick(r, host, checked) {
  const li = document.createElement("li");
  const pick = document.createElement("label");
  pick.className = "ask-card";
  const radio = document.createElement("input");
  radio.type = "radio";
  radio.name = "ask-pick";
  radio.value = r.id;
  radio.checked = checked;
  radio.addEventListener("change", () => {
    askChosen = r.id;
  });
  const body = document.createElement("div");
  body.className = "vault-row";
  const who = document.createElement("div");
  who.className = "vault-row__site";
  who.textContent = r.login || "";
  const site = document.createElement("div");
  site.className = "vault-row__user";
  site.textContent = r.host || host;
  body.append(who, site);
  if (r.has_password !== false) body.appendChild(secretLine(r.id, r.host));
  pick.append(radio, body);
  li.appendChild(pick);
  return li;
}

function prefillAskSave(data) {
  const loginInput = document.getElementById("ask-login");
  const passInput = document.getElementById("ask-pass");
  if (loginInput) loginInput.value = data.last_login || "";
  if (passInput) {
    passInput.value = "";
    passInput.type = "password";
  }
  setTimeout(() => {
    (passInput && loginInput && loginInput.value ? passInput : loginInput)?.focus();
  }, 0);
}

function showLoginAsk(data, force) {
  if (!askEl || !data || !data.id) return;
  if (data.id !== selected) {
    queuedAsks[data.id] = data;
    return;
  }
  if (!askEl.hidden && !force) {
    if (pendingAsk && pendingAsk.id === data.id) force = true;
    else return;
  }
  pendingAsk = data;
  const host = data.host || "this site";
  if (askTitle) askTitle.textContent = "Sign in to " + host;
  const recs = data.records || [];
  const others = data.others || [];
  const picks = recs.length ? recs : others;
  askChosen = picks[0] ? picks[0].id : "";
  if (askList) askList.replaceChildren();
  if (!recs.length && !others.length) {
    askCopy.textContent = "Save it once. Next time I’ll fill this site without asking.";
    if (askSave) askSave.hidden = false;
    if (askApprove) askApprove.hidden = true;
    prefillAskSave(data);
  } else {
    if (!recs.length) {
      askCopy.textContent = "Nothing saved for " + host + " yet. Pick a vault login, or save this one.";
      if (askSave) askSave.hidden = false;
      prefillAskSave(data);
    } else {
      askCopy.textContent = "I’ll type this username, then the password on the next page, and wait if there’s a code.";
      if (askSave) askSave.hidden = true;
    }
    if (askApprove) askApprove.hidden = false;
    recs.forEach((r, i) => askList.appendChild(askPick(r, host, i === 0)));
    if (others.length) {
      if (recs.length) {
        const heading = document.createElement("li");
        heading.className = "ask-list__label";
        heading.textContent = "Also in the vault";
        askList.appendChild(heading);
      }
      others.forEach((r, i) => askList.appendChild(askPick(r, host, !recs.length && i === 0)));
    }
  }
  askEl.hidden = false;
  logAction("login.ask.shown", { host: data.host, n: recs.length, others: others.length });
}

if (workBtn) {
  workBtn.addEventListener("click", async () => {
    if (!selected) return;
    logAction("work.start");
    workBtn.disabled = true;
    try {
      await fetch("/api/work", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: selected, on: true }),
      });
    } finally {
      workBtn.disabled = false;
    }
  });
}
if (vaultBtn) vaultBtn.addEventListener("click", openVault);
document.getElementById("vault-close")?.addEventListener("click", () => { vaultEl.hidden = true; });
function denyAsk() {
  logAction("login.deny");
  fetch("/api/login-deny", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: selected }) });
  askEl.hidden = true;
  pendingAsk = null;
}
document.getElementById("ask-close")?.addEventListener("click", denyAsk);
document.getElementById("ask-deny")?.addEventListener("click", denyAsk);
document.getElementById("ask-vault")?.addEventListener("click", () => {
  if (pendingAsk && pendingAsk.host) {
    const hostEl = document.getElementById("vault-host");
    if (hostEl && !hostEl.value) hostEl.value = pendingAsk.host;
  }
  askEl.hidden = true;
  openVault();
});
document.getElementById("ask-approve")?.addEventListener("click", async () => {
  const record = askChosen;
  logAction("login.approve", { record });
  if (!record) {
    if (askSave) askSave.hidden = false;
    return;
  }
  await fetch("/api/login-approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: selected, record }),
  });
  askEl.hidden = true;
});
bindReveal(document.getElementById("vault-pass-reveal"), document.getElementById("vault-pass"));
bindReveal(document.getElementById("ask-pass-reveal"), document.getElementById("ask-pass"));
askSave?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!selected || !pendingAsk) return;
  const login = document.getElementById("ask-login").value;
  const password = document.getElementById("ask-pass").value;
  logAction("vault.add", { host: pendingAsk.host, login, via: "ask" });
  const res = await fetch("/api/vault", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: selected, host: pendingAsk.host || "", login, password }),
  });
  const data = await res.json();
  const record = data.record && data.record.id;
  if (!res.ok || !record) {
    if (askCopy) askCopy.textContent = data.error || "Couldn’t save that login.";
    return;
  }
  await fetch("/api/login-approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: selected, record }),
  });
  askEl.hidden = true;
});
vaultForm?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const host = document.getElementById("vault-host").value;
  const login = document.getElementById("vault-login").value;
  const saveBtn = vaultForm.querySelector("button[type=submit]");
  logAction("vault.add", { host, login });
  if (saveBtn) saveBtn.disabled = true;
  try {
    await fetch("/api/vault", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: selected,
        host,
        login,
        password: document.getElementById("vault-pass").value,
      }),
    });
    vaultForm.reset();
    const pass = document.getElementById("vault-pass");
    const reveal = document.getElementById("vault-pass-reveal");
    if (pass) pass.type = "password";
    if (reveal) {
      reveal.textContent = "Show";
      reveal.setAttribute("aria-pressed", "false");
    }
    await loadVault();
    if (pendingAsk && pendingAsk.id === selected) {
      const listed = await fetch("/api/vault?id=" + encodeURIComponent(selected));
      const pack = await listed.json();
      const host = (pendingAsk.host || "").replace(/^www\./, "");
      const recs = (pack.records || []).filter((r) => !host || (r.host || "") === host);
      const usable = recs.length ? recs : pack.records || [];
      if (usable.length === 1 && usable[0].has_password !== false) {
        await fetch("/api/login-approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: selected, record: usable[0].id }),
        });
        askEl.hidden = true;
        pendingAsk = null;
      } else {
        showLoginAsk({ ...pendingAsk, records: usable }, true);
      }
    }
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
});

const events = new EventSource("/api/events");
events.addEventListener("steer", (ev) => {
  let data = {};
  try {
    data = JSON.parse(ev.data || "{}");
  } catch {
    data = {};
  }
  onSteerEvent(data);
});
events.addEventListener("steers", (ev) => {
  let rows = [];
  try {
    rows = JSON.parse(ev.data || "[]");
  } catch {
    rows = [];
  }
  if (!Array.isArray(rows)) return;
  for (const row of rows) onSteerEvent(row);
});
events.addEventListener("tabs", (ev) => {
  let data = {};
  try {
    data = JSON.parse(ev.data || "{}");
  } catch {
    data = {};
  }
  if (data.id && data.host && touches[data.id]) {
    touches[data.id].host = data.host;
    paintDrive();
  }
  if (data.id === selected && Array.isArray(data.tabs)) {
    paintChrome({
      id: data.id,
      tabs: data.tabs,
      active: data.active,
      url: (data.tabs.find((t) => t.id === data.active) || data.tabs[0] || {}).url || "",
      canBack: false,
      canForward: false,
    });
  }
});
events.addEventListener("gate", (ev) => {
  let data = {};
  try {
    data = JSON.parse(ev.data || "{}");
  } catch {
    data = {};
  }
  if (!data.id) return;
  if (data.gated) gates[data.id] = { reason: data.reason, label: data.label || "needs you" };
  else delete gates[data.id];
  paintDrive();
});
events.addEventListener("login-ask", (ev) => {
  let data = {};
  try {
    data = JSON.parse(ev.data || "{}");
  } catch {
    data = {};
  }
  showLoginAsk(data, true);
});
events.addEventListener("login-auto", (ev) => {
  let data = {};
  try {
    data = JSON.parse(ev.data || "{}");
  } catch {
    data = {};
  }
  if (!data.id) return;
  if (askEl && data.id === selected) askEl.hidden = true;
  autos[data.id] = { login: data.login || "saved login", host: data.host || "", at: Date.now() };
  logAction("login.auto", { host: data.host, login: data.login });
  paintDrive();
});
events.addEventListener("gates", (ev) => {
  let rows = [];
  try {
    rows = JSON.parse(ev.data || "[]");
  } catch {
    rows = [];
  }
  if (!Array.isArray(rows)) return;
  for (const g of rows) {
    if (g.id && g.gated) gates[g.id] = { reason: g.reason, label: g.label || "needs you" };
    else if (g.id) delete gates[g.id];
  }
  paintDrive();
});
