# Prims Browsers cloud consolidation

This directory is the future home for the two Cloudflare surfaces that exist only to operate **Prims Browsers**. It starts by centralizing their duplicated session contract and exact migration metadata. Production routes remain in the legacy repositories until preview and real-account acceptance pass.

## Target

```text
cloud/
  shared/
    session.ts
  apps/
    login/       # future import from primfoundation/logins-prims-sh
    gateway/     # future import from primfoundation/browsers-prims-sh
  migration.json
```

The two source repositories currently duplicate the exact same `src/session.ts` Git blob. That is now represented once under `cloud/shared/session.ts` with compatibility tests. No `SESSION_SECRET`, Apple private key, user cookie or container credential is copied into Git.

## Locked production behavior

- `login.prims.sh` remains the Apple OAuth door.
- Apple's form-post callback needs its cross-site state-cookie behavior preserved.
- `prims_session` remains HMAC-SHA256 and scoped to `.prims.sh` during compatibility migration.
- `browsers.prims.sh` remains the authenticated container list/hop surface.
- Container hosts retain their separate Authentik gate.
- Foundation Hub/publisher identity is **not** substituted for the browser-product login.

The current shared-secret cookie design is preserved only to make consolidation non-breaking. A future identity redesign must be a separate security/version migration with a dual-read or explicit logout/cutover plan.

## What is not done yet

The login/gateway application sources, public assets and wrangler configs have not been imported in this first slice. DNS, Cloudflare Workers, Apple configuration and production secrets are untouched. The legacy repositories are not archived and their histories remain authoritative for their current deployed code.

Next: import each source commit into `cloud/apps/*` with provenance, replace its local session file with this shared contract, run the legacy test behavior from here, then produce non-production Workers before any route cutover.
