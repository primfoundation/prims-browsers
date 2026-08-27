"""Chrome DevTools Protocol client. Fast hands for a jar. Not eidos-browsing."""

from __future__ import annotations

import asyncio
import json
import urllib.request

import websockets


def fetch_json(url: str, timeout: float = 3.0):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode())


def pages(cdp_base: str) -> list[dict]:
    rows = fetch_json(cdp_base.rstrip("/") + "/json/list")
    out = []
    for t in rows:
        if t.get("type") != "page":
            continue
        url = t.get("url") or ""
        if url.startswith("chrome://") or url.startswith("devtools://"):
            continue
        out.append(
            {
                "id": t.get("id"),
                "title": t.get("title") or "",
                "url": url,
                "ws": t.get("webSocketDebuggerUrl"),
            }
        )
    return out


def version(cdp_base: str) -> dict:
    return fetch_json(cdp_base.rstrip("/") + "/json/version")


async def _call(ws_url: str, method: str, params: dict | None = None, timeout: float = 8.0):
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=2) as ws:
        msg_id = 1
        await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                return msg.get("result") or {}


def call(ws_url: str, method: str, params: dict | None = None) -> dict:
    return asyncio.run(_call(ws_url, method, params))


def first_page_ws(cdp_base: str, tab_id: str | None = None) -> tuple[dict, str]:
    plist = pages(cdp_base)
    if not plist:
        raise RuntimeError("no pages on this jar")
    if tab_id:
        for p in plist:
            if p["id"] == tab_id:
                if not p.get("ws"):
                    raise RuntimeError("page has no websocket")
                return p, p["ws"]
        raise RuntimeError(f"tab {tab_id} not found")
    page = plist[-1]
    if not page.get("ws"):
        raise RuntimeError("page has no websocket")
    return page, page["ws"]
