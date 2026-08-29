"""PaseoVault envelope — same file the Paseo plugin uses.

Format is paseo-vault:v1 (scrypt + AES-256-GCM). The file lives on the cell's
paseo-home bind, so headed Prim desk on the host and the plugin in the container
open one store. Never log the key or a secret.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"paseo-vault:v1"
SCRYPT_N = 32_768
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024

_LOCK = threading.RLock()


def vault_dir(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root).expanduser()
    env = os.environ.get("PASEO_VAULT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".paseo" / "paseo-vault"


def vault_path(root: Path | str | None = None) -> Path:
    return vault_dir(root) / "vault.enc"


def key_path(root: Path | str | None = None) -> Path:
    return vault_dir(root) / "key"


def _derive(passphrase: str, salt: bytes) -> bytes:
    return hashlib_scrypt(passphrase.encode("utf-8"), salt)


def hashlib_scrypt(password: bytes, salt: bytes) -> bytes:
    import hashlib

    return hashlib.scrypt(
        password,
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=SCRYPT_MAXMEM,
    )


def ensure_key(root: Path | str | None = None) -> str:
    """Local cell key, mode 600. Hub passphrase UI can wait; browsing cannot."""
    path = key_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o770)
    except PermissionError:
        pass
    if not path.is_file():
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o660)
        try:
            os.write(fd, (secrets.token_urlsafe(32) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(path, 0o660)
    text = path.read_text(encoding="utf-8").strip()
    if len(text) < 12:
        raise ValueError("PaseoVault key file is too short")
    return text


def _b64(raw: bytes) -> str:
    import base64

    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str, n: int | None = None) -> bytes:
    import base64

    if not isinstance(text, str) or len(text) % 4 != 0 or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", text):
        raise ValueError("PaseoVault has an invalid field")
    decoded = base64.b64decode(text, validate=True)
    if base64.b64encode(decoded).decode("ascii") != text:
        raise ValueError("PaseoVault has an invalid field")
    if n is not None and len(decoded) != n:
        raise ValueError("PaseoVault has an invalid field")
    return decoded


def seal(payload: dict, key: bytes, salt: bytes) -> dict:
    nonce = os.urandom(12)
    aes = AESGCM(key)
    packed = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    out = aes.encrypt(nonce, packed, AAD)
    return {
        "version": 1,
        "kdf": "scrypt",
        "cipher": "aes-256-gcm",
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "tag": _b64(out[-16:]),
        "ciphertext": _b64(out[:-16]),
    }


def open_envelope(passphrase: str, envelope: dict) -> tuple[bytes, bytes, dict]:
    if envelope.get("version") != 1 or envelope.get("kdf") != "scrypt" or envelope.get("cipher") != "aes-256-gcm":
        raise ValueError("PaseoVault file uses an unsupported format")
    salt = _unb64(envelope["salt"], 16)
    key = _derive(passphrase, salt)
    nonce = _unb64(envelope["nonce"], 12)
    tag = _unb64(envelope["tag"], 16)
    ciphertext = _unb64(envelope["ciphertext"])
    try:
        plain = AESGCM(key).decrypt(nonce, ciphertext + tag, AAD)
        payload = json.loads(plain.decode("utf-8"))
    except Exception as exc:
        key = b""
        raise ValueError("Could not unlock PaseoVault.") from exc
    items = payload.get("items")
    if not isinstance(payload, dict) or not isinstance(items, list):
        raise ValueError("PaseoVault data is corrupt.")
    return key, salt, {"items": [_item(x) for x in items]}


def _item(candidate: object) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("PaseoVault contains an invalid item.")
    username = candidate.get("username")
    if username is not None and not isinstance(username, str):
        raise ValueError("PaseoVault has an invalid username.")
    for field in ("id", "label", "secret", "createdAt", "updatedAt"):
        if not isinstance(candidate.get(field), str) or not candidate[field]:
            raise ValueError(f"PaseoVault has an invalid {field}.")
    return {
        "id": candidate["id"],
        "label": candidate["label"],
        "username": username,
        "secret": candidate["secret"],
        "createdAt": candidate["createdAt"],
        "updatedAt": candidate["updatedAt"],
    }


def _load_open(root: Path | str | None = None) -> tuple[bytes, bytes, dict]:
    phrase = ensure_key(root)
    path = vault_path(root)
    if not path.is_file():
        salt = os.urandom(16)
        key = _derive(phrase, salt)
        payload = {"items": []}
        _write(seal(payload, key, salt), root=root)
        return key, salt, payload
    envelope = json.loads(path.read_text(encoding="utf-8"))
    return open_envelope(phrase, envelope)


def _write(envelope: dict, root: Path | str | None = None) -> None:
    path = vault_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o770)
    except PermissionError:
        pass
    tmp = path.with_name(f".vault.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o660)
    except PermissionError:
        pass
    tmp.replace(path)
    try:
        os.chmod(path, 0o660)
    except PermissionError:
        pass


def _iso_to_epoch(stamp: str) -> float:
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def public_row(item: dict) -> dict:
    return {
        "id": item["id"],
        "host": item["label"],
        "login": item.get("username") or "",
        "created_at": _iso_to_epoch(item["createdAt"]),
        "last_used_at": _iso_to_epoch(item["updatedAt"]),
        "has_password": bool(item.get("secret")),
    }


def list_records(_tid: str, root: Path | str | None = None) -> list[dict]:
    with _LOCK:
        _key, _salt, payload = _load_open(root)
        rows = [public_row(item) for item in payload["items"]]
    return sorted(rows, key=lambda r: float(r.get("last_used_at") or 0), reverse=True)


def add(_tid: str, host: str, login: str, password: str, root: Path | str | None = None) -> dict:
    host = (host or "").strip().lower().removeprefix("www.")
    login = (login or "").strip()
    if not host or not login or not password:
        raise ValueError("host, login, and password required")
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    item = {
        "id": f"paseo-vault:{uuid.uuid4()}",
        "label": host,
        "username": login,
        "secret": password,
        "createdAt": now,
        "updatedAt": now,
    }
    with _LOCK:
        key, salt, payload = _load_open(root)
        payload["items"].append(item)
        _write(seal(payload, key, salt), root=root)
    return public_row(item)


def remove(_tid: str, rid: str, root: Path | str | None = None) -> bool:
    with _LOCK:
        key, salt, payload = _load_open(root)
        before = len(payload["items"])
        payload["items"] = [item for item in payload["items"] if item["id"] != rid]
        if len(payload["items"]) == before:
            return False
        _write(seal(payload, key, salt), root=root)
        return True


def touch(_tid: str, rid: str, root: Path | str | None = None) -> bool:
    with _LOCK:
        key, salt, payload = _load_open(root)
        found = False
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        for item in payload["items"]:
            if item["id"] == rid:
                item["updatedAt"] = now
                found = True
        if found:
            _write(seal(payload, key, salt), root=root)
        return found


def secret(_tid: str, rid: str, root: Path | str | None = None) -> dict | None:
    with _LOCK:
        _key, _salt, payload = _load_open(root)
        for item in payload["items"]:
            if item["id"] == rid:
                return {
                    "id": item["id"],
                    "host": item["label"],
                    "login": item.get("username") or "",
                    "password": item["secret"],
                }
    return None
