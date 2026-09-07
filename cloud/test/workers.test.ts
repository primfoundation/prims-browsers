import assert from "node:assert/strict";
import test from "node:test";
import { createLocalJWKSet, exportJWK, exportPKCS8, generateKeyPair, jwtVerify, SignJWT } from "jose";
import login from "../apps/login/src/index.ts";
import gateway from "../apps/gateway/src/index.ts";
import { verifyAppleIdToken } from "../apps/login/src/apple.ts";
import { parseContainers } from "../apps/gateway/src/ui.ts";
import { signSession, verifySession } from "../shared/session.ts";

const secret = "synthetic-session-secret-for-tests-only";
const assets = { fetch: async () => new Response("asset") };
const fleet = [{ id: "demo", machine: "sandbox", tenant: "demo", label: "Example", url: "https://browser.example.test/" }];
const env = { SESSION_SECRET: secret, LOGIN_URL: "https://login.example.test/", COOKIE_NAME: "prims_session", COOKIE_DOMAIN: ".example.test", CONTAINERS: JSON.stringify(fleet), ASSETS: assets };
const apple = { APPLE_CLIENT_ID: "test-client", APPLE_TEAM_ID: "test-team", APPLE_KEY_ID: "test-key", APPLE_PRIVATE_KEY: "configured-but-unused", APPLE_REDIRECT_URI: "https://login.example.test/auth/apple/callback", POST_LOGIN_REDIRECT: "https://gateway.example.test/", ...env };

test("gateway fails closed without secrets, including the former dev bypass", async () => {
  for (const path of ["/", "/?dev=1", "/containers?dev=1"]) {
    const response = await gateway.fetch(new Request("https://gateway.example.test" + path), { ...env, SESSION_SECRET: undefined });
    assert.equal(response.status, 503);
    assert.doesNotMatch(await response.text(), /SESSION_SECRET|dev stub|browser\.example/);
  }
});

test("real gateway verifies legacy cookies, protects the fleet, and clears logout cookies", async () => {
  assert.equal((await gateway.fetch(new Request("https://gateway.example.test/containers"), env)).status, 302);
  const now = Math.floor(Date.now() / 1000);
  const token = await signSession({ sub: "example-user", iat: now, exp: now + 600 }, secret);
  const headers = { Cookie: `prims_session=${token}` };
  const response = await gateway.fetch(new Request("https://gateway.example.test/containers", { headers }), env);
  assert.deepEqual(await response.json(), { containers: fleet });
  assert.equal((await gateway.fetch(new Request("https://gateway.example.test/w/sandbox/demo", { headers }), env)).status, 200);
  assert.equal((await gateway.fetch(new Request("https://gateway.example.test/w/sandbox/unknown", { headers }), env)).status, 404);
  assert.equal((await gateway.fetch(new Request("https://gateway.example.test/w/%ZZ/demo", { headers }), env)).status, 400);
  const logout = await gateway.fetch(new Request("https://gateway.example.test/logout", { method: "POST" }), env);
  assert.match(logout.headers.get("set-cookie")!, /Max-Age=0/);
  assert.match(logout.headers.get("set-cookie")!, /Domain=\.example\.test/);
});

test("malformed cookies never crash authentication", async () => {
  for (const token of ["x.%", "%.x", "a.a", ".", "x".repeat(9000)]) {
    assert.equal(await verifySession(token, secret), null);
  }
  const now = Math.floor(Date.now() / 1000);
  for (const overrides of [{ exp: "forever" }, { sub: 123 }, { iat: now + 600 }, { exp: now }, { email: {} }]) {
    const value = { sub: "example", iat: now, exp: now + 600, ...overrides };
    assert.equal(await verifySession(await signSession(value as never, secret), secret), null);
  }
});

test("invalid or ambiguous container configuration exposes no fallback fleet", () => {
  for (const value of [undefined, "{", "{}", "[]", JSON.stringify([...fleet, ...fleet]), JSON.stringify([{ ...fleet[0], url: "https://user:password@example.test/" }])]) {
    assert.deepEqual(parseContainers(value), []);
  }
  assert.deepEqual(parseContainers(JSON.stringify(fleet)), fleet);
});

test("Apple authorization binds nonce to state and preserves cross-site POST cookies", async () => {
  const response = await login.fetch(new Request("https://login.example.test/auth/apple"), apple);
  const location = new URL(response.headers.get("location")!);
  assert.equal(location.searchParams.get("response_mode"), "form_post");
  assert.equal(location.searchParams.get("nonce"), location.searchParams.get("state"));
  assert.match(response.headers.get("set-cookie")!, /SameSite=None/);
  assert.match(response.headers.get("set-cookie")!, /Secure/);
  const rejected = await login.fetch(new Request("https://login.example.test/auth/apple/callback", {
    method: "POST", body: new URLSearchParams({ code: "unused", state: "wrong" }), headers: { Cookie: "prims_oauth_state=expected" }
  }), apple);
  assert.equal(rejected.status, 302);
  assert.match(rejected.headers.get("location")!, /Invalid%20OAuth%20state/);
  assert.equal(rejected.headers.get("set-cookie"), null);
});

test("Apple tokens require a valid signature, issuer, audience, expiry and nonce", async () => {
  const pair = await generateKeyPair("RS256");
  const jwk = { ...await exportJWK(pair.publicKey), kid: "fixture" };
  const keys = createLocalJWKSet({ keys: [jwk] });
  const now = Math.floor(Date.now() / 1000);
  const claims = { sub: "apple-sub", iss: "https://appleid.apple.com", aud: "test-client", iat: now, exp: now + 600, nonce: "expected" };
  const sign = (payload: Record<string, unknown>) => new SignJWT(payload).setProtectedHeader({ alg: "RS256", kid: "fixture" }).sign(pair.privateKey);
  const valid = await sign(claims);
  assert.equal((await verifyAppleIdToken(apple, valid, "expected", keys)).sub, "apple-sub");
  for (const change of [{ iss: "https://attacker.invalid" }, { aud: "another-client" }, { exp: now - 60 }, { nonce: "wrong" }, { iat: now + 600 }]) {
    await assert.rejects(() => sign({ ...claims, ...change }).then(token => verifyAppleIdToken(apple, token, "expected", keys)));
  }
  const other = await generateKeyPair("RS256");
  const forged = await new SignJWT(claims).setProtectedHeader({ alg: "RS256", kid: "fixture" }).sign(other.privateKey);
  await assert.rejects(() => verifyAppleIdToken(apple, forged, "expected", keys));
  const { nonce: _, ...missingNonce } = claims;
  await assert.rejects(() => sign(missingNonce).then(token => verifyAppleIdToken(apple, token, "expected", keys)));
});


test("Apple form-post completes only with the verified token and issues a gateway-compatible session", async (t) => {
  const identity = await generateKeyPair("RS256");
  const client = await generateKeyPair("ES256", { extractable: true });
  const configured = { ...apple, APPLE_PRIVATE_KEY: await exportPKCS8(client.privateKey) };
  const now = Math.floor(Date.now() / 1000);
  let token = await new SignJWT({ sub: "roundtrip-user", email: "example@example.test", nonce: "roundtrip-state" })
    .setProtectedHeader({ alg: "RS256", kid: "roundtrip-key" }).setIssuer("https://appleid.apple.com")
    .setAudience(apple.APPLE_CLIENT_ID).setIssuedAt(now).setExpirationTime(now + 600).sign(identity.privateKey);
  let exchanges = 0;
  t.mock.method(globalThis, "fetch", async (input: string | URL | Request, init?: RequestInit) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url === "https://appleid.apple.com/auth/keys")
      return Response.json({ keys: [{ ...await exportJWK(identity.publicKey), kid: "roundtrip-key", alg: "RS256", use: "sig" }] });
    assert.equal(url, "https://appleid.apple.com/auth/token");
    assert.equal(init?.method, "POST");
    const body = new URLSearchParams(init?.body as string);
    assert.equal(body.get("code"), "synthetic-code");
    assert.equal(body.get("redirect_uri"), apple.APPLE_REDIRECT_URI);
    await jwtVerify(body.get("client_secret")!, client.publicKey, {
      algorithms: ["ES256"], issuer: apple.APPLE_TEAM_ID, audience: "https://appleid.apple.com", subject: apple.APPLE_CLIENT_ID,
    });
    exchanges++;
    return Response.json({ id_token: token });
  });
  const request = () => new Request(apple.APPLE_REDIRECT_URI, {
    method: "POST", headers: { Cookie: "prims_oauth_state=roundtrip-state" },
    body: new URLSearchParams({ state: "roundtrip-state", code: "synthetic-code", user: JSON.stringify({ name: { firstName: "Example", lastName: "User" } }) }),
  });
  const response = await login.fetch(request(), configured);
  assert.equal(response.status, 302);
  assert.equal(response.headers.get("location"), apple.POST_LOGIN_REDIRECT);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const cookies = response.headers.getSetCookie();
  const sessionCookie = cookies.find(c => c.startsWith("prims_session="))!;
  assert.match(sessionCookie, /HttpOnly; Secure; SameSite=Lax/);
  assert.ok(cookies.some(c => c.startsWith("prims_oauth_state=;") && c.includes("Max-Age=0")));
  const me = await login.fetch(new Request("https://login.example.test/me", { headers: { Cookie: sessionCookie.split(";")[0] } }), configured);
  const data = await me.json() as { session: { sub: string; name: string } };
  assert.equal(data.session.sub, "roundtrip-user");
  assert.equal(data.session.name, "Example User");
  const gatewayResponse = await gateway.fetch(new Request("https://gateway.example.test/containers", { headers: { Cookie: sessionCookie.split(";")[0] } }), env);
  assert.equal(gatewayResponse.status, 200);
  assert.equal(gatewayResponse.headers.get("cache-control"), "no-store");
  token = token.slice(0, token.lastIndexOf(".") + 1) + "forged";
  const rejected = await login.fetch(request(), configured);
  assert.match(rejected.headers.get("location")!, /could%20not%20be%20verified/);
  assert.equal(rejected.headers.get("set-cookie"), null);
  assert.equal(exchanges, 2);
});

test("Apple callback bounds input and never reveals missing configuration", async () => {
  const base = { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" } };
  assert.equal((await login.fetch(new Request(apple.APPLE_REDIRECT_URI, { ...base, body: "x".repeat(32769) }), apple)).status, 413);
  assert.equal((await login.fetch(new Request(apple.APPLE_REDIRECT_URI, { method: "POST", body: "text" }), apple)).status, 415);
  const unavailable = await login.fetch(new Request(apple.APPLE_REDIRECT_URI, { ...base, body: "state=a&code=b" }), { ...apple, SESSION_SECRET: "short" });
  assert.equal(unavailable.status, 503);
  assert.doesNotMatch(await unavailable.text(), /SESSION_SECRET|APPLE_CLIENT|wrangler|Hancock/);
});
