"""PaseoVault as a *connected* vault — system vault stays. Never logs secrets."""

from __future__ import annotations

import json

from lib import vault


def test_paseo_backend_roundtrip(tmp_path, monkeypatch):
    d = tmp_path / "paseo-vault"
    monkeypatch.setenv("PASEO_VAULT_DIR", str(d))
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(tmp_path / "system-vault"))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    (tmp_path / "system-vault").mkdir()

    row = vault.add("gmw", "www.yahoo.com", "you@example.com", "prove-not-real", vault_id="paseo")
    listed = vault.list_records("gmw")
    match = next(r for r in listed if r["id"] == row["id"])
    assert match["host"] == "yahoo.com"
    assert match["login"] == "you@example.com"
    assert match["vault"] == "paseo"
    assert "password" not in match
    assert match["has_password"] is True

    got = vault.secret("gmw", row["id"])
    assert got is not None
    assert got["password"] == "prove-not-real"
    assert got["host"] == "yahoo.com"
    assert got["vault"] == "paseo"

    raw = (d / "vault.enc").read_text()
    assert "prove-not-real" not in raw
    assert "yahoo.com" not in raw
    envelope = json.loads(raw)
    assert envelope["version"] == 1
    assert envelope["kdf"] == "scrypt"
    assert envelope["cipher"] == "aes-256-gcm"

    assert vault.touch("gmw", row["id"]) is True
    assert vault.remove("gmw", row["id"]) is True
    assert not any(r["id"] == row["id"] for r in vault.list_records("gmw"))
    assert vault.secret("gmw", row["id"]) is None
    assert (d / "key").stat().st_mode & 0o777 == 0o660


def test_json_backend_unchanged(vault_dir):
    row = vault.add("eidos", "chatgpt.com", "a@x", "secret-never-list")
    listed = vault.list_records("eidos")
    assert listed[0]["vault"] == "system"
    assert "password" not in listed[0]
    raw = json.loads((vault_dir / "eidos.json").read_text())
    assert "secret-never-list" in json.dumps(raw)
    assert vault.secret("eidos", row["id"])["password"] == "secret-never-list"
