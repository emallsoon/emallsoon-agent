#!/usr/bin/env python3
"""bing_login.py — 持久化浏览器(9223)登录 Bing Webmaster（MS 账号，备用恢复脚本）
流程：login.live.com 邮箱 → "Use your password" 绕过验证码 → 密码 → KMSI
      → bing.com/webmasters Sign In → 账户卡片 .signInCard[0] → 控制台
凭据读取 /workspace/.browser-auth/credentials.env（不入库）
用法: python3 scripts/bing_login.py
"""
import sys, time
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page

CREDS = dict(l.strip().split("=", 1) for l in open("/workspace/.browser-auth/credentials.env") if "=" in l)
EMAIL, PASSWORD = CREDS["BING_EMAIL"], CREDS["BING_PASSWORD"]
LOGIN_URL = ("https://login.live.com/login.srf?wa=wsignin1.0"
             "&wreply=https%3A%2F%2Fwww.bing.com%2Fwebmasters%2Fabout%3Fhl%3Den")

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

def click_first(p, pattern):
    return p.eval_js(f"""(() => {{
  const els = [...document.querySelectorAll('button, a, input[type=submit], [role=button], [type=button]')];
  const re = new RegExp({pattern!r}, 'i');
  const hit = els.find(e => {{
    const t = e.innerText || e.value || e.getAttribute('aria-label') || '';
    return re.test(t) && (e.offsetParent !== null || e.tagName === 'A');
  }});
  if (hit) {{ hit.click(); return 'OK:' + (hit.innerText||hit.value||'').trim().slice(0,30); }}
  return 'NOEL';
}})()""")

def body_text(p, n=400):
    return (p.eval_js("document.body ? document.body.innerText : ''") or "")[:n].replace("\n", " | ")

def wait_sel(p, sel, timeout=25, poll=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if has_sel(p, sel):
            return True
        time.sleep(poll)
    return False

p = Page(9223)
print("goto:", p.goto(LOGIN_URL)[:100])
time.sleep(2)

# 1) 邮箱
if wait_sel(p, "input#usernameEntry, input[name=loginfmt], input[type=email]"):
    print("email:", set_val(p, "input#usernameEntry, input[name=loginfmt], input[type=email]", EMAIL))
    time.sleep(0.5)
    print("next:", click_first(p, "^next$"))
else:
    print("email-box: NO →", body_text(p, 200))

# 2) verify email 墙 → Use your password
t0 = time.time()
while time.time() - t0 < 25:
    t = body_text(p, 600).lower()
    if has_sel(p, "input[type=password], input[name=passwd]"):
        break
    if "verify your email" in t or "send code" in t:
        print("verify-wall:", click_first(p, "use your password|使用密码"))
        time.sleep(2)
        if has_sel(p, "input[type=password], input[name=passwd]"):
            break
    time.sleep(1)

# 3) 密码
if wait_sel(p, "input[type=password], input[name=passwd]", timeout=15):
    print("pwd:", set_val(p, "input[type=password], input[name=passwd]", PASSWORD))
    time.sleep(0.5)
    print("next:", click_first(p, "^(sign in|next|登录)$"))
else:
    print("pwd-box: NO →", body_text(p, 200))

# 4) Stay signed in → Yes
t0 = time.time()
while time.time() - t0 < 20:
    t = body_text(p, 600).lower()
    if "stay signed" in t:
        print("kmsi:", click_first(p, "^yes$|^是$"))
        break
    time.sleep(1.2)

# 5) 进 BWT → Sign In → 账户卡片
time.sleep(3)
print("goto:", p.goto("https://www.bing.com/webmasters")[:90])
time.sleep(5)
for i in range(8):
    st = p.eval_js("""(() => {
      const signIn = document.querySelector('button.signInButton, a.signInButton');
      const cards = document.querySelectorAll('.signInCard').length;
      const url = location.href;
      return {signIn: !!signIn, cards, url: url.slice(0,80)};
    })()""")
    if st["signIn"] and st["cards"] == 0:
        p.eval_js("document.querySelector('button.signInButton, a.signInButton')?.click()")
        time.sleep(2)
    elif st["cards"] > 0:
        r = p.eval_js("(() => { const c = document.querySelector('.signInCard'); if (c) { c.click(); return 'OK'; } return 'NO'; })()")
        print("card:", r)
        time.sleep(4)
        break
    elif "webmasters" in st["url"] and not st["signIn"]:
        print(">>> 已登录控制台:", st["url"])
        break
    time.sleep(1.5)

# 判定
time.sleep(3)
url = p.eval_js("location.href")
signin = p.eval_js("!!document.querySelector('button.signInButton, a.signInButton')")
print("final:", url[:90], "signIn:", signin)
print("RESULT:", "LOGGED_IN" if ("webmasters" in url and not signin) else "NOT_LOGGED_IN")
p.close()
