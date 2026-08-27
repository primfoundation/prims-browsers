# Prims Browsers

Product: primfoundation/prims-browsers. Local: `~/repos-prim-foundation/prims-browsers`.

- Own product. Do not shell out to eidos-browsing. Copy ideas, not the CLI.
- Tenant directory is mocked (`tenants.json`). Later: `prims-desktop tenants --json`.
- Hands: CDP (`lib/cdp.py`) first, VNC/xdotool if the DOM will not yield.
- Glass is embedded in the desk iframe. Do not poll. Do not reset iframe.src. noVNC URL uses resize=scale.
- Do not copy a human Chrome/Comet cookie jar into these profiles.
- Do not start five Chromiums for a mock. One live glass is enough (gmw).
- Config belongs under this repo / `~/.prim/` — not `~/.eidos-browsing/`.
- Visuals: `brand/` is `prim.brand` packs/prim. `identity.json` is law. Link `kit.css`. Do not invent hex. No Eidos tridot. No `#6c8aff`. Gold folio on ink.
