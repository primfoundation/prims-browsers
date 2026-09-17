"""Regression coverage for redirected work tabs and human takeover."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import threading
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parent.parent
WORK = "https://work.example/"
PAGE = {"id": "owned", "ws": "ws://owned", "url": WORK, "title": "Work"}


def load_desk():
    loader = SourceFileLoader("control_test_desk", str(ROOT / "bin/prims-browsers"))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_TABS_LEDGER", str(tmp_path / "tabs.json"))
    module = load_desk()
    row = {"id": "eidos", "work": WORK, "glass": {"cdp": "http://jar"}}
    monkeypatch.setattr(module, "load_doc", lambda: {"tenants": [row]})
    monkeypatch.setattr(module, "front_host", lambda _: "work.example")
    monkeypatch.setattr(module.cdp_lib, "activate", Mock())
    monkeypatch.setattr(module.cdp_lib, "call", Mock())
    monkeypatch.setattr(module.cdp_lib, "create_tab", Mock(return_value={"targetId": "owned"}))
    return module


class FastStop(threading.Event):
    def wait(self, timeout=None):
        return super().wait(min(timeout or 0.01, 0.01))


def test_redirects_keep_one_target_without_demo_actions(app, monkeypatch):
    stop = FastStop()
    urls = ["https://sso.example/login", "https://login.microsoftonline.com/authorize", WORK]
    observed = []
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [] if not app.cdp_lib.create_tab.called else [
        {**PAGE, "url": urls[min(len(observed), 2)]}
    ])

    def inspect(page):
        observed.append(page)
        if len(observed) == 4:
            stop.set()
        # The original bug reproduced even when the SPA login gate was not detected.
        return {"gated": False}

    monkeypatch.setattr(app.gate_lib, "inspect_page", inspect)
    monkeypatch.setattr(app, "emit_tabs", lambda *_: None)
    app.work_loop("eidos", WORK, stop)
    assert {p["id"] for p in observed} == {"owned"}
    assert len({p["url"] for p in observed}) == 3
    app.cdp_lib.create_tab.assert_called_once()
    app.cdp_lib.activate.assert_called_once_with("http://jar", "owned")
    app.cdp_lib.call.assert_not_called()  # No arbitrary links, messages, or repeat focus.
    assert app.tabs_lib.snapshot("eidos")["work_tab"] == "owned"


def test_closed_work_tab_stops_instead_of_reopening(app, monkeypatch):
    pages = iter([[PAGE], [PAGE], []])
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: next(pages))
    monkeypatch.setattr(app.gate_lib, "inspect_page", lambda _: {"gated": False})
    monkeypatch.setattr(app, "emit_tabs", lambda *_: None)
    app.work_loop("eidos", WORK, FastStop())
    app.cdp_lib.create_tab.assert_not_called()
    assert app.tabs_lib.snapshot("eidos")["work_tab"] is None


def test_uncertain_creation_is_not_retried(app, monkeypatch):
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [])
    app.cdp_lib.create_tab.side_effect = TimeoutError("response lost")
    app.work_loop("eidos", WORK, FastStop())
    app.cdp_lib.create_tab.assert_called_once()
    app.cdp_lib.activate.assert_not_called()


def test_saved_target_survives_desk_restart_and_auth_redirect(app, monkeypatch):
    app.tabs_lib.set_work("eidos", WORK, tab_id="owned")
    stop = FastStop()
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [{**PAGE, "url": "https://sso.example/login"}])
    monkeypatch.setattr(app.gate_lib, "inspect_page", lambda _: (stop.set() or {"gated": True, "reason": "login"}))
    app.work_loop("eidos", WORK, stop)
    app.cdp_lib.create_tab.assert_not_called()
    app.cdp_lib.activate.assert_called_once_with("http://jar", "owned")


def test_takeover_cancels_worker_waiting_for_login(app, monkeypatch):
    entered = threading.Event()
    stop = threading.Event()
    app._WORK["eidos"] = {"url": WORK, "stop": stop}
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [PAGE])
    monkeypatch.setattr(app.gate_lib, "inspect_page", lambda _: (entered.set() or {"gated": True, "reason": "login"}))
    monkeypatch.setattr(app, "emit_tabs", lambda *_: None)
    worker = threading.Thread(target=app.work_loop, args=("eidos", WORK, stop))
    worker.start()
    try:
        assert entered.wait(2)
        app.take_over("eidos")
        worker.join(1)
        assert not worker.is_alive()
        assert stop.is_set()
        assert app.human_control("eidos")
        assert "eidos" not in app._WORK
    finally:
        stop.set()
        worker.join(2)


def test_takeover_cancels_login_agent_during_mfa(app, monkeypatch):
    entered = threading.Event()
    stop = threading.Event()
    app._LOGIN["eidos"] = {"stop": stop}
    monkeypatch.setattr(app.vault_lib, "secret", lambda *_: {"login": "fixture", "password": "fixture", "host": "work.example"})
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [PAGE])
    monkeypatch.setattr(app.gate_lib, "inspect_front", lambda _: {"tab": "owned"})
    monkeypatch.setattr(app.gate_lib, "inspect_page", lambda _: (entered.set() or {"gated": True, "reason": "2fa"}))
    monkeypatch.setattr(app.login_lib, "bring_login_front", Mock())
    monkeypatch.setattr(app.login_lib, "dismiss_prompts", lambda _: {})
    monkeypatch.setattr(app.login_lib, "inspect_form", lambda _: {"step": "2fa"})
    act = Mock(return_value={"action": "wait-2fa"})
    monkeypatch.setattr(app.login_lib, "act", act)
    worker = threading.Thread(target=app.login_agent, args=("eidos", "fixture", stop))
    worker.start()
    try:
        assert entered.wait(2)
        app.take_over("eidos")
        app.continue_human("eidos")
        worker.join(1)
        assert not worker.is_alive()
        act.assert_called_once()
        assert app.human_control("eidos")
    finally:
        stop.set()
        worker.join(2)


def test_takeover_waits_for_inflight_action_before_acknowledging(app):
    entered, release, acknowledged = (threading.Event() for _ in range(3))
    stop = threading.Event()
    app._WORK["eidos"] = {"url": WORK, "stop": stop}

    def action():
        with app.hands_lock("eidos"):
            entered.set()
            release.wait(2)

    worker = threading.Thread(target=action)
    takeover = threading.Thread(target=lambda: (app.take_over("eidos"), acknowledged.set()))
    worker.start()
    try:
        assert entered.wait(1)
        takeover.start()
        assert stop.wait(1)
        assert not acknowledged.is_set()
        release.set()
        takeover.join(1)
        assert acknowledged.is_set()
    finally:
        release.set()
        worker.join(2)
        if takeover.ident:
            takeover.join(2)


@pytest.mark.parametrize("human", [False, True])
def test_continue_never_navigates_or_clears_real_login_gate(app, human):
    app.tabs_lib.set_work("eidos", WORK, tab_id="owned")
    app.tabs_lib.set_human("eidos", human)
    app.set_gate("eidos", True, "login")
    result = app.continue_human("eidos")
    assert result["human"] is human
    assert app.gate_view("eidos")["gated"] is True
    app.cdp_lib.create_tab.assert_not_called()
    app.cdp_lib.activate.assert_not_called()
    app.cdp_lib.call.assert_not_called()


def test_watcher_and_restart_do_not_undo_takeover(app, monkeypatch):
    app.take_over("eidos")
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [PAGE])
    monkeypatch.setattr(app.gate_lib, "inspect_front", lambda _: {"tab": "owned", "gated": True, "reason": "login"})
    bundle = Mock(side_effect=AssertionError("must not start automatic login"))
    monkeypatch.setattr(app.vault_lib, "ask_bundle", bundle)
    app.emit_tabs("eidos", "http://jar")
    assert load_desk().human_control("eidos")
    assert app.start_login("eidos", "fixture")["human"] is True
    app.set_gate("eidos", False)
    assert app.steer_view("eidos")["on"] is False
    monkeypatch.setenv("PRIMS_BROWSERS_AUTOWORK", "1")
    monkeypatch.delenv("PRIMS_BROWSERS_NO_WATCH", raising=False)
    monkeypatch.setattr(app.threading, "Thread", Mock())
    monkeypatch.setattr(app.chrome_prefs, "quiet_profile", lambda _: None)
    start = Mock(side_effect=AssertionError("takeover must survive autowork"))
    monkeypatch.setattr(app, "start_work", start)
    app.start_watchers()
    start.assert_not_called()


def test_explicit_work_resumes_and_repeated_work_is_idempotent(app, monkeypatch):
    app.take_over("eidos")
    thread = Mock()
    monkeypatch.setattr(app.threading, "Thread", thread)
    app.start_work("eidos", WORK)
    app.start_work("eidos", WORK)
    assert not app.human_control("eidos")
    assert thread.call_count == 1
    app.stop_work("eidos")


def test_explicit_login_can_resume_after_takeover(app, monkeypatch):
    app.take_over("eidos")
    start = Mock(return_value={"ok": True})
    monkeypatch.setattr(app, "_start_login", start)
    assert app.start_login("eidos", "fixture", explicit=True)["ok"]
    assert not app.human_control("eidos")
    start.assert_called_once_with("eidos", "fixture")


def test_gate_inspection_does_not_click_consent(app, monkeypatch):
    monkeypatch.setattr(app.gate_lib, "inspect", lambda _: {"reason": "consent", "gated": False})
    click = Mock()
    monkeypatch.setattr(app.gate_lib, "click_consent", click)
    app.gate_lib.inspect_page(PAGE)
    click.assert_not_called()


def test_idle_watcher_asks_before_filling_saved_credentials(app, monkeypatch):
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [PAGE])
    monkeypatch.setattr(app.gate_lib, "inspect_front", lambda _: {"tab": "owned", "href": WORK, "gated": True, "reason": "login"})
    monkeypatch.setattr(app.vault_lib, "ask_bundle", lambda *_: {"records": [{"id": "fixture", "has_password": True}]})
    monkeypatch.setattr(app.login_lib, "next_login", lambda *_: ("auto", "fixture"))
    start = Mock()
    monkeypatch.setattr(app, "start_login", start)
    app.emit_tabs("eidos", "http://jar")
    start.assert_not_called()
    assert app.ask_get("eidos", "work.example") == "pending"


def test_wait_does_not_accept_continue_as_login_success(app, monkeypatch):
    app.set_gate("eidos", False)
    monkeypatch.setattr(app.cdp_lib, "pages", lambda _: [PAGE])
    monkeypatch.setattr(app.gate_lib, "inspect_page", lambda _: {"gated": True, "reason": "login"})
    assert app.wait_until_ungated("eidos", "http://jar", PAGE, timeout=0.03, stop=FastStop()) is False


def test_work_target_changes_only_for_a_new_work_url(app):
    app.tabs_lib.set_work("eidos", WORK, tab_id="owned")
    app.tabs_lib.record("eidos", [{**PAGE, "url": "https://sso.example/login"}], "owned")
    assert app.tabs_lib.set_work("eidos", WORK)["work_tab"] == "owned"
    assert app.tabs_lib.set_work("eidos", "https://another.example/").get("work_tab") is None
