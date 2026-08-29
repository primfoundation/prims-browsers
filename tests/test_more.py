"""Extra proofs for gates, login steps, desk APIs, tab kinds."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from lib import cdp
from lib import gate
from lib import login
from lib import tabs
from lib import vault

FIX = Path(__file__).resolve().parent / "fixtures"


def test_pick_page_missing_tab():
    pages = [{"id": "A", "url": "https://x", "ws": "ws"}]
    try:
        cdp.pick_page(pages, tab_id="nope")
    except RuntimeError as e:
        assert "not found" in str(e)
    else:
        raise AssertionError("expected RuntimeError")


def test_ocr_reason_ignores_cookies_and_article_words():
    assert gate.ocr_reason("Accept and Continue to use cookies") is None
    assert gate.ocr_reason("This article mentions a captcha in passing") is None
    assert gate.ocr_reason("Please verify you are human") == "human"
    assert gate.ocr_reason("Just a moment") == "cloudflare"
    assert gate.ocr_reason("Enter the characters you see") == "captcha"


def test_hard_gate_matrix():
    for r in ("captcha", "human", "cloudflare", "2fa", "login", "sso"):
        assert gate.is_hard(r) is True
    assert gate.is_hard("consent") is False
    assert gate.is_hard(None) is False


def test_tab_classify():
    assert tabs.classify("https://chatgpt.com/auth/login", False, "https://chatgpt.com/") == "auth"
    assert tabs.classify("https://chatgpt.com/", False, "https://chatgpt.com/") == "work"
    assert tabs.classify("https://chatgpt.com/auth/login", True, "https://chatgpt.com/") == "gate"
    assert tabs.classify("https://www.bbc.com/news", False, "https://chatgpt.com/") == "other"


def test_form_steps_chatgpt_sso_password(chrome):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto((FIX / "chatgpt-like.html").as_uri())
        chat = page.evaluate(login.FORM_JS)
        page.evaluate("""() => {
          window.__clicked = [];
          document.querySelectorAll('button').forEach((b) => {
            b.addEventListener('click', () => { window.__clicked.push((b.id || b.innerText).trim()); });
          });
        }""")
        page.evaluate(login.SUBMIT_JS)
        submit_clicked = page.evaluate("window.__clicked")
        page.goto((FIX / "sso-only.html").as_uri())
        sso = page.evaluate(login.FORM_JS)
        page.goto((FIX / "password-only.html").as_uri())
        pw = page.evaluate(login.FORM_JS)
        page.goto((FIX / "consent.html").as_uri())
        clicked = page.evaluate(gate.CONSENT_JS)
        left = page.evaluate(gate.DETECT_JS)
        page.goto((FIX / "save-bubble.html").as_uri())
        dismissed = page.evaluate(login.DISMISS_JS)
        after = page.evaluate("window.__clicked")
        page.goto((FIX / "stay-signed-in.html").as_uri())
        stay = page.evaluate(login.DISMISS_JS)
        stay_clicked = page.evaluate("window.__clicked")
        page.goto((FIX / "signin-with-notnow.html").as_uri())
        skip_save = page.evaluate(login.DISMISS_JS)
        sign_clicked = page.evaluate("window.__clicked")
        page.goto((FIX / "delete-yes.html").as_uri())
        no_delete = page.evaluate(login.DISMISS_JS)
        delete_clicked = page.evaluate("window.__clicked")
        browser.close()
    assert chat.get("step") == "username"
    assert chat.get("hasSso") is True
    assert submit_clicked == ["go"]
    assert sso.get("step") == "sso"
    assert pw.get("step") == "password"
    assert pw.get("remembered") == "you@example.com"
    assert clicked.get("ok") is True
    assert left.get("reason") is None or left.get("reason") != "human"
    assert dismissed.get("ok") is True
    assert after[0] in ("never", "notnow")
    assert stay.get("kind") == "stay"
    assert stay_clicked == ["yes"]
    assert skip_save.get("kind") == "skip"
    assert sign_clicked == ["notnow"]
    assert no_delete.get("ok") is False
    assert delete_clicked == []


def test_combined_form_fills_user_then_password(chrome):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto((FIX / "combined-login.html").as_uri())
        form = page.evaluate(login.FORM_JS)
        assert form.get("step") == "password"
        assert form.get("hasUser") is True
        session = page.context.new_cdp_session(page)
        page.evaluate(login.FOCUS_JS % json.dumps("username"))
        session.send("Input.insertText", {"text": "a@x"})
        page.evaluate(login.FOCUS_JS % json.dumps("password"))
        session.send("Input.insertText", {"text": "s3cret"})
        page.evaluate(login.SUBMIT_JS)
        assert page.evaluate("document.body.dataset.in") == "a@x:set"
        browser.close()


def test_fill_password_skips_hidden_continue(tmp_path, chrome):
    import http.server
    import socket
    import socketserver
    import subprocess
    import threading
    import time

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_a):
            pass

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    http_port = s.getsockname()[1]
    s.close()
    d = socket.socket()
    d.bind(("127.0.0.1", 0))
    dbg = d.getsockname()[1]
    d.close()

    class Handler(Quiet):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(FIX), **k)

    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", http_port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    profile = tmp_path / "ch"
    profile.mkdir()
    proc = subprocess.Popen(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={dbg}",
            "--remote-allow-origins=*",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    cdp_base = f"http://127.0.0.1:{dbg}"
    try:
        deadline = time.time() + 12
        ready = False
        while time.time() < deadline:
            try:
                if cdp.version(cdp_base).get("webSocketDebuggerUrl"):
                    ready = True
                    break
            except Exception:
                time.sleep(0.15)
        assert ready, "chrome CDP did not come up"
        pages = cdp.pages(cdp_base)
        if not pages:
            cdp.create_tab(cdp_base, f"http://127.0.0.1:{http_port}/hidden-continue.html")
            time.sleep(0.4)
            pages = cdp.pages(cdp_base)
        page = pages[0]
        cdp.navigate(page["ws"], f"http://127.0.0.1:{http_port}/hidden-continue.html")
        time.sleep(0.4)
        pages = cdp.pages(cdp_base)
        page = next((p for p in pages if "hidden-continue" in (p.get("url") or "")), pages[0])
        form = login.inspect_form(page["ws"])
        assert form.get("step") == "password"
        r = login.fill_password(page["ws"], "demo-pass-not-real")
        assert r.get("ok") is True
        time.sleep(0.3)
        clicked = cdp.call(
            page["ws"],
            "Runtime.evaluate",
            {"expression": "window.__clicked", "returnByValue": True},
        )["result"]["value"]
        assert "go-pass" in clicked
        assert "go-user" not in clicked
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        httpd.shutdown()


def test_desk_health_revision_and_secret(desk):
    with urllib.request.urlopen(desk.base + "/health") as res:
        health = json.loads(res.read().decode())
    assert health["ok"] is True
    assert health["pid"]
    assert health["revision"]
    assert health["port"] == desk.port
    req = urllib.request.Request(desk.base + "/api/vault/secret?id=eidos&record=missing")
    try:
        urllib.request.urlopen(req)
        raise AssertionError("expected 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    add = urllib.request.Request(
        desk.base + "/api/vault",
        data=json.dumps(
            {"id": "eidos", "host": "chatgpt.com", "login": "a@x", "password": "nolog"}
        ).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(add) as res:
        body = json.loads(res.read().decode())
    rid = body["record"]["id"]
    assert "password" not in body["record"]
    with urllib.request.urlopen(desk.base + "/api/vault?id=eidos") as res:
        listed = json.loads(res.read().decode())
    assert all("password" not in r for r in listed["records"])
    with urllib.request.urlopen(desk.base + f"/api/vault/secret?id=eidos&record={rid}") as res:
        secret = json.loads(res.read().decode())
    assert secret.get("password") == "nolog"
    with urllib.request.urlopen(desk.base + "/") as res:
        html = res.read().decode()
    assert 'id="work-btn"' in html
    assert 'id="ask-save"' in html
    assert 'name="vault-secret"' in html
    assert 'id="page-send"' in html
    assert 'id="page-text"' in html
    assert "clipboard-read" in html
    js = urllib.request.urlopen(desk.base + "/desk.js").read().decode()
    assert "login-auto" in js
    assert "filling as" in js
    assert "last_login" in js
    assert 'action: "insert"' in js
    assert 'autocomplete="new-password"' not in html
    assert 'name="password"' not in html.split("id=\"vault-form\"")[1].split("</form>")[0]
    deny = urllib.request.Request(
        desk.base + "/api/login-deny",
        data=json.dumps({"id": "eidos"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(deny) as res:
        assert json.loads(res.read().decode())["ok"] is True
    bad = urllib.request.Request(
        desk.base + "/api/login-approve",
        data=json.dumps({"id": "eidos"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(bad)
        raise AssertionError("expected 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_vault_www_roundtrip(vault_dir):
    row = vault.add("eidos", "WWW.ChatGPT.com", "One@X", "p")
    assert row["host"] == "chatgpt.com"
    assert vault.list_for_host("eidos", "www.chatgpt.com")[0]["id"] == row["id"]
    assert vault.list_for_host("eidos", "nope.example") == []
