#!/usr/bin/env python3
"""GSC 登录 v9：GUI 模式下 reCAPTCHA 处理 + 图片挑战截图（供用户点选）"""
import sys, time, json, base64, os
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page
import pyotp

CREDS = dict(l.strip().split("=", 1) for l in open("/workspace/.browser-auth/credentials.env") if "=" in l)
EMAIL, PASSWORD, TOTP = CREDS["GSC_EMAIL"], CREDS["GSC_PASSWORD"], CREDS["GSC_TOTP_SECRET"]
SHOT_DIR = "/workspace/.browser-auth"

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

def find_tg(p, part):
    for t in p.bcall("Target.getTargets").get("targetInfos", []):
        if part in t.get("url", ""):
            return t
    return None

def rc_eval(p, tg, js):
    r = p.bcall("Target.attachToTarget", {"targetId": tg["targetId"], "flatten": True})
    sid = r["sessionId"]
    pid = p._bid + 1
    p.bws.send(json.dumps({"id": pid, "method": "Runtime.evaluate",
                           "params": {"expression": js, "returnByValue": True, "awaitPromise": True},
                           "sessionId": sid}))
    while True:
        m = json.loads(p.bws.recv())
        if m.get("id") == pid:
            if "error" in m: return "ERR"
            if "exceptionDetails" in m.get("result", {}):
                return "EXC"
            return m["result"].get("result", {}).get("value", "?")[:120]

def shot(p, name):
    """整页截图保存（GUI 模式下含 reCAPTCHA 挑战画面）"""
    r = p.pcall("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = r.get("data", "")
    if not data:
        # 换 viewport 全量
        r = p.pcall("Page.captureScreenshot", {"format": "png"})
        data = r.get("data", "")
    path = os.path.join(SHOT_DIR, name)
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    print("saved:", path)
    return path

def rc_click_checkbox(p):
    """点击 checkbox，返回 True=已过 / 'challenge'=图片挑战 / False=失败"""
    tg = find_tg(p, "recaptcha/anchor")
    if not tg:
        return "NO_ANCHOR"
    for i in range(8):
        st = rc_eval(p, tg, """(() => {
          const box = document.querySelector('.recaptcha-checkbox');
          if (!box) return 'NOBOX';
          const a = box.getAttribute('aria-checked');
          if (a === 'true') return 'ALREADY';
          box.click();
          return 'CLICKED';
        })()""")
        print(f"  anchor[{i}]:", st)
        if st == "ALREADY":
            return True
        if st == "CLICKED":
            time.sleep(3)
            break
        time.sleep(2)
    # 检查是否进入图片挑战（bframe 有 rc-imageselect 等）
    tg2 = find_tg(p, "recaptcha/bframe")
    if tg2:
        st = rc_eval(p, tg2, """(() => {
          const b = document.body;
          const sel = document.querySelector('.rc-imageselect, .rc-image-tile, img[class*=rc]');
          const help = document.querySelector('.rc-challenge-help');
          return JSON.stringify({challenge: !!sel, help: !!help,
                                 txt: (b ? b.innerText : '').slice(0,120).replace(/\\n+/g,'|')});
        })()""")
        print("  bframe:", st)
        if st and '"challenge":true' in st:
            return "challenge"
    # checkbox 是否变绿（已验证）
    tg3 = find_tg(p, "recaptcha/anchor")
    if tg3:
        st = rc_eval(p, tg3, """(() => {
          const box = document.querySelector('.recaptcha-checkbox');
          return box ? box.getAttribute('aria-checked') : 'gone';
        })()""")
        print("  anchor-state:", st)
        if st == "true":
            return True
    return "challenge"

p = Page(9223)
url = p.goto("https://accounts.google.com/ServiceLogin?hl=en"
             "&continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console")
print("goto:", url[:90])
time.sleep(2)
t = body_text(p, 1200)

# 账号选择 / 邮箱
import re
if "choose an account" in t.lower():
    r = p.eval_js(f"""(() => {{
      const el = document.querySelector("div[data-email='{EMAIL}']");
      if (el) {{ el.click(); return 'OK'; }} return 'NOEL';
    }})()""")
    print("chooser:", r)
    time.sleep(3)
    t = body_text(p, 1200)
if "enter your email" in t.lower() or "sign in" in t.lower():
    if p.eval_js("!!document.querySelector('input#identifierId')"):
        print("email:", set_val(p, "input#identifierId", EMAIL))
        time.sleep(0.5)
        click_sel(p, "#identifierNext button, #identifierNext")
        time.sleep(3)

# 密码
if p.eval_js("!!document.querySelector('input[type=password]')"):
    print("pwd:", set_val(p, "input[type=password]", PASSWORD))
    time.sleep(0.5)
    click_sel(p, "#passwordNext button, #passwordNext")
    time.sleep(4)

t = body_text(p, 1500)
print("stage:", t[:200])

# reCAPTCHA 处理
if "verify it" in t.lower() or "not a robot" in t.lower():
    print(">>> reCAPTCHA 出现，GUI 模式点击 checkbox")
    r = rc_click_checkbox(p)
    print("rc result:", r)
    if r == "challenge":
        print(">>> 图片挑战：截图给用户")
        shot(p, "recaptcha-challenge.png")
        print("WAIT_USER")
        # 等待用户点选后继续（脚本在此暂停，由主流程接管）
    else:
        time.sleep(1)
        print("next:", click_sel(p, "#identifierNext button, #passwordNext button, button[jsname]") if False else "OK")
        # 点 Next（挑战页按钮）
        p.eval_js("""(() => {
          const btns = [...document.querySelectorAll('button, [role=button]')];
          const b = btns.find(x => /next/i.test(x.innerText||''));
          if (b) b.click();
        })()""")
        time.sleep(5)
        t = body_text(p, 1200)
        print("after-rc:", t[:220])

# TOTP
if any(k in t.lower() for k in ["2-step", "two-step", "enter the code", "verify", "authenticator"]):
    code = pyotp.TOTP(TOTP).now()
    print("totp:", code, set_val(p, "input#totpPin, input[name=Pin], input[type=tel]", code))
    time.sleep(0.5)
    click_sel(p, "#totpNext button, button[jsname]")
    time.sleep(5)
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
