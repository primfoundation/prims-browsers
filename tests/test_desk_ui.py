"""Drive the desk in headless Chrome. No human, no live jars."""

from __future__ import annotations

import json
import urllib.request


def _post(base: str, path: str, data: dict) -> dict:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())


def test_login_approve_without_cdp_does_not_kill_desk(desk):
    from lib import vault as vault_lib

    row = vault_lib.add("eidos", "chatgpt.com", "a@x", "pw")
    out = _post(desk.base, "/api/login-approve", {"id": "eidos", "record": row["id"]})
    assert out.get("ok") is True
    with urllib.request.urlopen(desk.base + "/health") as res:
        assert json.loads(res.read().decode())["ok"] is True


def test_continue_and_work_without_jar_keep_desk_alive(desk):
    cont = _post(desk.base, "/api/continue", {"id": "eidos"})
    assert cont.get("id") == "eidos"
    work = _post(desk.base, "/api/work", {"id": "eidos", "on": True})
    assert work.get("ok") is True
    with urllib.request.urlopen(desk.base + "/health") as res:
        assert json.loads(res.read().decode())["ok"] is True
    _post(desk.base, "/api/work", {"id": "eidos", "on": False})


def test_insert_requires_text_and_survives_missing_cdp(desk):
    import urllib.error

    empty = urllib.request.Request(
        desk.base + "/api/chrome",
        data=json.dumps({"id": "eidos", "action": "insert", "text": ""}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(empty)
        raise AssertionError("expected 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read().decode())
        assert body.get("error") == "text required"
    missing = urllib.request.Request(
        desk.base + "/api/chrome",
        data=json.dumps({"id": "eidos", "action": "insert", "text": "hello"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(missing)
        raise AssertionError("expected 404")
    except urllib.error.HTTPError as e:
        assert e.code == 404
    with urllib.request.urlopen(desk.base + "/health") as res:
        assert json.loads(res.read().decode())["ok"] is True


def test_test_event_hook_requires_flag_on_this_desk(desk):
    out = _post(desk.base, "/api/test/event", {"event": "login-auto", "data": {"id": "eidos", "login": "a@x"}})
    assert out.get("ok") is True


def test_ask_save_fill_queue_and_auto_lede(desk, chrome):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(desk.base + "/?id=eidos", wait_until="domcontentloaded")
        page.wait_for_selector("#rail")
        page.wait_for_timeout(400)

        _post(
            desk.base,
            "/api/test/event",
            {
                "event": "login-ask",
                "data": {
                    "id": "eidos",
                    "host": "chatgpt.com",
                    "records": [],
                    "last_login": "you@example.com",
                },
            },
        )
        page.wait_for_selector("#ask-save:not([hidden])", timeout=5000)
        assert page.locator("#ask-approve").is_hidden()
        assert page.locator("#ask-login").input_value() == "you@example.com"
        assert "Save it once" in page.locator("#ask-copy").inner_text()

        _post(
            desk.base,
            "/api/test/event",
            {
                "event": "login-ask",
                "data": {
                    "id": "eidos",
                    "host": "chatgpt.com",
                    "records": [
                        {"id": "aaa", "host": "chatgpt.com", "login": "one@x", "has_password": True},
                        {"id": "bbb", "host": "chatgpt.com", "login": "two@x", "has_password": True},
                    ],
                },
            },
        )
        page.wait_for_timeout(300)
        assert page.locator("#ask-approve").is_visible()
        assert page.locator("#ask-list li").count() == 2

        _post(
            desk.base,
            "/api/test/event",
            {"event": "login-auto", "data": {"id": "eidos", "host": "chatgpt.com", "login": "one@x"}},
        )
        page.wait_for_timeout(400)
        assert page.locator("#login-ask").is_hidden()
        assert "one@x" in page.locator("#hands-who").inner_text()

        _post(
            desk.base,
            "/api/test/event",
            {
                "event": "login-ask",
                "data": {"id": "aic", "host": "bbc.com", "records": [], "last_login": ""},
            },
        )
        page.wait_for_timeout(300)
        assert page.locator("#login-ask").is_hidden()
        page.locator("#rail button[data-id='aic']").click()
        page.wait_for_selector("#ask-save:not([hidden])", timeout=5000)
        assert "bbc.com" in page.locator("#ask-title").inner_text()
        browser.close()


def test_save_and_fill_stores_vault_without_human(desk, chrome):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.goto(desk.base + "/?id=eidos", wait_until="domcontentloaded")
        page.wait_for_selector("#rail")
        page.wait_for_timeout(400)
        _post(
            desk.base,
            "/api/test/event",
            {
                "event": "login-ask",
                "data": {"id": "eidos", "host": "chatgpt.com", "records": [], "last_login": "agent@prims.local"},
            },
        )
        page.wait_for_selector("#ask-save:not([hidden])")
        page.fill("#ask-pass", "demo-pass-not-real")
        page.click("#ask-save button[type=submit]")
        page.wait_for_function("() => document.getElementById('login-ask').hidden === true", timeout=5000)
        browser.close()
    with urllib.request.urlopen(desk.base + "/api/vault?id=eidos") as res:
        pack = json.loads(res.read().decode())
    logins = [(r.get("host"), r.get("login")) for r in pack.get("records") or []]
    assert ("chatgpt.com", "agent@prims.local") in logins
    assert all("password" not in r for r in pack["records"])


def test_chrome_replays_pending_login_ask(desk):
    _post(
        desk.base,
        "/api/test/event",
        {
            "event": "login-ask",
            "data": {"id": "eidos", "host": "chatgpt.com", "records": [], "last_login": "held@prims.local"},
        },
    )
    with urllib.request.urlopen(desk.base + "/api/chrome?id=eidos") as res:
        data = json.loads(res.read().decode())
    ask = data.get("loginAsk") or {}
    assert ask.get("id") == "eidos"
    assert ask.get("host") == "chatgpt.com"
    assert ask.get("last_login") == "held@prims.local"
    _post(desk.base, "/api/login-deny", {"id": "eidos"})
    with urllib.request.urlopen(desk.base + "/api/chrome?id=eidos") as res:
        gone = json.loads(res.read().decode())
    assert "loginAsk" not in gone


def test_ask_shows_other_vault_logins(desk, chrome):
    from playwright.sync_api import sync_playwright

    _post(
        desk.base,
        "/api/vault",
        {
            "id": "eidos",
            "host": "prims-fixture",
            "login": "you@example.com",
            "password": "demo-pass-not-real",
        },
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(desk.base + "/?id=eidos", wait_until="domcontentloaded")
        page.wait_for_selector("#rail")
        page.wait_for_timeout(400)
        _post(
            desk.base,
            "/api/test/event",
            {
                "event": "login-ask",
                "data": {"id": "eidos", "host": "chatgpt.com", "records": []},
            },
        )
        page.wait_for_selector("#login-ask:not([hidden])", timeout=5000)
        assert page.locator("#ask-approve").is_visible()
        assert page.locator("#ask-save").is_visible()
        assert page.locator("#ask-list li").count() >= 1
        assert "you@example.com" in page.locator("#ask-list").inner_text()
        assert "chatgpt.com" in page.locator("#ask-title").inner_text()
        browser.close()


def test_reload_replays_login_ask_sheet(desk, chrome):
    from playwright.sync_api import sync_playwright

    _post(
        desk.base,
        "/api/test/event",
        {
            "event": "login-ask",
            "data": {
                "id": "eidos",
                "host": "chatgpt.com",
                "records": [{"id": "aaa", "host": "chatgpt.com", "login": "held@x", "has_password": True}],
            },
        },
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(desk.base + "/?id=eidos", wait_until="domcontentloaded")
        page.wait_for_selector("#login-ask:not([hidden])", timeout=8000)
        assert "held@x" in page.locator("#ask-list").inner_text()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#login-ask:not([hidden])", timeout=8000)
        assert "held@x" in page.locator("#ask-list").inner_text()
        browser.close()
