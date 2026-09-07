import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";

/**
 * Sign in with Apple — OIDC/OAuth stubs.
 * Requires Apple Developer Services ID + Return URL (Daniel/Hancock).
 * Do not invent secrets; env-gate everything.
 */

export type AppleEnv = {
  APPLE_CLIENT_ID?: string;
  APPLE_TEAM_ID?: string;
  APPLE_KEY_ID?: string;
  APPLE_PRIVATE_KEY?: string;
  APPLE_REDIRECT_URI: string;
};

export function requireAppleConfig(env: AppleEnv): string | null {
  const missing: string[] = [];
  for (const k of [
    "APPLE_CLIENT_ID",
    "APPLE_TEAM_ID",
    "APPLE_KEY_ID",
    "APPLE_PRIVATE_KEY",
  ] as const) {
    if (!env[k]) missing.push(k);
  }
  if (missing.length) {
    return (
      "Apple Sign In is not configured. Missing env: " +
      missing.join(", ") +
      ". Create a Services ID in Apple Developer (Daniel/Hancock) with Return URL " +
      env.APPLE_REDIRECT_URI +
      ", then set secrets via wrangler secret put / .dev.vars."
    );
  }
  return null;
}

export function appleAuthorizeUrl(env: AppleEnv, state: string): string {
  const u = new URL("https://appleid.apple.com/auth/authorize");
  u.searchParams.set("response_type", "code");
  // Apple requires form_post whenever name or email scope is requested
  // (query mode → "invalid_request. response_mode must be form_post …").
  // The callback therefore arrives as an application/x-www-form-urlencoded
  // POST with code/state/error (and first-login user JSON), not a GET.
  u.searchParams.set("response_mode", "form_post");
  u.searchParams.set("client_id", env.APPLE_CLIENT_ID!);
  u.searchParams.set("redirect_uri", env.APPLE_REDIRECT_URI);
  u.searchParams.set("scope", "name email");
  u.searchParams.set("state", state);
  u.searchParams.set("nonce", state);
  return u.toString();
}

/** Build client_secret JWT (ES256) for Apple token endpoint. */
export async function appleClientSecret(env: AppleEnv): Promise<string> {
  const err = requireAppleConfig(env);
  if (err) throw new Error(err);

  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "ES256", kid: env.APPLE_KEY_ID! };
  const claims = {
    iss: env.APPLE_TEAM_ID!,
    iat: now,
    exp: now + 60 * 30,
    aud: "https://appleid.apple.com",
    sub: env.APPLE_CLIENT_ID!,
  };

  const enc = new TextEncoder();
  const b64url = (buf: ArrayBuffer | Uint8Array | string) => {
    const bytes =
      typeof buf === "string"
        ? enc.encode(buf)
        : buf instanceof Uint8Array
          ? buf
          : new Uint8Array(buf);
    let s = "";
    for (const b of bytes) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };

  const unsigned = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(claims))}`;

  let pem = env.APPLE_PRIVATE_KEY!.replace(/\\n/g, "\n").trim();
  pem = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const der = Uint8Array.from(atob(pem), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    key,
    enc.encode(unsigned),
  );
  return `${unsigned}.${b64url(sig)}`;
}

export type AppleTokenResponse = {
  access_token?: string;
  id_token?: string;
  refresh_token?: string;
  error?: string;
  error_description?: string;
};

export async function exchangeAppleCode(
  env: AppleEnv,
  code: string,
): Promise<AppleTokenResponse> {
  const clientSecret = await appleClientSecret(env);
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: env.APPLE_REDIRECT_URI,
    client_id: env.APPLE_CLIENT_ID!,
    client_secret: clientSecret,
  });
  const res = await fetch("https://appleid.apple.com/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return (await res.json()) as AppleTokenResponse;
}

const appleKeys = createRemoteJWKSet(new URL("https://appleid.apple.com/auth/keys"));

export async function verifyAppleIdToken(
  env: Pick<AppleEnv, "APPLE_CLIENT_ID">, token: string, nonce: string,
  keys: JWTVerifyGetKey = appleKeys,
) {
  if (!env.APPLE_CLIENT_ID || !nonce || token.length > 32768) throw new Error("Invalid identity token");
  const { payload } = await jwtVerify(token, keys, {
    algorithms: ["RS256"], issuer: "https://appleid.apple.com", audience: env.APPLE_CLIENT_ID,
    requiredClaims: ["sub", "iat", "exp", "nonce"], clockTolerance: 5,
  });
  if (typeof payload.sub !== "string" || !payload.sub || payload.nonce !== nonce ||
      !Number.isSafeInteger(payload.iat) || payload.iat! > Date.now() / 1000 + 5) {
    throw new Error("Invalid identity token");
  }
  return payload;
}
