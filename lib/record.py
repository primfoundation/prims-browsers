"""Record the jar display (X11 :0), not the host desktop.

ffmpeg x11grab inside the container. Copy the mp4 out on stop.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

JAR_MP4 = "/tmp/prims-record.mp4"
JAR_PID = "/tmp/prims-record.pid"
JAR_LOG = "/tmp/prims-record.log"
APP_USER = "1000"


def state_dir() -> Path:
    env = os.environ.get("PRIMS_RECORD_ROOT")
    return Path(env) if env else Path.home() / ".prim/prims-browsers/record"


def state_path(tid: str) -> Path:
    return state_dir() / f"{tid}.json"


def ffmpeg_cmd(size: str, fps: int, dest: str) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "x11grab",
        "-framerate",
        str(fps),
        "-video_size",
        size,
        "-i",
        ":0.0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        dest,
    ]


def exec_in(
    container: str,
    args: list[str],
    *,
    user: str | None = APP_USER,
    check: bool = False,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "-e", "DISPLAY=:0"]
    if user:
        cmd.extend(["-u", str(user)])
    cmd.append(container)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=check)


def load_state(tid: str) -> dict | None:
    p = state_path(tid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def save_state(tid: str, row: dict) -> None:
    p = state_path(tid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(row, indent=2) + "\n")


def clear_state(tid: str) -> None:
    p = state_path(tid)
    if p.is_file():
        p.unlink()


def display_size(container: str) -> str:
    proc = exec_in(
        container,
        ["sh", "-c", 'echo ${DISPLAY_WIDTH:-1920}x${DISPLAY_HEIGHT:-1080}'],
    )
    size = (proc.stdout or "").strip()
    if not size or "x" not in size:
        return "1920x1080"
    return size


def ensure_ffmpeg(container: str) -> str:
    have = exec_in(container, ["sh", "-c", "command -v ffmpeg"])
    if have.returncode == 0 and (have.stdout or "").strip():
        return (have.stdout or "").strip()
    inst = exec_in(container, ["add-pkg", "ffmpeg"], user="0", timeout=180)
    if inst.returncode != 0:
        err = (inst.stderr or inst.stdout or "add-pkg ffmpeg failed").strip()[:240]
        raise RuntimeError(err)
    have = exec_in(container, ["sh", "-c", "command -v ffmpeg"])
    path = (have.stdout or "").strip()
    if have.returncode != 0 or not path:
        raise RuntimeError("ffmpeg missing after add-pkg")
    return path


def _alive(container: str, pid: str) -> bool:
    if not pid:
        return False
    proc = exec_in(container, ["sh", "-c", f"kill -0 {pid} 2>/dev/null"])
    return proc.returncode == 0


def start(tid: str, container: str, out: str, fps: int = 10) -> dict:
    existing = load_state(tid)
    if existing and _alive(container, str(existing.get("pid") or "")):
        raise RuntimeError(f"{tid} already recording pid={existing.get('pid')}")
    ensure_ffmpeg(container)
    size = display_size(container)
    inner = " ".join(ffmpeg_cmd(size, fps, JAR_MP4))
    script = (
        f"rm -f {JAR_MP4} {JAR_PID} {JAR_LOG}; "
        f"{inner} >{JAR_LOG} 2>&1 & echo $! > {JAR_PID}"
    )
    proc = exec_in(container, ["sh", "-c", script])
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg start failed").strip()[:240])
    time.sleep(0.4)
    pid_proc = exec_in(container, ["sh", "-c", f"cat {JAR_PID}"])
    pid = (pid_proc.stdout or "").strip()
    if not _alive(container, pid):
        log = exec_in(container, ["sh", "-c", f"cat {JAR_LOG} 2>/dev/null | tail -c 400"])
        raise RuntimeError((log.stdout or "ffmpeg died on start").strip()[:240])
    row = {
        "id": tid,
        "container": container,
        "pid": pid,
        "out": str(Path(out).expanduser().resolve()),
        "fps": fps,
        "size": size,
        "jar_mp4": JAR_MP4,
        "started": time.time(),
    }
    save_state(tid, row)
    return row


def stop(tid: str, container: str) -> dict:
    row = load_state(tid)
    if not row:
        raise RuntimeError(f"{tid} is not recording")
    pid = str(row.get("pid") or "")
    if _alive(container, pid):
        exec_in(container, ["sh", "-c", f"kill -INT {pid} 2>/dev/null"])
        for _ in range(20):
            if not _alive(container, pid):
                break
            time.sleep(0.15)
        if _alive(container, pid):
            exec_in(container, ["sh", "-c", f"kill -KILL {pid} 2>/dev/null"])
    out = Path(row.get("out") or (state_dir() / f"{tid}.mp4"))
    out.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["docker", "cp", f"{container}:{JAR_MP4}", str(out)],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
        err = (cp.stderr or "docker cp failed or empty mp4").strip()[:240]
        raise RuntimeError(err)
    clear_state(tid)
    exec_in(container, ["sh", "-c", f"rm -f {JAR_MP4} {JAR_PID} {JAR_LOG}"])
    row["bytes"] = out.stat().st_size
    row["out"] = str(out)
    row["stopped"] = time.time()
    return row


def status(tid: str, container: str) -> dict:
    row = load_state(tid) or {}
    pid = str(row.get("pid") or "")
    return {
        "id": tid,
        "recording": bool(row) and _alive(container, pid),
        "pid": pid or None,
        "out": row.get("out"),
        "size": row.get("size"),
        "fps": row.get("fps"),
    }
