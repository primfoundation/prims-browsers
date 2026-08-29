# Changelog

All notable changes to this project are documented here.

## Unreleased

### Product
- Position as FOSS toolkit: sandbox jars agents drive without the host mouse.
- Paseo plugin → usually one tenant; local desk → multi-tenant.
- Desk auto-opens a sole tenant and hides the rail; multi-tenant keeps the picker.
- Tenant `work` URL lives in `tenants.json` (no hardcoded fleet map).
- Doctor validates config shape, not a fixed five-tenant list.
- System vault always on; connect additional vaults (`paseo-vault`) via `vaults.json` / `prims-browsers vaults`. Write target defaults to system; lists merge.
- FOSS sample `jars/compose.yaml` (alpha/beta → example.com); private fleets stay in gitignored `compose.local.yaml`.
- README screenshots under `docs/screenshots/`; `scripts/capture-screenshots.py` regenerates them.
- CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md; `tenants.json` gitignored (use `tenants.example.json`).

## 0.1.0 — 2026-08-27

- Initial desk, CDP hands, VNC fallback, brand kit, jar compose, record via x11grab.
