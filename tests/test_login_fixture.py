"""Username page → remembered username on password page → 2FA wait. Real CDP + fixture."""

from __future__ import annotations

import http.server
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "web" / "fixture"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _bind() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(directory: Path, port: int) -> socketserver.TCPServer:
    class Handler(_Quiet):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_username_then_password_then_2fa(tmp_path, chrome):
    from lib import cdp as cdp_lib
    from lib import login as login_lib

    http_port = _bind()
    dbg = _bind()
    httpd = _serve(FIXTURE, http_port)
    profile = tmp_path / "chrome"
    profile.mkdir()
    proc = subprocess.Popen(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-search-engine-choice-screen",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={dbg}",
            "--remote-allow-origins=*",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    cdp = f"http://127.0.0.1:{dbg}"
    try:
        deadline = time.time() + 12
        ver = None
        while time.time() < deadline:
            try:
                ver = cdp_lib.version(cdp)
                if ver.get("webSocketDebuggerUrl"):
                    break
            except Exception:
                time.sleep(0.15)
        assert ver and ver.get("webSocketDebuggerUrl"), "chrome CDP did not come up"
        pages = cdp_lib.pages(cdp)
        if not pages:
            cdp_lib.create_tab(cdp, f"http://127.0.0.1:{http_port}/login.html")
            time.sleep(0.4)
            pages = cdp_lib.pages(cdp)
        page = pages[0]
        cdp_lib.navigate(page["ws"], f"http://127.0.0.1:{http_port}/login.html")
        time.sleep(0.4)
        pages = cdp_lib.pages(cdp)
        page = next((p for p in pages if "login.html" in (p.get("url") or "")), pages[0])
        ws = page["ws"]
        form = login_lib.inspect_form(ws)
        assert form.get("step") == "username"
        user = "you@example.com"
        filled = login_lib.fill_username(ws, user)
        assert filled.get("ok") is True
        time.sleep(0.4)
        form = login_lib.inspect_form(ws)
        assert form.get("step") == "password"
        assert form.get("remembered") == user
        pw = login_lib.fill_password(ws, "demo-pass-not-real")
        assert pw.get("ok") is True
        time.sleep(0.4)
        form = login_lib.inspect_form(ws)
        assert form.get("step") == "2fa"
        assert form.get("remembered") == user
        tick = login_lib.act(ws, user, "demo-pass-not-real")
        assert tick.get("action") == "wait-2fa"
        otp = cdp_lib.call(
            ws,
            "Runtime.evaluate",
            {"expression": "document.getElementById('otp') && document.getElementById('otp').value", "returnByValue": True},
        )["result"]["value"]
        assert otp in ("", None)
        signed_in = cdp_lib.call(
            ws,
            "Runtime.evaluate",
            {"expression": "document.getElementById('step-ok').hidden", "returnByValue": True},
        )["result"]["value"]
        assert signed_in is True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        httpd.shutdown()
