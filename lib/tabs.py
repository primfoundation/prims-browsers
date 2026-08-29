"""Per-tenant tab ledger. Identity + role, updated from CDP target events."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from pathlib import Path

_LOCK = threading.RLock()


def _ledger() -> Path:
    env = os.environ.get("PRIMS_TABS_LEDGER")
    return Path(env) if env else Path.home() / ".prim/prims-browsers/tabs.json"


def _host(url: str) -> str:
    from lib import vault as vault_lib

    return vault_lib.page_host(url)


def _title(raw: str, host: str) -> str:
    t = (raw or "").replace("&amp;", "&").strip()
    for junk in (" - Chromium", " - Google Chrome", " | Greenmark Waste Solutions"):
        if t.endswith(junk):
            t = t[: -len(junk)].strip()
    if t.lower() in ("", "new tab", "untitled"):
        return host or "tab"
    return t[:48]


def classify(url: str, gated: bool, work_url: str | None) -> str:
    u = url or ""
    if gated:
        return "gate"
    if "/login" in u or "authentik" in u or "/signin" in u or "/auth/" in u:
        return "auth"
    if work_url and work_url.rstrip("/") in u.rstrip("/"):
        return "work"
    return "other"


def load() -> dict:
    with _LOCK:
        p = _ledger()
        if not p.is_file():
            return {}
        try:
            data = json.loads(p.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def save(data: dict) -> None:
    with _LOCK:
        p = _ledger()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)


def snapshot(tid: str) -> dict:
    data = load()
    row = data.get(tid) or {"id": tid, "work": None, "front": None, "tabs": []}
    return row


def set_work(tid: str, url: str | None) -> dict:
    with _LOCK:
        p = _ledger()
        if p.is_file():
            try:
                data = json.loads(p.read_text())
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
        else:
            data = {}
        row = data.get(tid) or {"id": tid, "work": None, "front": None, "tabs": []}
        row["work"] = url
        data[tid] = row
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(p)
        return row


def record(tid: str, pages: list[dict], front_id: str | None, gated_ids: set[str] | None = None) -> dict:
    gated_ids = gated_ids or set()
    with _LOCK:
        pth = _ledger()
        if pth.is_file():
            try:
                data = json.loads(pth.read_text())
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
        else:
            data = {}
        row = data.get(tid) or {"id": tid, "work": None, "front": None, "tabs": []}
        work = row.get("work")
        now = time.time()
        tabs = []
        for p in pages:
            url = p.get("url") or ""
            host = _host(url)
            kind = classify(url, p.get("id") in gated_ids, work)
            tabs.append(
                {
                    "id": p.get("id"),
                    "title": _title(p.get("title") or "", host),
                    "host": host,
                    "url": url,
                    "kind": kind,
                    "front": p.get("id") == front_id,
                    "seen": now,
                }
            )
        row["tabs"] = tabs
        row["front"] = front_id
        row["updated"] = now
        data[tid] = row
        pth.parent.mkdir(parents=True, exist_ok=True)
        tmp = pth.with_name(f".{pth.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(pth)
        return row
