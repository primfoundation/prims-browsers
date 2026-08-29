#!/usr/bin/env python3
"""Capture FOSS-safe README screenshots. Requires Chrome + Playwright + a live jar optional."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
BIN = ROOT / "bin" / "prims-browsers"


def wait_health(base: str, tries: int = 80) -> None:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(base + "/health", timeout=0.4) as res:
                if res.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise SystemExit(f"desk not healthy: {base}")


def start_desk(tenants: Path, port: int, vault: Path) -> tuple[subprocess.Popen, str]:
    env = {
        **os.environ,
        "PRIMS_BROWSERS_PORT": str(port),
        "PRIMS_BROWSERS_TENANTS": str(tenants),
        "PRIMS_BROWSERS_NO_WATCH": "1",
        "PRIMS_ACTLOG_QUIET": "1",
        "PRIMS_VAULT_ROOT": str(vault),
        "PRIMS_BROWSERS_TEST": "1",
    }
    vault.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, str(BIN), "serve"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        wait_health(base)
    except SystemExit:
        proc.kill()
        raise
    return proc, base


def post(base: str, path: str, data: dict) -> dict:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode())


def stop(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=4)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Neutral page in a live jar when present (ignore failures).
    subprocess.run([str(BIN), "nav", "eidos", "https://example.com/"], check=False, cwd=str(ROOT))
    try:
        sys.path.insert(0, str(ROOT))
        from lib import cdp as cdp_lib

        _page, ws = cdp_lib.first_page_ws("http://127.0.0.1:19221")
        cdp_lib.call(
            ws,
            "Runtime.evaluate",
            {
                "expression": """(() => {
                  for (const b of document.querySelectorAll('button')) {
                    const t = (b.textContent || '').trim().toLowerCase();
                    if (t === 'cancel') { b.click(); return 'cancel'; }
                  }
                  return null;
                })()""",
            },
        )
    except Exception:
        pass
    time.sleep(1.0)

    td = Path(tempfile.mkdtemp(prefix="prims-shot-"))
    multi = {
        "source": "file",
        "tenants": [
            {
                "id": "work",
                "label": "Work",
                "home": "https://example.com/",
                "work": "https://example.com/",
                "glass": {
                    "container": "prims-browsers-eidos",
                    "vnc": "http://127.0.0.1:15801",
                    "cdp": "http://127.0.0.1:19221",
                },
            },
            {
                "id": "personal",
                "label": "Personal",
                "home": "https://example.org/",
                "work": "https://example.org/",
                "glass": {
                    "container": "prims-browsers-aic",
                    "vnc": "http://127.0.0.1:15803",
                    "cdp": "http://127.0.0.1:19223",
                },
            },
            {"id": "client", "label": "Client", "home": "https://example.net/", "work": "https://example.net/"},
        ],
    }
    solo = {
        "source": "file",
        "tenants": [
            {
                "id": "mine",
                "label": "My jar",
                "home": "https://example.com/",
                "work": "https://example.com/",
                "glass": {
                    "container": "prims-browsers-eidos",
                    "vnc": "http://127.0.0.1:15801",
                    "cdp": "http://127.0.0.1:19221",
                },
            }
        ],
    }
    multi_path = td / "multi.json"
    solo_path = td / "solo.json"
    multi_path.write_text(json.dumps(multi, indent=2))
    solo_path.write_text(json.dumps(solo, indent=2))

    proc_m, base_m = start_desk(multi_path, 7761, td / "v-m")
    proc_s, base_s = start_desk(solo_path, 7762, td / "v-s")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)

            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            page.goto(base_m + "/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#rail button", timeout=10000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "desk-multi.png"))
            print("desk-multi.png")

            page.goto(base_m + "/?id=work", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2800)
            page.screenshot(path=str(OUT / "desk-glass.png"))
            print("desk-glass.png")

            page2 = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
            page2.goto(base_s + "/", wait_until="domcontentloaded", timeout=20000)
            page2.wait_for_timeout(2200)
            page2.screenshot(path=str(OUT / "desk-solo.png"))
            print("desk-solo.png")

            post(
                base_s,
                "/api/test/event",
                {
                    "event": "login-ask",
                    "data": {
                        "id": "mine",
                        "host": "example.com",
                        "records": [
                            {"id": "aaa", "host": "example.com", "login": "you@example.com", "has_password": True},
                            {"id": "bbb", "host": "example.com", "login": "alt@example.com", "has_password": True},
                        ],
                    },
                },
            )
            page2.wait_for_timeout(700)
            page2.screenshot(path=str(OUT / "desk-vault-ask.png"))
            print("desk-vault-ask.png")
            browser.close()
    finally:
        stop(proc_m)
        stop(proc_s)

    for p in sorted(OUT.glob("*.png")):
        print(f"  {p.name} {p.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
