# Prims Browsers

GitHub: https://github.com/primfoundation/prims-browsers

Local tree: `~/repos-prim-foundation/prims-browsers`

Headed Chromium per tenant. Glass lives in a browser tab (desk + noVNC). Close the tab; the jar keeps running.

Hands are this product: **CDP first**, VNC/xdotool if the page will not yield. Not eidos-browsing.

```bash
ln -sf "$(pwd)/bin/prims-browsers" ~/.local/bin/prims-browsers
prims-browsers tenants
prims-browsers doctor
prims-browsers open          # desk at http://127.0.0.1:7751/
prims-browsers tabs gmw
prims-browsers screenshot gmw --out /tmp/gmw.png
```

Tenant list is mocked in `tenants.json`. Later: `prims-desktop tenants --json`.
