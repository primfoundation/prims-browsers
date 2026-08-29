from __future__ import annotations

import json
from pathlib import Path

from lib import cdp
from lib import chrome_prefs
from lib import login
from lib import vault

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def test_rank_login_prefers_real_host_over_fixture():
    fixture = login.rank_login_candidate("file:///config/prims-fixture/login.html", "2fa", visible=True, prefer_host="chatgpt.com")
    real = login.rank_login_candidate("https://chatgpt.com/auth/login", "username", visible=False, prefer_host="chatgpt.com")
    assert real > fixture
    demo = login.rank_login_candidate("file:///config/prims-fixture/login.html", "username", visible=True, prefer_host="prims-fixture")
    assert demo > 0


def test_work_needle_skips_auth_urls():
    assert cdp.needle_hits("https://chatgpt.com/uc/abc", "https://chatgpt.com/") is True
    assert cdp.needle_hits("https://chatgpt.com/auth/login", "https://chatgpt.com/") is False
    assert cdp.needle_hits("https://chatgpt.com/auth/login", "https://chatgpt.com/", allow_auth=True) is True
    assert cdp.is_auth_url("https://chatgpt.com/auth/login") is True


def test_pick_page_does_not_skip_login():
    login_tab = {"id": "L", "url": "https://chatgpt.com/auth/login", "ws": "ws://l"}
    work = {"id": "W", "url": "https://chatgpt.com/", "ws": "ws://w"}
    pages = [login_tab, work]
    assert cdp.pick_page(pages, tab_id="L")["id"] == "L"
    assert cdp.pick_page(pages, visible_id="L")["id"] == "L"
    assert cdp.pick_page(pages, visible_id="W")["id"] == "W"
    assert cdp.pick_page(pages)["id"] == "L"


def test_quiet_chromium_prefs(tmp_path):
    default = tmp_path / "Default"
    default.mkdir()
    prefs = default / "Preferences"
    prefs.write_text("{}")
    (tmp_path / "Local State").write_text("{}")
    assert chrome_prefs.quiet_profile(tmp_path) is True
    data = json.loads(prefs.read_text())
    assert data["credentials_enable_service"] is False
    assert data["profile"]["password_manager_enabled"] is False
    state = json.loads((tmp_path / "Local State").read_text())
    assert "PasswordManagerOnboardingDisabled" in state["browser"]["enabled_labs_experiments"]
    assert chrome_prefs.quiet_profile(tmp_path / "missing") is False
    bad = tmp_path / "bad"
    (bad / "Default").mkdir(parents=True)
    (bad / "Default" / "Preferences").write_text("{not json")
    assert chrome_prefs.quiet_profile(bad) is False


def test_page_host_www_and_fixture():
    assert vault.page_host("https://www.chatgpt.com/auth/login") == "chatgpt.com"
    assert vault.page_host("file:///config/prims-fixture/login.html") == "prims-fixture"
    assert vault.page_host("http://127.0.0.1:7751/fixture/login") == "prims-fixture"
    assert vault.list_for_host("nobody", "") == []


def test_should_ask_once():
    assert login.should_ask(None) is True
    assert login.should_ask("pending") is False
    assert login.should_ask("approved") is False
    assert login.should_ask("denied") is False


def test_decide_login_auto_only_when_one_password():
    assert login.decide_login(True, [{"id": "a", "has_password": True}]) == ("skip", None)
    assert login.decide_login(False, []) == ("ask", None)
    assert login.decide_login(False, [{"id": "a", "has_password": False}]) == ("ask", None)
    assert login.decide_login(False, [{"id": "a", "has_password": True}]) == ("auto", "a")
    assert login.decide_login(
        False,
        [{"id": "a", "has_password": True}, {"id": "b", "has_password": True}],
    ) == ("ask", None)
    assert login.decide_login(
        False,
        [{"id": "a", "has_password": False}, {"id": "b", "has_password": True}],
    ) == ("auto", "b")


def test_next_login_respects_ask_state():
    one = [{"id": "a", "has_password": True}]
    assert login.next_login(False, None, one) == ("auto", "a")
    assert login.next_login(False, None, []) == ("ask", None)
    assert login.next_login(True, None, one) == ("skip", None)
    assert login.next_login(False, "pending", one) == ("skip", None)
    assert login.next_login(False, "approved", one) == ("skip", None)
    assert login.next_login(False, "denied", one) == ("skip", None)


def test_gate_js_ignores_article_copy(chrome, tmp_path):
    from playwright.sync_api import sync_playwright

    from lib import gate

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto((FIX / "article-mentions-captcha.html").as_uri())
        hit = page.evaluate(gate.DETECT_JS)
        browser.close()
    assert hit["reason"] is None
    assert hit["gated"] is False


def test_gate_js_consent_and_login(chrome):
    from playwright.sync_api import sync_playwright

    from lib import gate

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.goto((FIX / "consent.html").as_uri())
        consent = page.evaluate(gate.DETECT_JS)
        page.goto((FIX / "login.html").as_uri())
        signin = page.evaluate(gate.DETECT_JS)
        browser.close()
    assert consent["reason"] == "consent"
    assert "consent" in consent["hits"]
    assert gate.is_hard("consent") is False
    assert signin["reason"] == "login"
    assert gate.is_hard("login") is True
