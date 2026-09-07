import assert from "node:assert/strict";
import test from "node:test";
import { readCookie, signSession, verifySession } from "../shared/session.ts";

const secret = "0123456789abcdef0123456789abcdef";

function payload(overrides: Partial<{ sub: string; email: string; name: string; iat: number; exp: number }> = {}) {
  const now = Math.floor(Date.now() / 1000);
  return {
    sub: "apple-user-1",
    email: "person@example.test",
    name: "Example Person",
    iat: now,
    exp: now + 3600,
    ...overrides,
  };
}

test("sign and verify preserve the legacy payload contract", async () => {
  const original = payload();
  const token = await signSession(original, secret);
  const verified = await verifySession(token, secret);
  assert.deepEqual(verified, original);
  assert.equal(token.split(".").length, 2);
});

test("tampering fails closed", async () => {
  const token = await signSession(payload(), secret);
  const [body, signature] = token.split(".");
  const altered = `${body.slice(0, -1)}${body.endsWith("A") ? "B" : "A"}.${signature}`;
  assert.equal(await verifySession(altered, secret), null);
  assert.equal(await verifySession(token, "fedcba9876543210fedcba9876543210"), null);
});

test("expired and malformed sessions fail closed", async () => {
  const now = Math.floor(Date.now() / 1000);
  assert.equal(await verifySession(await signSession(payload({ exp: now - 1 }), secret), secret), null);
  assert.equal(await verifySession("not-a-token", secret), null);
  assert.equal(await verifySession(null, secret), null);
});

test("short signing secrets are rejected", async () => {
  await assert.rejects(() => signSession(payload(), "too-short"), /too short/);
});

test("cookie reader preserves opaque signed-token characters", () => {
  const request = new Request("https://browsers.prims.sh/", {
    headers: { Cookie: "other=x; prims_session=abc.def; theme=paper" },
  });
  assert.equal(readCookie(request, "prims_session"), "abc.def");
  assert.equal(readCookie(request, "missing"), null);
});
