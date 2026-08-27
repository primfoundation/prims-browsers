const rail = document.getElementById("rail");
const title = document.getElementById("title");
const meta = document.getElementById("meta");
const empty = document.getElementById("empty");
const glass = document.getElementById("glass");
const watch = document.getElementById("watch");
const closeBtn = document.getElementById("close");
const sourceEl = document.getElementById("source");

let selected = null;
let tenants = [];

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

function setStage(row) {
  selected = row ? row.id : null;
  for (const b of rail.querySelectorAll("button")) {
    b.setAttribute("aria-current", b.dataset.id === selected ? "true" : "false");
  }
  if (!row) {
    title.textContent = "Pick a tenant";
    meta.textContent = "";
    empty.classList.remove("off");
    empty.textContent = "Five desks. Click Greenmark to embed the glass here.";
    glass.classList.remove("on");
    unbindGlass();
    watch.hidden = true;
    closeBtn.hidden = true;
    return;
  }
  title.textContent = row.label;
  meta.textContent = [row.sandbox || `sandbox:${row.id}`, hasGlass(row) ? row.glass.vnc : "no glass"].join(" · ");
  watch.hidden = !hasGlass(row);
  closeBtn.hidden = false;
  if (hasGlass(row)) {
    empty.classList.add("off");
    glass.classList.add("on");
    bindGlass(glassUrl(row.glass.vnc));
  } else {
    empty.classList.remove("off");
    empty.textContent = `${row.label} is a name on this desk. No Chromium yet.`;
    glass.classList.remove("on");
    unbindGlass();
  }
}

function render(data) {
  tenants = data.tenants || [];
  sourceEl.textContent = `source=${data.source || "mock"} · later=${data.later || ""}`;
  rail.replaceChildren();
  for (const row of tenants) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.id = row.id;
    const kind = hasGlass(row) ? "glass" : "name";
    btn.innerHTML = `<span class="state ${kind}">${kind}</span><span class="id">${row.id}</span><span class="label">${row.label}</span>`;
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

fetch("/tenants.json")
  .then((res) => res.json())
  .then(render);
