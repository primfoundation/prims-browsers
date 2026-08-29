from __future__ import annotations

import json

from lib import vault


def test_list_is_public_no_password(vault_dir):
    row = vault.add("eidos", "chatgpt.com", "you@example.com", "secret-never-list")
    assert "password" not in row
    listed = vault.list_records("eidos")
    assert len(listed) == 1
    assert listed[0]["host"] == "chatgpt.com"
    assert listed[0]["login"] == "you@example.com"
    assert listed[0]["has_password"] is True
    assert "password" not in listed[0]
    raw = json.loads((vault_dir / "eidos.json").read_text())
    assert raw["records"][0]["password"] == "secret-never-list"


def test_list_several(vault_dir):
    vault.add("eidos", "prims-fixture", "a@x", "p1")
    vault.add("eidos", "chatgpt.com", "b@x", "p2")
    vault.add("eidos", "amazon.com", "c@x", "p3")
    hosts = [r["host"] for r in vault.list_records("eidos")]
    assert hosts[0] == "amazon.com"
    assert set(hosts) == {"prims-fixture", "chatgpt.com", "amazon.com"}


def test_secret_reveal_and_soft_remove(vault_dir):
    row = vault.add("eidos", "prims-fixture", "you@example.com", "demo-pass-not-real")
    got = vault.secret("eidos", row["id"])
    assert got is not None
    assert got["password"] == "demo-pass-not-real"
    assert vault.remove("eidos", row["id"]) is True
    assert vault.list_records("eidos") == []
    assert vault.secret("eidos", row["id"]) is None
    raw = json.loads((vault_dir / "eidos.json").read_text())
    assert raw["records"][0]["deleted_at"]


def test_list_for_host(vault_dir):
    vault.add("eidos", "www.chatgpt.com", "one", "p")
    vault.add("eidos", "amazon.com", "two", "p")
    hits = vault.list_for_host("eidos", "chatgpt.com")
    assert [h["login"] for h in hits] == ["one"]


def test_last_used_is_default(vault_dir):
    a = vault.add("eidos", "chatgpt.com", "first@x", "p")
    b = vault.add("eidos", "chatgpt.com", "second@x", "p")
    vault.touch("eidos", a["id"])
    hosts = vault.list_for_host("eidos", "chatgpt.com")
    assert hosts[0]["id"] == a["id"]
    assert vault.last_username("eidos") == "first@x"
    assert "last_used_at" in hosts[0]
    assert vault.touch("eidos", "nope") is False
    assert vault.last_username("ghost") == ""
    _ = b


def test_ask_bundle_lists_other_vault_logins(vault_dir):
    vault.add("eidos", "prims-fixture", "you@example.com", "p1")
    vault.add("eidos", "test.example", "test", "p2")
    pack = vault.ask_bundle("eidos", "chatgpt.com", "https://chatgpt.com/auth/login")
    assert pack["id"] == "eidos"
    assert pack["host"] == "chatgpt.com"
    assert pack["records"] == []
    assert [r["login"] for r in pack["others"]] == ["test", "you@example.com"]
    assert all("password" not in r for r in pack["others"])
    mine = vault.add("eidos", "chatgpt.com", "me@x", "p3")
    pack = vault.ask_bundle("eidos", "chatgpt.com")
    assert [r["id"] for r in pack["records"]] == [mine["id"]]
    assert mine["id"] not in {r["id"] for r in pack["others"]}
    assert {r["login"] for r in pack["others"]} == {"test", "you@example.com"}


def test_other_tenant_isolated(vault_dir):
    vault.add("eidos", "chatgpt.com", "e", "p")
    vault.add("aic", "bbc.com", "a", "p")
    assert len(vault.list_records("eidos")) == 1
    assert vault.list_records("eidos")[0]["host"] == "chatgpt.com"
    assert vault.list_records("aic")[0]["host"] == "bbc.com"
