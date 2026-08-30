#!/usr/bin/env python3
"""走到 Verify it's you 页并截图 + dump（GUI 模式）"""
import sys, time, json, base64
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page

CREDS = dict(l.strip().split("=", 1) for l in open("/workspace/.browser-auth/credentials.env") if "=" in l)
EMAIL, PASSWORD = CREDS["GSC_EMAIL"], CREDS["GSC_PASSWORD"]

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

p = Page(9223)
p.goto("https://accounts.google.com/ServiceLogin?hl=en&continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console")
time.sleep(2.5)
t = (p.eval_js("document.body.innerText") or "")
if "choose an account" in t.lower():
    p.eval_js(f"""(() => {{ const el = document.querySelector("div[data-email='{EMAIL}']"); if (el) el.click(); }})()""")
    time.sleep(3)
if p.eval_js("!!document.querySelector('input#identifierId')"):
    print("email:", set_val(p, "input#identifierId", EMAIL)); time.sleep(0.5)
    click_sel(p, "#identifierNext button, #identifierNext"); time.sleep(3)
if p.eval_js("!!document.querySelector('input[type=password]')"):
    print("pwd:", set_val(p, "input[type=password]", PASSWORD)); time.sleep(0.5)
    click_sel(p, "#passwordNext button, #passwordNext"); time.sleep(5)

# 挑战页状态
t = (p.eval_js("document.body.innerText") or "").replace("\n", " | ")[:400]
print("page:", t)
print("url:", p.eval_js("location.href")[:100])
print("iframes:", p.eval_js("(() => [...document.querySelectorAll('iframe')].map(f=>(f.src||'').slice(0,90)))()"))
# 所有可点击元素
els = p.eval_js(r"""
(() => {
  const out = [];
  document.querySelectorAll('button, a, [role=button], [role=link], [data-identifier], li').forEach(e => {
    const tx = (e.innerText||'').trim().replace(/\s+/g,' ').slice(0,60);
    if (tx && tx.length > 1) out.push({tag: e.tagName, t: tx, href: (e.href||'').slice(0,60)});
  });
  const seen = new Set();
  return out.filter(x => { if (seen.has(x.t)) return false; seen.add(x.t); return true; }).slice(0, 20);
})()
""")
print("clickables:", json.dumps(els, ensure_ascii=False, indent=1))
# 截图
r = p.pcall("Page.captureScreenshot", {"format": "png"})
open("/workspace/.browser-auth/gui-challenge.png", "wb").write(base64.b64decode(r["data"]))
print("shot saved")
p.close()
