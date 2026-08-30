#!/usr/bin/env python3
"""GSC 登录 v10：GUI 模式完整流程（reCAPTCHA checkbox 点击用 frame 方式）"""
import sys, time, json, base64
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page
import pyotp

CREDS = dict(l.strip().split("=", 1) for l in open("/workspace/.browser-auth/credentials.env") if "=" in l)
EMAIL, PASSWORD, TOTP = CREDS["GSC_EMAIL"], CREDS["GSC_PASSWORD"], CREDS["GSC_TOTP_SECRET"]

def body_text(p, n=400):
    return (p.eval_js("document.body ? document.body.innerText : ''") or "")[:n].replace("\n", " | ")

def set_val(p, sel, val):
    return p.eval_js(f"""(() => {{
  const el = document.querySelector({sel!r});
  if (!el) return 'NOEL';
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, {val!r});
  el.dispatchEvent(new Event('input', {{bubbles:true}}));
  el.dispatchEvent(new Event('change', {{bubbles:true}}));
  return 'OK';
}})()""")

def click_sel(p, sel):
    return p.eval_js(f"""(() => {{
  const el = document.querySelector({sel!r});
  if (el) {{ el.click(); return 'OK'; }} return 'NOEL';
}})()""")

def click_text(p, pattern):
    return p.eval_js(f"""(() => {{
  const els = [...document.querySelectorAll('button, [role=button], a')];
  const re = new RegExp({pattern!r}, 'i');
  const hit = els.find(e => re.test(e.innerText||''));
  if (hit) {{ hit.click(); return 'OK'; }} return 'NOEL';
}})()""")

def find_frame(p, url_part):
    tree = p.pcall("Page.getFrameTree")["frameTree"]
    def walk(n):
        fr = n["frame"]
        if url_part in fr.get("url", ""):
            return fr
        for c in n.get("childFrames", []):
            r = walk(c)
            if r: return r
        return None
    return walk(tree)

def frame_eval(p, fid, js):
    r1 = p.pcall("Page.createIsolatedWorld", {"frameId": fid, "worldName": "w", "grantUniveralAccess": True})
    ctx = r1["executionContextId"]
    r2 = p.pcall("Runtime.evaluate", {"expression": js, "contextId": ctx, "returnByValue": True, "awaitPromise": True})
    if "exceptionDetails" in r2:
        return "EXC"
    return r2.get("result", {}).get("value", "?")[:120]

def rc_solve(p):
    """点击 checkbox；返回 True/False"""
    for i in range(10):
        fr = find_frame(p, "recaptcha/enterprise/anchor")
        if not fr:
            time.sleep(1.5)
            continue
        st = frame_eval(p, fr["id"], """(() => {
          const box = document.querySelector('.recaptcha-checkbox');
          if (!box) return 'WAIT';
          if (box.getAttribute('aria-checked') === 'true') return 'ALREADY';
          box.click();
          return 'CLICKED';
        })()""")
        print(f"  rc[{i}]:", st)
        if st == "ALREADY":
            return True
        if st == "CLICKED":
            time.sleep(4)
            st2 = frame_eval(p, fr["id"], """(() => {
              const box = document.querySelector('.recaptcha-checkbox');
              return box ? box.getAttribute('aria-checked') : 'gone';
            })()""")
            print("  state:", st2)
            return st2 == "true"
        time.sleep(2)
    return False

p = Page(9223)
print("goto:", p.goto("https://accounts.google.com/ServiceLogin?hl=en"
                      "&continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console")[:90])
time.sleep(2)
t = body_text(p, 1200)
if "choose an account" in t.lower():
    p.eval_js(f"""(() => {{ const el = document.querySelector("div[data-email='{EMAIL}']"); if (el) el.click(); }})()""")
    print("chooser: OK"); time.sleep(3)
if p.eval_js("!!document.querySelector('input#identifierId')"):
    print("email:", set_val(p, "input#identifierId", EMAIL)); time.sleep(0.5)
    click_sel(p, "#identifierNext button, #identifierNext"); time.sleep(3)
if p.eval_js("!!document.querySelector('input[type=password]')"):
    print("pwd:", set_val(p, "input[type=password]", PASSWORD)); time.sleep(0.5)
    click_sel(p, "#passwordNext button, #passwordNext"); time.sleep(5)

t = body_text(p, 1500)
print("stage:", t[:180])

if "recaptcha" in p.eval_js("location.href") or "not a robot" in t.lower():
    print(">>> reCAPTCHA solve")
    ok = rc_solve(p)
    print("rc solved:", ok)
    time.sleep(2)
    print("next:", click_text(p, "^next$|^continue$"))
    time.sleep(5)
    t = body_text(p, 1500)
    print("after-rc:", t[:220])

if any(k in t.lower() for k in ["2-step", "two-step", "enter the code", "verify", "authenticator"]):
    code = pyotp.TOTP(TOTP).now()
    print("totp:", code, set_val(p, "input#totpPin, input[name=Pin], input[type=tel]", code))
    time.sleep(0.5)
    click_sel(p, "#totpNext button, button[jsname]")
    time.sleep(6)
    t = body_text(p, 1200)
    print("after-totp:", t[:220])

# 判定
p.goto("https://search.google.com/search-console?resource_id=sc-domain%3Aemallsoon.com&hl=en")
time.sleep(6)
url = p.eval_js("location.href")
print("final:", url)
t = body_text(p, 300)
print("text:", t[:180])
if url.startswith("https://search.google.com/search-console") and "about" not in url:
    print("RESULT: LOGGED_IN")
else:
    print("RESULT:", "NOT_LOGGED_IN" if "start now" in t.lower() else "UNCERTAIN")
p.close()
