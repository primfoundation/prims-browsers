# Contributing

Thanks for helping with Prims Browsers.

## Setup

```bash
git clone https://github.com/primfoundation/prims-browsers.git
cd prims-browsers
cp tenants.example.json tenants.json
ln -sf "$(pwd)/bin/prims-browsers" ~/.local/bin/prims-browsers
python3 -m pip install pytest playwright   # playwright for desk UI tests
playwright install chromium                # or use channel=chrome on macOS
```

Optional jars:

```bash
docker compose -f jars/compose.yaml up -d --build
```

Point `tenants.json` `glass` at the containers you started.

## Checks

```bash
prims-browsers doctor
prims-browsers test
# or: python3 -m pytest tests/ -q
```

UI screenshots for the README:

```bash
python3 scripts/capture-screenshots.py
```

## Guidelines

- Keep the product a **toolkit**: sandbox jars agents control without the host mouse.
- Paseo plugin shape = usually one tenant; local desk = multi-tenant is fine.
- Do not shell out to eidos-browsing. Do not copy human Chrome/Comet cookie jars into profiles.
- Brand: use `brand/` (`prim.brand`). Do not invent hex; no Eidos tridot.
- Secrets and private fleets stay out of git (`tenants.json`, `jars/compose.local.yaml`).
- Prefer small PRs with tests for vault, desk, and CDP behavior.

## License

By contributing you agree your changes are MIT, same as this repository.
