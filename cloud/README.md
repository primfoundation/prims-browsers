# Prims Browsers cloud consolidation

Both Cloudflare applications now live here: `apps/login` is the Apple sign-in door and `apps/gateway` is the authenticated container list/hop surface. They import one `shared/session.ts` and reuse the repository's `brand/` assets. Exact source commits and compatibility gates are recorded in [migration.json](migration.json).

The source imports are adapted, not byte-for-byte mirrors. They remove the legacy unsigned Apple identity-token decoder, missing-secret development bypass and embedded fallback fleet. Apple tokens now require a valid RS256 signature from Apple JWKS, issuer, audience, expiry and state-bound nonce. Valid legacy HMAC sessions remain compatible; malformed or incorrectly typed tokens fail closed. Invalid/ambiguous fleet configuration exposes no containers.

## Verify

```bash
cd cloud
npm ci --ignore-scripts
npm run verify
npm run dry-run
```

The 13 tests cover shared legacy sessions, authenticated/unauthenticated gateway routes, deep-link errors, logout, configuration failure, signed/forged Apple-token fixtures and a complete mocked Apple form-post/token-exchange/JWKS/session/gateway round trip. Both actual Worker entry points typecheck and dry-build with shared assets. These are synthetic/local proofs; they do not establish a real Apple account or production browser-container session.

## Preview and cutover

Checked-in Worker names end in `-preview`. Route URLs use `.invalid`, `COOKIE_DOMAIN` is empty (host-only), and `CONTAINERS` is empty. Set approved preview URLs and synthetic fleet configuration before deployment. Keep secret values in Cloudflare bindings. A real end-to-end preview across separate login/gateway hosts needs a controlled shared parent domain and matching cookie scope; unrelated workers.dev hosts cannot share a host-only cookie.

For production compatibility, preserve `login.prims.sh`, `browsers.prims.sh`, `prims_session`, `.prims.sh` scope, the deliberate shared-secret migration window, Apple's cross-site POST state cookie and the independent Authentik gate at container hosts. At cutover, restart login attempts begun by the old Worker because they lack the new nonce; already-valid session cookies remain verifiable.

Before moving routes, record preview deployments and source revisions; verify real Apple callback, existing sessions, logout, invalid sessions and a real container hop. Retain the prior Worker versions, routes and configuration for rollback. Restore both surfaces together if shared-contract acceptance fails, then repeat health/session checks. Record an actual recovery drill and observation window before archiving either source repository. No account, Apple service configuration, live Worker, DNS route or legacy history was changed by this import.
