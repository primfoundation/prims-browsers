"""Chrome DevTools Protocol client. Fast hands for a jar. Not eidos-browsing."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import time
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
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=2, max_size=8_000_000) as ws:
        msg_id = 1
        await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                return msg.get("result") or {}


_LOOP_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=12, thread_name_prefix="cdp")


def _sync(coro_fn):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return coro_fn()
    return _LOOP_POOL.submit(coro_fn).result(timeout=25)


def call(ws_url: str, method: str, params: dict | None = None) -> dict:
    return _sync(lambda: asyncio.run(_call(ws_url, method, params)))


async def _call_many(ws_url: str, steps: list[tuple[str, dict | None]], timeout: float = 8.0) -> list[dict]:
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=2, max_size=8_000_000) as ws:
        out = []
        n = 1
        for method, params in steps:
            await ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if msg.get("id") == n:
                    if "error" in msg:
                        raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                    out.append(msg.get("result") or {})
                    break
            n += 1
        return out


def call_many(ws_url: str, steps: list[tuple[str, dict | None]]) -> list[dict]:
    return _sync(lambda: asyncio.run(_call_many(ws_url, steps)))


async def _navigate(ws_url: str, url: str, timeout: float = 20.0) -> dict:
    async with websockets.connect(ws_url, open_timeout=8, close_timeout=2, max_size=8_000_000) as ws:
        n = 1
        await ws.send(json.dumps({"id": n, "method": "Page.enable"}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            if msg.get("id") == n:
                break
        n = 2
        await ws.send(json.dumps({"id": n, "method": "Page.navigate", "params": {"url": url}}))
        nav = None
        loaded = False
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - asyncio.get_event_loop().time()))
            msg = json.loads(raw)
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                nav = msg.get("result") or {}
            if msg.get("method") == "Page.loadEventFired":
                loaded = True
            if nav is not None and loaded:
                return nav
        if nav is None:
            raise RuntimeError("navigate did not reply")
        return nav


def navigate(ws_url: str, url: str) -> dict:
    return _sync(lambda: asyncio.run(_navigate(ws_url, url)))


def activate(cdp_base: str, tab_id: str) -> None:
    try:
        urllib.request.urlopen(cdp_base.rstrip("/") + "/json/activate/" + tab_id, timeout=3).read()
        return
    except Exception:
        pass
    call(version(cdp_base)["webSocketDebuggerUrl"], "Target.activateTarget", {"targetId": tab_id})


def create_tab(cdp_base: str, url: str) -> dict:
    return call(version(cdp_base)["webSocketDebuggerUrl"], "Target.createTarget", {"url": url})


def is_auth_url(url: str) -> bool:
    u = (url or "").lower()
    return "/login" in u or "/signin" in u or "/auth/" in u or "authentik" in u or "sign-in" in u


def needle_hits(url: str, needle: str, allow_auth: bool = False) -> bool:
    u = url or ""
    n = (needle or "").rstrip("/")
    if not n or n not in u:
        return False
    if not allow_auth and is_auth_url(u):
        return False
    return True


def find_tab(cdp_base: str, needle: str, allow_auth: bool = False) -> dict | None:
    for p in pages(cdp_base):
        if needle_hits(p.get("url") or "", needle, allow_auth=allow_auth):
            return p
    return None


def front_tab(cdp_base: str, needle: str) -> dict:
    tab = find_tab(cdp_base, needle)
    if not tab:
        created = create_tab(cdp_base, needle)
        tid = created.get("targetId")
        for _ in range(20):
            time.sleep(0.2)
            tab = find_tab(cdp_base, needle)
            if tab:
                break
            if tid:
                for p in pages(cdp_base):
                    if p.get("id") == tid:
                        tab = p
                        break
            if tab:
                break
        if not tab:
            raise RuntimeError(f"no tab for {needle}")
    activate(cdp_base, tab["id"])
    try:
        if tab.get("ws"):
            call(tab["ws"], "Page.bringToFront")
    except Exception:
        pass
    return tab


async def _history(ws_url: str, timeout: float = 8.0) -> dict:
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=2, max_size=8_000_000) as ws:
        n = 1
        await ws.send(json.dumps({"id": n, "method": "Page.enable"}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                break
        n = 2
        await ws.send(json.dumps({"id": n, "method": "Page.getNavigationHistory"}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                return msg.get("result") or {}


def history(ws_url: str) -> dict:
    return _sync(lambda: asyncio.run(_history(ws_url)))


async def _history_go(ws_url: str, delta: int, timeout: float = 8.0) -> dict:
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=2, max_size=8_000_000) as ws:
        n = 1
        await ws.send(json.dumps({"id": n, "method": "Page.enable"}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                break
        n = 2
        await ws.send(json.dumps({"id": n, "method": "Page.getNavigationHistory"}))
        hist = None
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                hist = msg.get("result") or {}
                break
        idx = hist.get("currentIndex") or 0
        entries = hist.get("entries") or []
        target = idx + delta
        if target < 0 or target >= len(entries):
            return {"ok": False, "error": "no history", "index": idx, "n": len(entries)}
        n = 3
        await ws.send(json.dumps({
            "id": n,
            "method": "Page.navigateToHistoryEntry",
            "params": {"entryId": entries[target]["id"]},
        }))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("id") == n:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message") or str(msg["error"]))
                return {"ok": True, "index": target, "n": len(entries)}


def history_go(ws_url: str, delta: int) -> dict:
    return _sync(lambda: asyncio.run(_history_go(ws_url, delta)))


def pick_page(plist: list[dict], tab_id: str | None = None, visible_id: str | None = None) -> dict:
    """Hands follow an assigned tab, else the visible one. Never skip /login."""
    if not plist:
        raise RuntimeError("no pages on this jar")
    if tab_id:
        for p in plist:
            if p.get("id") == tab_id:
                return p
        raise RuntimeError(f"tab {tab_id} not found")
    if visible_id:
        for p in plist:
            if p.get("id") == visible_id:
                return p
    return plist[0]


def visible_page(cdp_base: str, plist: list[dict] | None = None) -> dict | None:
    rows = plist if plist is not None else pages(cdp_base)
    for p in rows:
        if not p.get("ws"):
            continue
        try:
            r = call(p["ws"], "Runtime.evaluate", {"expression": "document.visibilityState", "returnByValue": True})
            if (r or {}).get("result", {}).get("value") == "visible":
                return p
        except Exception:
            continue
    return None


def first_page_ws(cdp_base: str, tab_id: str | None = None) -> tuple[dict, str]:
    plist = pages(cdp_base)
    if not plist:
        raise RuntimeError("no pages on this jar")
    vis = None if tab_id else visible_page(cdp_base, plist)
    page = pick_page(plist, tab_id=tab_id, visible_id=(vis or {}).get("id"))
    if not page.get("ws"):
        raise RuntimeError("page has no websocket")
    return page, page["ws"]
