"""Append-only action log so Continue / gates can be diagnosed."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()


def _path() -> Path:
    env = os.environ.get("PRIMS_ACTLOG")
    return Path(env) if env else Path.home() / ".prim/prims-browsers/actions.jsonl"


def add(kind: str, **fields) -> None:
    rec = {"ts": time.time(), "kind": kind, **fields}
    line = json.dumps(rec, default=str)
    path = _path()
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(line + "\n")
    if os.environ.get("PRIMS_ACTLOG_QUIET"):
        return
    print("actlog", line, flush=True)
