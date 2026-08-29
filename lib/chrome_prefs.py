"""Quiet Chromium password-save chrome so the desk vault is the only save UI."""

from __future__ import annotations

import json
from pathlib import Path


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".prims.tmp")
    tmp.write_text(json.dumps(data, indent=3))
    tmp.replace(path)


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def quiet_profile(profile_dir: Path) -> bool:
    root = Path(profile_dir)
    changed = False
    prefs = _load(root / "Default" / "Preferences")
    if prefs is not None:
        prefs["credentials_enable_service"] = False
        profile = prefs.get("profile")
        if not isinstance(profile, dict):
            profile = {}
            prefs["profile"] = profile
        profile["password_manager_enabled"] = False
        _write(root / "Default" / "Preferences", prefs)
        changed = True
    state = _load(root / "Local State")
    if state is not None:
        browser = state.get("browser")
        if not isinstance(browser, dict):
            browser = {}
            state["browser"] = browser
        browser["enabled_labs_experiments"] = list(
            dict.fromkeys(list(browser.get("enabled_labs_experiments") or []) + ["PasswordManagerOnboardingDisabled"])
        )
        _write(root / "Local State", state)
        changed = True
    return changed
