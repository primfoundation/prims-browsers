"""Isolated real-Chromium proof; never connects to a live user's jar.

Run with PRIMS_TEST_IMAGE set to an already-local Chromium container image ID.
The temporary container uses no host profile, mounts, credentials, or public port.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

import pytest

from lib import cdp


ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not os.environ.get("PRIMS_TEST_IMAGE"), reason="isolated Chromium image not supplied")


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def until(fn, seconds=8):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            value = fn()
            if value:
                return value
        except Exception as exc:
            last = exc
        time.sleep(0.1)
    raise AssertionError(f"condition did not become true: {last}")


def test_redirect_takeover_restart_and_closed_target(tmp_path):
    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/work":
                self.send_response(302)
                self.send_header("Location", "/auth/signin")
                self.end_headers()
                return
            body = ("<title>Fixture sign in</title><h1>Sign in</h1><form>"
                    "<input type=email name=username placeholder=Username>"
                    "<input type=password name=password><button>Sign in</button></form>")
            if self.path in ("/done", "/manual"):
                body = "<title>Fixture page</title><h1>Ready</h1><input placeholder=Notes>"
            payload = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    site = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    site_url = f"http://127.0.0.1:{site.server_port}"
    cdp_port, desk_port = port(), port()
    browser_url, desk_url = f"http://127.0.0.1:{cdp_port}", f"http://127.0.0.1:{desk_port}"
    container = "prims-control-proof-" + uuid.uuid4().hex[:10]
    ledger = tmp_path / "tabs.json"
    tenants = tmp_path / "tenants.json"
    tenants.write_text(json.dumps({"tenants": [{"id": "fixture", "work": site_url + "/work", "glass": {"cdp": browser_url}}]}))
    env = {**os.environ, "PRIMS_BROWSERS_PORT": str(desk_port), "PRIMS_BROWSERS_TENANTS": str(tenants),
           "PRIMS_TABS_LEDGER": str(ledger), "PRIMS_VAULT_ROOT": str(tmp_path / "vault"),
           "PRIMS_VAULTS": str(tmp_path / "vaults.json"), "PRIMS_ACTLOG": str(tmp_path / "actions.jsonl"),
           "PRIMS_ACTLOG_QUIET": "1"}
    for key in ("PRIMS_BROWSERS_NO_WATCH", "PRIMS_BROWSERS_AUTOWORK", "PASEO_VAULT_DIR"):
        env.pop(key, None)
    desk = None
    log = (tmp_path / "desk.log").open("w")

    def start_desk():
        proc = subprocess.Popen([sys.executable, str(ROOT / "bin/prims-browsers"), "serve"], cwd=ROOT, env=env, stdout=log, stderr=log)
        until(lambda: urllib.request.urlopen(desk_url + "/health", timeout=0.5).status == 200)
        return proc

    def post(path, data):
        req = urllib.request.Request(desk_url + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    def stable(ids, active=None):
        for _ in range(3):
            assert {p["id"] for p in cdp.pages(browser_url)} == ids
            if active:
                assert cdp.visible_page(browser_url)["id"] == active
            time.sleep(1)

    try:
        launched = subprocess.run(["docker", "run", "-d", "--rm", "--pull=never", "--name", container,
                                   "--network", "host", "--entrypoint", "/usr/bin/chromium", os.environ["PRIMS_TEST_IMAGE"],
                                   "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                                   "--no-first-run", "--disable-background-networking", "--remote-allow-origins=*",
                                   f"--remote-debugging-port={cdp_port}", "--user-data-dir=/tmp/prims-proof-profile", "about:blank"],
                                  capture_output=True, text=True, timeout=15)
        assert launched.returncode == 0, launched.stderr
        until(lambda: cdp.version(browser_url))
        desk = start_desk()
        assert post("/api/work", {"id": "fixture", "on": True})["ok"]
        work = until(lambda: next((p for p in cdp.pages(browser_url) if "/auth/signin" in p["url"]), None))
        target = work["id"]
        ids = {p["id"] for p in cdp.pages(browser_url)}
        # The previous Continue implementation created a replacement work tab.
        post("/api/continue", {"id": "fixture"})
        post("/api/work", {"id": "fixture", "on": True})
        stable(ids)
        cdp.navigate(work["ws"], site_url + "/sso/authorize")
        post("/api/continue", {"id": "fixture"})
        stable(ids)
        assert json.loads(ledger.read_text())["fixture"]["work_tab"] == target
        assert post("/api/chrome", {"id": "fixture", "action": "takeover"})["human"]
        manual_id = cdp.create_tab(browser_url, site_url + "/manual")["targetId"]
        manual = until(lambda: next((p for p in cdp.pages(browser_url) if p["id"] == manual_id), None))
        cdp.call(manual["ws"], "Page.bringToFront")
        ids.add(manual_id)
        cdp.navigate(work["ws"], site_url + "/done")
        post("/api/continue", {"id": "fixture"})
        stable(ids, manual_id)
        desk.terminate()
        desk.wait(timeout=5)
        env["PRIMS_BROWSERS_AUTOWORK"] = "1"
        desk = start_desk()
        stable(ids, manual_id)
        assert json.loads(ledger.read_text())["fixture"]["human"] is True
        # Explicit Work resumes the same target; closing it stops, without replacement.
        post("/api/work", {"id": "fixture", "on": True})
        until(lambda: cdp.visible_page(browser_url)["id"] == target)
        cdp.call(cdp.version(browser_url)["webSocketDebuggerUrl"], "Target.closeTarget", {"targetId": target})
        ids.remove(target)
        stable(ids)
        post("/api/continue", {"id": "fixture"})
        stable(ids)
        print(json.dumps({"sso_target_preserved": True, "continue_created_tabs": 0,
                          "takeover_preserved_manual_focus": True, "takeover_survived_autowork_restart": True,
                          "closed_target_replacements": 0}))
    finally:
        if desk:
            desk.terminate()
            try:
                desk.wait(timeout=5)
            except subprocess.TimeoutExpired:
                desk.kill()
        log.close()
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=15)
        site.shutdown()
        site.server_close()
