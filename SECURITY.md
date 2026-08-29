# Security

## Reporting

Email **security@primfoundation.org** (or open a private GitHub security advisory on [primfoundation/prims-browsers](https://github.com/primfoundation/prims-browsers)) if you find a vulnerability.

Please do not file public issues for secrets, RCE, or auth bypasses until we have a fix or coordinated disclosure window.

## Scope

Prims Browsers runs headed Chromium in Docker and a local desk on loopback. Treat jars as **untrusted sandboxes**:

- Do not mount your host home directory into a jar.
- Do not paste production secrets into agent-controlled pages without vault discipline.
- Vault files under `~/.prim/prims-browsers/vault/` are the **system** store. Connected vaults (e.g. PaseoVault) are additional — treat each path as sensitive.
- `vaults.json` under `~/.prim/prims-browsers/` lists connected vaults; do not commit it.
- Published compose samples bind VNC/CDP to `127.0.0.1` only. Do not publish those ports to the LAN without auth/TLS.

## Supported versions

Security fixes land on `main`. Tag releases when practical; until then, pull `main`.
