"""Detect pages that need a human: captcha, bot-check, login, approve.

Only what's on screen. Article copy that mentions 'captcha' is not a gate.
Consent is clicked, not a yellow human-orb.
"""

from __future__ import annotations

import base64
import subprocess
import tempfile

from lib import cdp as cdp_lib

HARD = frozenset({"captcha", "human", "cloudflare", "2fa", "login", "sso"})

DETECT_JS = r"""
(() => {
  const vis = document.visibilityState;
  const title = (document.title || "").toLowerCase();
  const href = (location.href || "").toLowerCase();
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const authUrl = /\/login|\/signin|sign-in|accounts\.|authentik|auth\.openai|chatgpt\.com\/auth/.test(href);
  const hits = [];
  if (shown(document.querySelector('#challenge-running, #cf-stage, .cf-turnstile, iframe[src*="challenges.cloudflare"]')))
    hits.push("cloudflare");
  if (shown(document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .g-recaptcha, .h-captcha')))
    hits.push("captcha");
  const btn = [...document.querySelectorAll("button, [role=button]")].find(b => /accept and continue|accept all cookies|agree and continue|^i agree$|^accept all$/i.test((b.innerText||"").trim()));
  if (btn && shown(btn)) hits.push("consent");
  if (/^just a moment|^attention required|verify you are human|checking your browser before/.test(title))
    hits.push("cloudflare");
  const otp = [...document.querySelectorAll('input')].find(i => shown(i) && (i.autocomplete === 'one-time-code' || /otp|totp|2fa|one-time/.test(((i.name||'')+' '+(i.id||'')).toLowerCase())));
  if (otp) hits.push("2fa");
  const pass = [...document.querySelectorAll('input[type=password]')].find(shown);
  const user = [...document.querySelectorAll('input')].find(i => shown(i) && (i.type === 'email' || /email|username|identifier/.test(((i.name||'')+' '+(i.id||'')+' '+(i.autocomplete||'')).toLowerCase())));
  if (pass && authUrl) hits.push("login");
  if (!pass && user && authUrl) hits.push("login");
  if (!pass && !user && !otp) {
    const sso = [...document.querySelectorAll("button, [role=button], a")].find(b => {
      if (!shown(b)) return false;
      const t = ((b.innerText || b.getAttribute("aria-label") || "")).toLowerCase();
      return /continue with google|continue with apple|sign in with google|sign in with apple/.test(t);
    });
    if (sso && authUrl) hits.push("sso");
  }
  const hard = hits.find(h => h !== "consent") || null;
  return {
    gated: hits.length > 0,
    reason: hard || hits[0] || null,
    hits,
    visible: vis === "visible",
    title: document.title || "",
    href: location.href || ""
  };
})()
"""

CONSENT_JS = r"""
(() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const btn = [...document.querySelectorAll("button, [role=button]")].find(b => {
    if (!shown(b)) return false;
    return /accept and continue|accept all cookies|agree and continue|^i agree$|^accept all$/i.test((b.innerText||"").trim());
  });
  if (!btn) return {ok:false};
  btn.click();
  return {ok:true, t: (btn.innerText||"").trim().slice(0,40)};
})()
"""


def is_hard(reason: str | None) -> bool:
    return (reason or "") in HARD


def ocr_text(png: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(png)
        f.flush()
        try:
            return subprocess.check_output(
                ["tesseract", f.name, "stdout", "--psm", "6"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=12,
            )
        except Exception:
            return ""


def ocr_reason(text: str) -> str | None:
    t = (text or "").lower()
    if "verify you are human" in t or "i'm not a robot" in t or "not a robot" in t:
        return "human"
    if "just a moment" in t or "checking your browser" in t or "attention required" in t:
        return "cloudflare"
    if "enter the characters you see" in t:
        return "captcha"
    return None


def inspect_shot(ws_url: str) -> dict:
    try:
        data = cdp_lib.call(ws_url, "Page.captureScreenshot", {"format": "png"}).get("data")
        if not data:
            return {"gated": False, "reason": None}
        png = base64.b64decode(data)
        text = ocr_text(png)
        reason = ocr_reason(text)
        return {"gated": bool(reason), "reason": reason, "ocr": text[:400]}
    except Exception as e:
        return {"gated": False, "reason": None, "error": str(e)[:120]}


def inspect(ws_url: str) -> dict:
    try:
        result = cdp_lib.call(ws_url, "Runtime.evaluate", {"expression": DETECT_JS, "returnByValue": True})
        val = (result or {}).get("result", {}).get("value")
        if isinstance(val, dict):
            return {
                "gated": bool(val.get("gated")),
                "reason": val.get("reason"),
                "hits": val.get("hits") or [],
                "title": val.get("title") or "",
                "href": val.get("href") or "",
            }
    except Exception as e:
        return {"gated": False, "reason": None, "error": str(e)[:120]}
    return {"gated": False, "reason": None}


def click_consent(ws_url: str) -> dict:
    try:
        r = cdp_lib.call(ws_url, "Runtime.evaluate", {"expression": CONSENT_JS, "returnByValue": True})
        val = (r or {}).get("result", {}).get("value")
        return val if isinstance(val, dict) else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def inspect_page(p: dict) -> dict:
    if not p.get("ws"):
        return {"gated": False, "reason": None, "tab": p.get("id")}
    hit = inspect(p["ws"])
    hit["tab"] = p.get("id")
    if hit.get("reason") == "consent":
        click_consent(p["ws"])
        hit = inspect(p["ws"])
        hit["tab"] = p.get("id")
        hit["consent"] = True
    if not hit.get("gated") and p.get("ws"):
        title = (hit.get("title") or "").lower()
        if title.startswith("just a moment") or "attention required" in title or "verify you are" in title or "checking your browser" in title:
            shot = inspect_shot(p["ws"])
            if is_hard(shot.get("reason")):
                hit = {**hit, **shot, "tab": p.get("id")}
    hit["hard"] = is_hard(hit.get("reason"))
    hit["gated"] = bool(hit.get("hard"))
    return hit


def inspect_front(cdp_base: str) -> dict:
    plist = cdp_lib.pages(cdp_base)
    if not plist:
        return {"gated": False, "reason": None, "tabs": 0}
    target = cdp_lib.visible_page(cdp_base, plist) or plist[0]
    hit = inspect_page(target)
    hit["tabs"] = len(plist)
    return hit


def label(reason: str | None) -> str:
    return {
        "captcha": "prove you're human",
        "human": "prove you're human",
        "cloudflare": "prove you're human",
        "login": "sign in",
        "consent": "accept to continue",
        "2fa": "enter the code",
        "sso": "use a password login",
    }.get(reason or "", "needs you")
