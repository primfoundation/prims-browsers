"""System vault always on; connected Paseo (and future) vaults merge in."""

from __future__ import annotations

import json

from lib import vault


def test_system_vault_tagged(vault_dir):
    row = vault.add("eidos", "chatgpt.com", "a@x", "secret")
    assert row["vault"] == "system"
    assert row["vault_kind"] == "prims"
    listed = vault.list_records("eidos")
    assert listed[0]["vault"] == "system"
    assert vault.describe_vaults()["system"]["builtin"] is True
    assert vault.write_target() == "system"


def test_connect_paseo_merges_with_system(tmp_path, monkeypatch):
    sys_root = tmp_path / "system"
    paseo_root = tmp_path / "paseo"
    sys_root.mkdir()
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(sys_root))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    monkeypatch.delenv("PASEO_VAULT_DIR", raising=False)

    vault.add("t", "example.com", "sys@x", "s1", vault_id="system")
    vault.connect("paseo-vault", str(paseo_root), vault_id="paseo", label="Paseo")
    vault.add("t", "example.com", "paseo@x", "s2", vault_id="paseo")

    listed = vault.list_records("t")
    logins = {r["login"]: r["vault"] for r in listed}
    assert logins["sys@x"] == "system"
    assert logins["paseo@x"] == "paseo"
    desc = vault.describe_vaults()
    assert {v["id"] for v in desc["vaults"]} == {"system", "paseo"}

    got = vault.secret("t", [r["id"] for r in listed if r["login"] == "paseo@x"][0])
    assert got["password"] == "s2"
    assert got["vault"] == "paseo"


def test_env_paseo_does_not_replace_system(tmp_path, monkeypatch):
    sys_root = tmp_path / "system"
    paseo_root = tmp_path / "paseo-env"
    sys_root.mkdir()
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(sys_root))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "empty-vaults.json"))
    monkeypatch.setenv("PASEO_VAULT_DIR", str(paseo_root))

    vault.add("t", "a.com", "sys@x", "s1")  # default write = system
    vault.add("t", "b.com", "paseo@x", "s2", vault_id="paseo")
    ids = {r["vault"] for r in vault.list_records("t")}
    assert ids == {"system", "paseo"}


def test_disconnect_and_write_target(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(tmp_path / "system"))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    monkeypatch.delenv("PASEO_VAULT_DIR", raising=False)
    (tmp_path / "system").mkdir()
    vault.connect("paseo-vault", str(tmp_path / "p"), vault_id="paseo")
    assert vault.set_write("paseo") == "paseo"
    assert vault.write_target() == "paseo"
    assert vault.disconnect("paseo") is True
    assert vault.write_target() == "system"
    raw = json.loads((tmp_path / "vaults.json").read_text())
    assert raw["connected"] == []
