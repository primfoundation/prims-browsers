"""Agentic login: remember username → fill password page → wait on 2FA. Never log secrets."""

from __future__ import annotations

import json

from lib import cdp as cdp_lib

FORM_JS = r"""
(() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== 'hidden' && st.display !== 'none' && !el.disabled;
  };
  const inputs = [...document.querySelectorAll('input')].filter(shown);
  const blob = ((document.body && document.body.innerText) || '').slice(0, 1800).toLowerCase();
  const meta = (el) => ((el.autocomplete||'')+' '+(el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.inputMode||'')).toLowerCase();
  const otp = inputs.find(i => i.autocomplete === 'one-time-code' || /otp|totp|2fa|one-time|one_time|verify-code|verification/.test(meta(i)));
  const pass = inputs.find(i => i.type === 'password');
  const user = inputs.find(i => i.type === 'email' || /email|username|user|login|identifier/.test(meta(i)));
  const textOnly = inputs.filter(i => i.type === 'text' || i.type === 'email' || i.type === 'tel');
  const sso = [...document.querySelectorAll('button, [role=button], a')].some(b => {
    if (!shown(b)) return false;
    const t = ((b.innerText || b.getAttribute('aria-label') || '')).toLowerCase();
    return /continue with google|continue with apple|sign in with google|sign in with apple/.test(t);
  });
  let step = 'other';
  if (otp)
    step = '2fa';
  else if (pass) step = 'password';
  else if (user || (textOnly.length === 1 && !pass)) step = 'username';
  else if (sso) step = 'sso';
  const who = document.querySelector('[data-remembered]')?.textContent || user?.value || '';
  return {
    step,
    hasUser: Boolean(user || textOnly[0]),
    hasPass: Boolean(pass),
    hasOtp: Boolean(otp),
    hasSso: Boolean(sso),
    remembered: (who || '').trim().slice(0, 120),
    href: location.href,
    title: document.title || '',
  };
})()
"""

FOCUS_JS = r"""
(() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== 'hidden' && st.display !== 'none' && !el.disabled;
  };
  const inputs = [...document.querySelectorAll('input')].filter(shown);
  const meta = (el) => ((el.autocomplete||'')+' '+(el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')).toLowerCase();
  const kind = %s;
  let el = null;
  if (kind === 'password') el = inputs.find(i => i.type === 'password');
  else el = inputs.find(i => i.type === 'email' || /email|username|user|login|identifier/.test(meta(i)))
        || inputs.find(i => i.type === 'text' || i.type === 'email' || i.type === 'tel');
  if (!el) return {ok:false, error:'no field'};
  el.focus();
  el.click();
  try { el.select(); } catch (e) {}
  const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
  if (proto && proto.set) proto.set.call(el, '');
  else el.value = '';
  el.dispatchEvent(new InputEvent('input', {bubbles:true, composed:true, inputType:'deleteContent'}));
  return {ok:true, kind};
})()
"""

SUBMIT_JS = r"""
(() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== 'hidden' && st.display !== 'none' && !el.disabled;
  };
  const active = document.activeElement;
  const btn = [...document.querySelectorAll('button, input[type=submit]')].filter(shown).find(b => {
    const t = ((b.innerText || b.value || '') + ' ' + (b.getAttribute('aria-label')||'')).toLowerCase().trim();
    if (/with |google|apple|github|phone|passkey|confirm code/.test(t)) return false;
    return /^(next|continue|log in|sign in|submit)$/i.test(t) || /^(next|continue|log in|sign in|submit)\b/.test(t);
  });
  if (btn) { btn.click(); return {ok:true, submitted:true, how:'button'}; }
  if (active && active.form) {
    try { active.form.requestSubmit(); } catch(e) { active.form.submit(); }
    return {ok:true, submitted:true, how:'form'};
  }
  return {ok:true, submitted:false};
})()
"""

CHECK_JS = r"""
(() => {
  const el = document.activeElement;
  if (!el || !('value' in el)) return {ok:true, valueOn:0};
  return {ok:true, valueOn: (el.value || '').length};
})()
"""


def inspect_form(ws: str) -> dict:
    try:
        r = cdp_lib.call(ws, "Runtime.evaluate", {"expression": FORM_JS, "returnByValue": True})
        val = (r or {}).get("result", {}).get("value")
        if isinstance(val, dict):
            return val
    except Exception as e:
        return {"step": "other", "error": str(e)[:120]}
    return {"step": "other"}


def _eval(ws: str, expression: str, await_promise: bool = False) -> dict:
    r = cdp_lib.call(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
    )
    val = (r or {}).get("result", {}).get("value")
    return val if isinstance(val, dict) else {"ok": False}


def _fill(ws: str, kind: str, value: str, submit: bool = True) -> dict:
    focused = _eval(ws, FOCUS_JS % json.dumps(kind))
    if not focused.get("ok"):
        return focused
    try:
        cdp_lib.call(ws, "Input.insertText", {"text": value})
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "kind": kind}
    check = _eval(ws, CHECK_JS)
    filled = int(check.get("valueOn") or 0)
    out = {"ok": filled > 0, "kind": kind, "valueOn": filled, "submitted": False}
    if filled <= 0:
        out["error"] = "empty"
        return out
    if submit:
        clicked = _eval(ws, SUBMIT_JS)
        out["submitted"] = bool(clicked.get("submitted"))
        out["how"] = clicked.get("how")
    return out


def fill_username(ws: str, login: str, submit: bool = True) -> dict:
    return _fill(ws, "username", login, submit=submit)


def fill_password(ws: str, password: str, submit: bool = True) -> dict:
    return _fill(ws, "password", password, submit=submit)


def rank_login_candidate(url: str, step: str, visible: bool = False, prefer_host: str | None = None) -> int:
    """Higher wins. Leftover file:// fixtures lose to the real host."""
    u = (url or "").lower()
    score = 0
    if step in ("username", "password", "2fa", "sso"):
        score += 10
    elif any(s in u for s in ("/login", "signin", "sign-in", "accounts.", "/auth")):
        score += 3
    if visible:
        score += 8
    host = (prefer_host or "").lower().removeprefix("www.")
    if host and host in u:
        score += 6
    leftover = u.startswith("file:") or "prims-fixture" in u or "/fixture/login" in u
    if leftover and host and host not in ("prims-fixture", "127.0.0.1", "localhost"):
        score -= 5
    return score


def find_login_page(cdp_base: str, prefer_host: str | None = None) -> tuple[dict | None, dict]:
    """Prefer a tab that is actually a login/2FA form for this host."""
    pages = cdp_lib.pages(cdp_base)
    visible = cdp_lib.visible_page(cdp_base, pages)
    vis_id = (visible or {}).get("id")
    ranked: list[tuple[int, dict, dict]] = []
    for p in pages:
        ws = p.get("ws")
        if not ws:
            continue
        form = inspect_form(ws)
        score = rank_login_candidate(
            p.get("url") or "",
            form.get("step") or "other",
            visible=p.get("id") == vis_id,
            prefer_host=prefer_host,
        )
        if score > 0:
            ranked.append((score, p, form))
    ranked.sort(key=lambda row: -row[0])
    if not ranked:
        return None, {"step": "other"}
    return ranked[0][1], ranked[0][2]


def bring_login_front(cdp_base: str, page: dict) -> None:
    if not page or not page.get("id"):
        return
    try:
        cdp_lib.activate(cdp_base, page["id"])
    except Exception:
        pass
    ws = page.get("ws")
    if ws:
        try:
            cdp_lib.call(ws, "Page.bringToFront")
        except Exception:
            pass


def act(ws: str, user: str, password: str) -> dict:
    """One tick: fill whatever page is showing, using the remembered username."""
    form = inspect_form(ws)
    step = form.get("step") or "other"
    out = {
        "step": step,
        "hasUser": form.get("hasUser"),
        "hasPass": form.get("hasPass"),
        "hasOtp": form.get("hasOtp"),
        "hasSso": form.get("hasSso"),
        "remembered": form.get("remembered"),
        "href": form.get("href"),
        "title": form.get("title"),
    }
    if step == "2fa":
        return {**out, "action": "wait-2fa", "ok": True}
    if step == "sso":
        return {**out, "action": "wait-sso", "ok": True}
    if step == "username":
        r = fill_username(ws, user, submit=True)
        return {**out, "action": "username", **r}
    if step == "password":
        if form.get("hasUser"):
            fill_username(ws, user, submit=False)
        r = fill_password(ws, password, submit=True)
        return {**out, "action": "password", **r}
    return {**out, "action": "none", "ok": True}


def should_ask(prev: str | None) -> bool:
    return prev not in ("pending", "approved", "denied")


def decide_login(busy: bool, recs: list[dict]) -> tuple[str, str | None]:
    """Minimize clicks: one saved password for this host → fill it. Else ask."""
    if busy:
        return "skip", None
    usable = [r for r in recs if r.get("has_password") and r.get("id")]
    if len(usable) == 1:
        return "auto", usable[0]["id"]
    return "ask", None


def next_login(busy: bool, prev: str | None, recs: list[dict]) -> tuple[str, str | None]:
    if busy or not should_ask(prev):
        return "skip", None
    return decide_login(False, recs)


DISMISS_JS = r"""
(() => {
  const shown = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const label = (el) => ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').trim();
  const btns = [...document.querySelectorAll('button, [role=button], input[type=button], a')].filter(shown);
  const stay = btns.find(b => /^(stay signed in|keep me signed in)$/i.test(label(b)));
  if (stay) { stay.click(); return {ok:true, kind:'stay', t: label(stay).slice(0,40)}; }
  const yes = btns.find(b => /^yes$/i.test(label(b)));
  if (yes) {
    const blob = ((document.body && document.body.innerText) || '').slice(0, 500).toLowerCase();
    if (/stay signed in|keep me signed in|stay signed-in/.test(blob)) {
      yes.click();
      return {ok:true, kind:'stay', t: 'Yes'};
    }
  }
  const skip = btns.find(b => {
    const t = label(b).toLowerCase();
    return t === 'not now' || t === 'never' || t === 'skip' || t === 'no thanks'
      || t === "don't use" || t === 'use password instead' || t === 'not this time'
      || t === 'never save' || t === 'save later' || t === 'no, thanks';
  });
  if (skip) { skip.click(); return {ok:true, kind:'skip', t: label(skip).slice(0,40)}; }
  return {ok:false};
})()
"""


def dismiss_prompts(ws: str) -> dict:
    try:
        r = cdp_lib.call(ws, "Runtime.evaluate", {"expression": DISMISS_JS, "returnByValue": True})
        val = (r or {}).get("result", {}).get("value")
        return val if isinstance(val, dict) else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

