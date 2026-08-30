"""Credential vaults for Prims Browsers.

System vault (always on): JSON under PRIMS_VAULT_ROOT or
~/.prim/prims-browsers/vault/. People can also connect their own vault(s)
(e.g. PaseoVault) via vaults.json — lists merge; writes default to system.

Never log secrets.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

_LOCK = threading.RLock()

SYSTEM_ID = "system"
SYSTEM_KIND = "prims"
SYSTEM_LABEL = "System"


def _config_path() -> Path:
    env = os.environ.get("PRIMS_VAULTS")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".prim/prims-browsers/vaults.json"


def _system_root() -> Path:
    env = os.environ.get("PRIMS_VAULT_ROOT")
    return Path(env).expanduser() if env else Path.home() / ".prim/prims-browsers/vault"


def _expand(path: str | Path) -> Path:
    return Path(os.path.expanduser(str(path)))


def _load_config() -> dict:
    path = _config_path()
    if not path.is_file():
        return {"write": SYSTEM_ID, "connected": []}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {"write": SYSTEM_ID, "connected": []}
    if not isinstance(data, dict):
        return {"write": SYSTEM_ID, "connected": []}
    connected = data.get("connected") or []
    if not isinstance(connected, list):
        connected = []
    return {
        "write": data.get("write") or SYSTEM_ID,
        "connected": [c for c in connected if isinstance(c, dict) and c.get("id") and c.get("kind")],
    }


def _save_config(data: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _path(tid: str) -> Path:
    safe = "".join(c for c in tid if c.isalnum() or c in "-_") or "tenant"
    return _system_root() / f"{safe}.json"


def _load(tid: str) -> list[dict]:
    p = _path(tid)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text())
        rows = data.get("records") if isinstance(data, dict) else data
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _save(tid: str, rows: list[dict]) -> None:
    _system_root().mkdir(parents=True, exist_ok=True)
    p = _path(tid)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"tenant": tid, "records": rows}, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(p)
    os.chmod(p, 0o600)


def public(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "host": row.get("host"),
        "login": row.get("login"),
        "title": row.get("title") or "",
        "created_at": row.get("created_at"),
        "last_used_at": row.get("last_used_at"),
        "has_password": bool(row.get("password")),
    }


def _tag(row: dict, vault_id: str, kind: str, label: str) -> dict:
    out = dict(row)
    out["vault"] = vault_id
    out["vault_kind"] = kind
    out["vault_label"] = label
    return out


def _sort_public(rows: list[dict]) -> list[dict]:
    def key(r: dict):
        return float(r.get("last_used_at") or r.get("created_at") or 0)

    return sorted(rows, key=key, reverse=True)


class _SystemVault:
    id = SYSTEM_ID
    kind = SYSTEM_KIND
    label = SYSTEM_LABEL

    def describe(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "path": str(_system_root()),
            "builtin": True,
            "writeable": True,
        }

    def list_records(self, tid: str) -> list[dict]:
        with _LOCK:
            rows = [r for r in _load(tid) if not r.get("deleted_at")]
        return [_tag(public(r), self.id, self.kind, self.label) for r in rows]

    def add(self, tid: str, host: str, login: str, password: str) -> dict:
        host = normalize_host(host)
        login = (login or "").strip()
        if not host or not login or not password:
            raise ValueError("host, login, and password required")
        row = {
            "id": uuid.uuid4().hex[:12],
            "host": host,
            "login": login,
            "password": password,
            "created_at": time.time(),
            "last_used_at": time.time(),
            "deleted_at": None,
        }
        with _LOCK:
            rows = _load(tid)
            rows.append(row)
            _save(tid, rows)
        return _tag(public(row), self.id, self.kind, self.label)

    def patch(
        self,
        tid: str,
        rid: str,
        host: str | None = None,
        login: str | None = None,
        title: str | None = None,
    ) -> dict | None:
        """Change host/login/title only. Never returns password."""
        with _LOCK:
            rows = _load(tid)
            found = None
            for r in rows:
                if r.get("id") == rid and not r.get("deleted_at"):
                    if host is not None:
                        h = normalize_host(host)
                        if not h:
                            raise ValueError("host required")
                        r["host"] = h
                    if login is not None:
                        lg = (login or "").strip()
                        if not lg:
                            raise ValueError("login required")
                        r["login"] = lg
                    if title is not None:
                        r["title"] = (title or "").strip()
                    found = r
                    break
            if found is None:
                return None
            _save(tid, rows)
            return _tag(public(found), self.id, self.kind, self.label)

    def remove(self, tid: str, rid: str) -> bool:
        with _LOCK:
            rows = _load(tid)
            found = False
            for r in rows:
                if r.get("id") == rid and not r.get("deleted_at"):
                    r["deleted_at"] = time.time()
                    found = True
            if found:
                _save(tid, rows)
            return found

    def touch(self, tid: str, rid: str) -> bool:
        with _LOCK:
            rows = _load(tid)
            found = False
            for r in rows:
                if r.get("id") == rid and not r.get("deleted_at"):
                    r["last_used_at"] = time.time()
                    found = True
            if found:
                _save(tid, rows)
            return found

    def secret(self, tid: str, rid: str) -> dict | None:
        with _LOCK:
            for r in _load(tid):
                if r.get("id") == rid and not r.get("deleted_at"):
                    return {
                        "id": r["id"],
                        "host": r.get("host"),
                        "login": r.get("login"),
                        "password": r.get("password"),
                        "vault": self.id,
                    }
        return None


class _PaseoVault:
    kind = "paseo-vault"

    def __init__(self, vault_id: str, root: Path, label: str | None = None):
        self.id = vault_id
        self.root = root
        self.label = label or vault_id

    def describe(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "path": str(self.root),
            "builtin": False,
            "writeable": True,
        }

    def _call(self, name: str, *args):
        from lib import paseo_vault

        return getattr(paseo_vault, name)(*args, root=self.root)

    def list_records(self, tid: str) -> list[dict]:
        rows = self._call("list_records", tid)
        return [_tag(r, self.id, self.kind, self.label) for r in rows]

    def add(self, tid: str, host: str, login: str, password: str) -> dict:
        row = self._call("add", tid, host, login, password)
        return _tag(row, self.id, self.kind, self.label)

    def remove(self, tid: str, rid: str) -> bool:
        return bool(self._call("remove", tid, rid))

    def touch(self, tid: str, rid: str) -> bool:
        return bool(self._call("touch", tid, rid))

    def secret(self, tid: str, rid: str) -> dict | None:
        got = self._call("secret", tid, rid)
        if not got:
            return None
        got = dict(got)
        got["vault"] = self.id
        return got


def _connected_backends() -> list:
    cfg = _load_config()
    out = []
    seen = set()
    for row in cfg["connected"]:
        if row.get("enabled") is False:
            continue
        vid = str(row["id"])
        if vid == SYSTEM_ID or vid in seen:
            continue
        kind = row.get("kind")
        if kind == "paseo-vault":
            path = row.get("path")
            if not path:
                continue
            out.append(_PaseoVault(vid, _expand(path), row.get("label")))
            seen.add(vid)
    # Legacy env: connect Paseo without vaults.json, never replaces system.
    env = os.environ.get("PASEO_VAULT_DIR")
    if env and "paseo" not in seen and SYSTEM_ID != "paseo":
        out.append(_PaseoVault("paseo", _expand(env), "Paseo"))
    return out


def backends() -> list:
    """System first, then connected vaults."""
    return [_SystemVault(), *_connected_backends()]


def write_target() -> str:
    env = os.environ.get("PRIMS_VAULT_WRITE")
    if env:
        return env.strip()
    return str(_load_config().get("write") or SYSTEM_ID)


def describe_vaults() -> dict:
    rows = [b.describe() for b in backends()]
    return {
        "write": write_target(),
        "system": next(r for r in rows if r["id"] == SYSTEM_ID),
        "vaults": rows,
        "config": str(_config_path()),
    }


def connect(kind: str, path: str, vault_id: str | None = None, label: str | None = None) -> dict:
    """Register a connected vault. System stays; this is additive."""
    kind = (kind or "").strip()
    if kind != "paseo-vault":
        raise ValueError("supported kinds: paseo-vault")
    root = _expand(path)
    if not root:
        raise ValueError("path required")
    vid = (vault_id or kind.split("-")[0] or "connected").strip()
    if vid == SYSTEM_ID:
        raise ValueError("id 'system' is reserved for the built-in vault")
    cfg = _load_config()
    connected = [c for c in cfg["connected"] if c.get("id") != vid]
    entry = {"id": vid, "kind": kind, "path": str(root), "label": label or vid, "enabled": True}
    connected.append(entry)
    cfg["connected"] = connected
    _save_config(cfg)
    return entry


def disconnect(vault_id: str) -> bool:
    vid = (vault_id or "").strip()
    if not vid or vid == SYSTEM_ID:
        return False
    cfg = _load_config()
    before = len(cfg["connected"])
    cfg["connected"] = [c for c in cfg["connected"] if c.get("id") != vid]
    if len(cfg["connected"]) == before:
        return False
    if cfg.get("write") == vid:
        cfg["write"] = SYSTEM_ID
    _save_config(cfg)
    return True


def set_write(vault_id: str) -> str:
    vid = (vault_id or "").strip() or SYSTEM_ID
    ids = {b.id for b in backends()}
    if vid not in ids:
        raise ValueError(f"unknown vault {vid}")
    cfg = _load_config()
    cfg["write"] = vid
    _save_config(cfg)
    return vid


def _backend(vault_id: str | None):
    vid = vault_id or write_target()
    for b in backends():
        if b.id == vid:
            return b
    raise ValueError(f"unknown vault {vid}")


def list_records(tid: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for b in backends():
        for r in b.list_records(tid):
            rid = r.get("id")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            rows.append(r)
    return _sort_public(rows)


def normalize_host(host: str) -> str:
    return (host or "").strip().lower().removeprefix("www.")


def page_host(href: str) -> str:
    p = urllib.parse.urlparse(href or "")
    path = p.path or href or ""
    host = normalize_host(p.hostname or "")
    local = host in {"", "127.0.0.1", "localhost", "host.docker.internal"}
    if local and ("prims-fixture" in path or "/fixture/login" in path or path.endswith("/login.html")):
        return "prims-fixture"
    return host


def list_for_host(tid: str, host: str) -> list[dict]:
    host = normalize_host(host)
    if not host:
        return []
    return [r for r in list_records(tid) if normalize_host(r.get("host") or "") == host]


def add(tid: str, host: str, login: str, password: str, vault_id: str | None = None) -> dict:
    return _backend(vault_id).add(tid, host, login, password)


def patch_record(
    tid: str,
    rid: str,
    host: str | None = None,
    login: str | None = None,
    title: str | None = None,
    vault_id: str | None = None,
) -> dict | None:
    """Rename metadata. Password is not accepted and not returned."""
    if host is None and login is None and title is None:
        raise ValueError("host, login, or title required")
    if vault_id:
        b = _backend(vault_id)
        fn = getattr(b, "patch", None)
        if not fn:
            raise ValueError(f"vault {vault_id} cannot patch metadata")
        return fn(tid, rid, host=host, login=login, title=title)
    for b in backends():
        fn = getattr(b, "patch", None)
        if not fn:
            continue
        got = fn(tid, rid, host=host, login=login, title=title)
        if got:
            return got
    return None


def remove(tid: str, rid: str, vault_id: str | None = None) -> bool:
    if vault_id:
        return _backend(vault_id).remove(tid, rid)
    for b in backends():
        if b.remove(tid, rid):
            return True
    return False


def touch(tid: str, rid: str, vault_id: str | None = None) -> bool:
    if vault_id:
        return _backend(vault_id).touch(tid, rid)
    for b in backends():
        if b.touch(tid, rid):
            return True
    return False


def last_username(tid: str) -> str:
    rows = list_records(tid)
    return (rows[0].get("login") or "") if rows else ""


def ask_bundle(tid: str, host: str, href: str = "") -> dict:
    recs = list_for_host(tid, host) if host else []
    ids = {r.get("id") for r in recs}
    others = [r for r in list_records(tid) if r.get("id") not in ids]
    return {
        "id": tid,
        "host": host,
        "href": href,
        "reason": "login",
        "records": recs,
        "others": others,
        "last_login": last_username(tid),
        "vaults": describe_vaults()["vaults"],
        "write": write_target(),
    }


def secret(tid: str, rid: str, vault_id: str | None = None) -> dict | None:
    """Return login+password for fill. Caller must not log it."""
    if vault_id:
        return _backend(vault_id).secret(tid, rid)
    for b in backends():
        got = b.secret(tid, rid)
        if got:
            return got
    return None
