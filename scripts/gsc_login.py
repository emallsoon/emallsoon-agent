#!/usr/bin/env python3
"""GSC 登录 v8：逐步等待元素（identifier → password → TOTP）"""
import sys, time, json
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page
import pyotp

CREDS = dict(l.strip().split("=", 1) for l in open("/workspace/.browser-auth/credentials.env") if "=" in l)
EMAIL, PASSWORD, TOTP = CREDS["GSC_EMAIL"], CREDS["GSC_PASSWORD"], CREDS["GSC_TOTP_SECRET"]

def has_sel(p, sel):
    return bool(p.eval_js(f"!!document.querySelector({sel!r})"))

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

def wait_sel(p, sel, timeout=25, poll=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if has_sel(p, sel):
            return True
        time.sleep(poll)
    return False

def body_text(p, n=300):
    return (p.eval_js("document.body ? document.body.innerText : ''") or "")[:n].replace("\n", " | ")

p = Page(9223)
url = p.goto("https://accounts.google.com/ServiceLogin?hl=en"
             "&continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console")
print("goto:", url[:100])
time.sleep(2)

# 若 accountchooser → 点账号
t = body_text(p, 1200)
if "choose an account" in t.lower():
    print("chooser detected")
    r = p.eval_js(f"""(() => {{
      const el = document.querySelector("div[data-email='{EMAIL}']");
      if (el) {{ el.click(); return 'OK'; }} return 'NOEL';
    }})()""")
    print("chooser:", r)
    time.sleep(4)

# 邮箱
if wait_sel(p, "input#identifierId"):
    print("email-box: yes")
    print("fill:", set_val(p, "input#identifierId", EMAIL))
    time.sleep(0.5)
    print("next:", click_sel(p, "#identifierNext button, #identifierNext"))
    # 等密码框
    if wait_sel(p, "input[type=password]", timeout=20):
        print("pwd-box: yes")
        print("fill:", set_val(p, "input[type=password]", PASSWORD))
        time.sleep(0.5)
        print("next:", click_sel(p, "#passwordNext button, #passwordNext"))
    else:
        print("pwd-box: NO →", body_text(p, 250))
else:
    print("email-box: NO →", body_text(p, 250))

# 等 TOTP 或成功跳转
t0 = time.time()
totp_done = False
while time.time() - t0 < 30:
    t = body_text(p, 900).lower()
    if has_sel(p, "input#totpPin"):
        code = pyotp.TOTP(TOTP).now()
        print("totp:", code, set_val(p, "input#totpPin, input[name=Pin]", code))
        time.sleep(0.5)
        click_sel(p, "#totpNext button, button[jsname]")
        time.sleep(4)
        totp_done = True
        break
    if "wrong password" in t or "couldn" in t and "sign you in" in t:
        print("LOGIN ERROR:", body_text(p, 250))
        break
    if "verify it" in t or "not a robot" in t:
        print("CHALLENGE:", body_text(p, 250))
        break
    time.sleep(1.5)

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
