"""Push CDP target changes (tabs created/closed/renamed) to a callback. Not a poll."""

from __future__ import annotations

import asyncio
import json
import time

import websockets

from lib import cdp as cdp_lib

WATCH_METHODS = {
    "Target.targetCreated",
    "Target.targetDestroyed",
    "Target.targetInfoChanged",
    "Target.detachedFromTarget",
}


async def _watch(cdp_base: str, on_change) -> None:
    ver = cdp_lib.version(cdp_base)
    ws_url = ver.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("no browser websocket")
    async with websockets.connect(ws_url, open_timeout=8, close_timeout=2) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}}))
        on_change("hello", {})
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            method = msg.get("method") or ""
            if method in WATCH_METHODS:
                info = (msg.get("params") or {}).get("targetInfo") or {}
                t = info.get("type") or ""
                if t and t not in ("page", ""):
                    continue
                on_change(method, msg.get("params") or {})


def watch_forever(cdp_base: str, on_change) -> None:
    while True:
        try:
            asyncio.run(_watch(cdp_base, on_change))
        except Exception:
            time.sleep(1.5)
