# Prims Browsers

Product: primfoundation/prims-browsers. Local: `~/repos-prim-foundation/prims-browsers`.

- **Why:** sandbox jars where agents browse and take mouse control **without affecting the host mouse**. Not eidos-browsing.
- **Deploy:** Paseo plugin → usually **one tenant**. Local machine desk → **multi-tenant** is the point (several sandboxes).
- **Vault:** system vault always on; people may connect their own vault(s) (`vaults.json` / `prims-browsers vaults connect`). Lists merge; write target defaults to system.
- Own product. Do not shell out to eidos-browsing. Copy ideas, not the CLI.
- Tenant directory is `tenants.json` (gitignored; copy `tenants.example.json`). Override with `PRIMS_BROWSERS_TENANTS`. Private fleets: `jars/compose.local.yaml` (gitignored). FOSS sample: `jars/compose.yaml`.
- Hands: CDP (`lib/cdp.py`) first, VNC/xdotool if the DOM will not yield. Jar DISPLAY, not host Accessibility mouse injection.
- Record: `prims-browsers record <id> start|stop` — jar DISPLAY `:0` via ffmpeg x11grab. Not host screencapture. Not CDP screencast.
- Glass is embedded in the desk iframe. Do not poll. Do not reset iframe.src. noVNC URL uses resize=scale.
- Desk: auto-open the sole tenant; show the rail only when there are two or more.
- Do not copy a human Chrome/Comet cookie jar into these profiles.
- Config belongs under this repo / `~/.prim/` — not `~/.eidos-browsing/`.
- Visuals: `brand/` is `prim.brand` packs/prim. `identity.json` is law. Link `kit.css`. Do not invent hex. No Eidos tridot. No `#6c8aff`.
- Gold folio on ink, ink folio on paper. Default palette is paper (prims.sh). Paper/Ink/System lives in the top bar.
- NavRow: selected is a raised rounded fill. Never a left accent stripe.
- Tests: `prims-browsers test` or `python3 -m pytest tests/ -q`. Isolated vault/desk; does not drive live jars. Record proofs with `testr`.
- Serve does not auto-start work loops. Click Work on the desk (or POST `/api/work`). `PRIMS_BROWSERS_AUTOWORK=1` restores the old race. Work URL comes from `tenants[].work` (else `home`).
- Hands follow the assigned/visible tab. Never skip `/login`. Continue during login does not yank the work tab in front.
