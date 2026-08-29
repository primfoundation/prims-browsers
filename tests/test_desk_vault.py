"""Desk vault: list of logins, masked by default, Show reveals, Hide covers again."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _wait_health(url: str, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=0.4) as res:
                if res.status == 200:
                    return
        except Exception as e:
            last = e
        time.sleep(0.1)
    raise AssertionError(f"desk did not come up: {last}")


def test_vault_list_hidden_then_reveal(tmp_path, free_port, monkeypatch, chrome):
    from playwright.sync_api import sync_playwright

    from lib import vault as vault_lib

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(vault_root))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    monkeypatch.delenv("PASEO_VAULT_DIR", raising=False)
    a = vault_lib.add("eidos", "prims-fixture", "you@example.com", "demo-pass-not-real")
    vault_lib.add("eidos", "chatgpt.com", "you@example.com", "other-secret")

    tenants = tmp_path / "tenants.json"
    tenants.write_text(
        json.dumps(
            {
                "source": "test",
                "tenants": [{"id": "eidos", "label": "Eidos"}],
            }
        )
    )
    env = {
        **dict(os.environ),
        "PRIMS_VAULT_ROOT": str(vault_root),
        "PRIMS_VAULTS": str(tmp_path / "vaults.json"),
        "PRIMS_BROWSERS_PORT": str(free_port),
        "PRIMS_BROWSERS_NO_WATCH": "1",
        "PRIMS_BROWSERS_TENANTS": str(tenants),
        "PRIMS_ACTLOG": str(tmp_path / "actions.jsonl"),
        "PRIMS_ACTLOG_QUIET": "1",
    }
    log = (tmp_path / "desk.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "bin" / "prims-browsers"), "serve"],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{free_port}"
    try:
        _wait_health(base)
        with urllib.request.urlopen(base + "/api/vault?id=eidos") as res:
            payload = json.loads(res.read().decode())
        assert len(payload["records"]) == 2
        assert all("password" not in r for r in payload["records"])

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            page.goto(base + "/?id=eidos&vault=1", wait_until="domcontentloaded")
            page.wait_for_selector(".vault-list li", timeout=8000)
            assert page.locator(".vault-list li").count() == 2
            sites = page.locator(".vault-row__site").all_inner_texts()
            assert set(sites) == {"prims-fixture", "chatgpt.com"}
            secrets = page.locator(".secret-line code").all_inner_texts()
            assert secrets == ["••••••••", "••••••••"]
            page.locator(".vault-list li").nth(0).locator("button", has_text="Show").click()
            page.wait_for_function(
                "() => document.querySelector('.secret-line code')?.textContent !== '••••••••'"
            )
            shown = page.locator(".secret-line code").nth(0).inner_text()
            assert shown != "••••••••"
            assert len(shown) > 0
            assert page.locator(".vault-list li").nth(0).locator(".secret-line button").inner_text() == "Hide"
            still = page.locator(".secret-line code").nth(1).inner_text()
            assert still == "••••••••"
            page.locator(".vault-list li").nth(0).locator("button", has_text="Hide").click()
            page.wait_for_function(
                "() => document.querySelector('.secret-line code')?.textContent === '••••••••'"
            )
            proof = tmp_path / "vault-list.png"
            page.screenshot(path=str(proof))
            browser.close()
        assert proof.is_file() and proof.stat().st_size > 1000
        _ = a
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except Exception:
            proc.kill()
