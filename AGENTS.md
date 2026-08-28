# Prims Browsers

Product: primfoundation/prims-browsers. Local: `~/repos-prim-foundation/prims-browsers`.

- Own product. Do not shell out to eidos-browsing. Copy ideas, not the CLI.
- Tenant directory is mocked (`tenants.json`). Later: `prims-desktop tenants --json`.
- Hands: CDP (`lib/cdp.py`) first, VNC/xdotool if the DOM will not yield.
Record: `prims-browsers record <id> start|stop` — jar DISPLAY `:0` via ffmpeg x11grab. Not host screencapture. Not CDP screencast.
- Glass is embedded in the desk iframe. Do not poll. Do not reset iframe.src. noVNC URL uses resize=scale.
- Do not copy a human Chrome/Comet cookie jar into these profiles.
- Five jars. gmw is the existing logged-in Cerebro box. The other four are `jars/compose.yaml` (Paseo per tenant). Do not copy Comet cookies.
- Config belongs under this repo / `~/.prim/` — not `~/.eidos-browsing/`.
- Visuals: `brand/` is `prim.brand` packs/prim. `identity.json` is law. Link `kit.css`. Do not invent hex. No Eidos tridot. No `#6c8aff`.
- Gold folio on ink, ink folio on paper. Default palette is paper (prims.sh). Paper/Ink/System lives in the top bar.
- NavRow: selected is a raised rounded fill. Never a left accent stripe.
- Tests: `prims-browsers test` or `python3 -m pytest tests/ -q`. Isolated vault/desk; does not drive live jars. Record proofs with `testr`.
- Serve does not auto-start work loops. Click Work on the desk (or POST `/api/work`). `PRIMS_BROWSERS_AUTOWORK=1` restores the old race.
- Hands follow the assigned/visible tab. Never skip `/login`. Continue during login does not yank the work tab in front.
