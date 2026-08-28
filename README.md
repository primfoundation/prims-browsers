# Prims Browsers

GitHub: https://github.com/primfoundation/prims-browsers

Local tree: `~/repos-prim-foundation/prims-browsers`

Headed Chromium per tenant. Glass lives in a browser tab (desk + noVNC). Close the tab; the jar keeps running. Tabs, URL, back/forward, and Take over stay on the desk; the jar Chromium is not allowed to go fullscreen and hide its chrome.

Hands are this product: **CDP first**, VNC/xdotool if the page will not yield. Not eidos-browsing.

```bash
ln -sf "$(pwd)/bin/prims-browsers" ~/.local/bin/prims-browsers
prims-browsers tenants
prims-browsers doctor
prims-browsers open          # desk at http://127.0.0.1:7751/
prims-browsers tabs gmw
prims-browsers screenshot gmw --out /tmp/gmw.png
prims-browsers record eidos start --out /tmp/eidos.mp4
prims-browsers record eidos stop
```

`record` is ffmpeg x11grab of the jar's `:0` (headed Chromium), not the Mac desktop. `stop` copies the mp4 out. First start will `add-pkg ffmpeg` if the image was built before that package landed.

Five jars. Greenmark keeps the existing Cerebro box. The other four:

```bash
docker compose -f jars/compose.yaml up -d
```

| Tenant | Starts at |
|---|---|
| eidos | example.com |
| gmw | example.com |
| aic | example.org |
| arp | example.net |
| reeves | example.com |

Tenant list is mocked in `tenants.json`. Later: `prims-desktop tenants --json`.

Brand: `brand/` is the Prim kit from `prim.brand` (`packs/prim`). Desk links `kit.css` and sets `data-palette="ink"`. Do not copy tokens out of the pack.

```bash
prims-browsers test          # vault + login fixture + desk vault UI
python3 -m pytest tests/ -q
```

Tests use a temp vault and a throwaway desk port. They do not click around the live tenant jars.

Work does not start on `serve`. Open a tenant and click **Work**, or `POST /api/work`. Desk restarts itself when source files are newer than the running process.
