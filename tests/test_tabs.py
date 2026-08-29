from __future__ import annotations

from lib import tabs


def test_file_login_tab_has_fixture_host_and_auth_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_TABS_LEDGER", str(tmp_path / "tabs.json"))
    pages = [
        {
            "id": "1",
            "title": "Sign in · Prims",
            "url": "file:///config/prims-fixture/login.html",
        }
    ]
    row = tabs.record("eidos", pages, "1", gated_ids=set())
    assert row["tabs"][0]["host"] == "prims-fixture"
    assert row["tabs"][0]["kind"] == "auth"
    again = tabs.snapshot("eidos")
    assert again["tabs"][0]["id"] == "1"


def test_record_keeps_work_url(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_TABS_LEDGER", str(tmp_path / "tabs.json"))
    tabs.set_work("eidos", "https://chatgpt.com/")
    pages = [{"id": "w", "title": "ChatGPT", "url": "https://chatgpt.com/uc/x"}]
    row = tabs.record("eidos", pages, "w")
    assert row["work"] == "https://chatgpt.com/"
    assert row["tabs"][0]["kind"] == "work"
