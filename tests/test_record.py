"""Record command builder + state machine. Does not drive live jars."""

from __future__ import annotations

from lib import record


def test_ffmpeg_cmd_is_x11grab_on_display_zero():
    cmd = record.ffmpeg_cmd("1280x800", 10, record.JAR_MP4)
    assert cmd[:3] == ["ffmpeg", "-y", "-nostdin"]
    assert "-f" in cmd and "x11grab" in cmd
    assert ":0.0" in cmd
    assert "libx264" in cmd
    assert "1280x800" in cmd
    assert cmd[-1] == record.JAR_MP4


def test_start_refuses_live_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_RECORD_ROOT", str(tmp_path))
    record.save_state("eidos", {"pid": "99", "out": str(tmp_path / "x.mp4")})

    def fake_exec(container, args, **kwargs):
        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        text = " ".join(args)
        if "kill -0" in text:
            P.returncode = 0
            return P()
        raise AssertionError(text)

    monkeypatch.setattr(record, "exec_in", fake_exec)
    try:
        record.start("eidos", "prims-browsers-eidos", str(tmp_path / "a.mp4"))
    except RuntimeError as e:
        assert "already recording" in str(e)
    else:
        raise AssertionError("expected already recording")


def test_stop_without_state(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_RECORD_ROOT", str(tmp_path))
    try:
        record.stop("eidos", "prims-browsers-eidos")
    except RuntimeError as e:
        assert "not recording" in str(e)
    else:
        raise AssertionError("expected not recording")


def test_status_idle(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIMS_RECORD_ROOT", str(tmp_path))
    monkeypatch.setattr(record, "exec_in", lambda *a, **k: type("P", (), {"returncode": 1, "stdout": "", "stderr": ""})())
    st = record.status("eidos", "prims-browsers-eidos")
    assert st["recording"] is False
    assert st["id"] == "eidos"
