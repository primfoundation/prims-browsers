"""Isolated vault/actlog. Never touch ~/.prim/prims-browsers/vault."""

from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

os.environ["PRIMS_ACTLOG_QUIET"] = "1"
os.environ.setdefault("PRIMS_VAULT_ROOT", tempfile.mkdtemp(prefix="prims-vault-test-"))
os.environ.setdefault("PRIMS_VAULTS", str(Path(tempfile.mkdtemp(prefix="prims-vaults-")) / "vaults.json"))
os.environ.setdefault("PRIMS_ACTLOG", str(Path(tempfile.mkdtemp(prefix="prims-actlog-")) / "actions.jsonl"))
os.environ.setdefault("PRIMS_TABS_LEDGER", str(Path(tempfile.mkdtemp(prefix="prims-tabs-")) / "tabs.json"))
os.environ.pop("PASEO_VAULT_DIR", None)
os.environ.pop("PRIMS_VAULT_WRITE", None)


def chrome_path() -> Path | None:
    p = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return p if p.is_file() else None


@pytest.fixture
def vault_dir(tmp_path, monkeypatch):
    d = tmp_path / "vault"
    d.mkdir()
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(d))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    monkeypatch.delenv("PASEO_VAULT_DIR", raising=False)
    monkeypatch.delenv("PRIMS_VAULT_WRITE", raising=False)
    return d


@pytest.fixture
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def chrome():
    p = chrome_path()
    if not p:
        pytest.skip("Google Chrome not installed")
    return p


@pytest.fixture
def desk(tmp_path, free_port, monkeypatch):
    import json
    import subprocess
    import sys
    import time
    import urllib.request
    from types import SimpleNamespace

    root = Path(__file__).resolve().parent.parent
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.setenv("PRIMS_VAULT_ROOT", str(vault_root))
    monkeypatch.setenv("PRIMS_VAULTS", str(tmp_path / "vaults.json"))
    tenants = tmp_path / "tenants.json"
    tenants.write_text(
        json.dumps(
            {
                "source": "file",
                "tenants": [
                    {"id": "eidos", "label": "Eidos", "work": "https://chatgpt.com/"},
                    {"id": "aic", "label": "AIC", "work": "https://www.bbc.com/news"},
                ],
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
        "PRIMS_BROWSERS_TEST": "1",
    }
    log = (tmp_path / "desk.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, str(root / "bin" / "prims-browsers"), "serve"],
        cwd=str(root),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{free_port}"
    deadline = time.time() + 8
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=0.4) as res:
                if res.status == 200:
                    break
        except Exception as e:
            last = e
        time.sleep(0.1)
    else:
        proc.terminate()
        raise AssertionError(f"desk did not come up: {last}")
    try:
        yield SimpleNamespace(base=base, port=free_port, vault_root=vault_root, tmp=tmp_path)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except Exception:
            proc.kill()
