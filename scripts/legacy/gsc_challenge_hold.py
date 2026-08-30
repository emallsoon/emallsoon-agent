#!/usr/bin/env python3
"""重新走到 reCAPTCHA 挑战页，等 iframe 加载，标注 checkbox 坐标后截图"""
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

p = Page(9223)
p.goto("https://accounts.google.com/ServiceLogin?hl=en&continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console")
time.sleep(2)
t = (p.eval_js("document.body.innerText") or "")
if "choose an account" in t.lower():
    p.eval_js(f"""(() => {{ const el = document.querySelector("div[data-email='{EMAIL}']"); if (el) el.click(); }})()""")
    time.sleep(3)
if p.eval_js("!!document.querySelector('input#identifierId')"):
    set_val(p, "input#identifierId", EMAIL); time.sleep(0.5)
    click_sel(p, "#identifierNext button, #identifierNext"); time.sleep(3)
if p.eval_js("!!document.querySelector('input[type=password]')"):
    set_val(p, "input[type=password]", PASSWORD); time.sleep(0.5)
    click_sel(p, "#passwordNext button, #passwordNext"); time.sleep(5)

url = p.eval_js("location.href")
print("URL:", url[:100])
print("text:", (p.eval_js("document.body.innerText") or "").replace("\n"," | ")[:200])

# 等 recaptcha iframe 加载（最多 20s）
anchor_box = None
for i in range(12):
    fr = find_frame(p, "recaptcha/enterprise/anchor")
    if fr:
        r1 = p.pcall("Page.createIsolatedWorld", {"frameId": fr["id"], "worldName": "an"})
        ctx = r1["executionContextId"]
        r2 = p.pcall("Runtime.evaluate", {"expression": """(() => {
          const box = document.querySelector('.recaptcha-checkbox');
          if (!box) return null;
          const r = box.getBoundingClientRect();
          return JSON.stringify({x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                                 checked: box.getAttribute('aria-checked')});
        })()""", "contextId": ctx, "returnByValue": True})
        v = r2.get("result", {}).get("value")
        if v and v != "null":
            anchor_box = json.loads(v)
            print(f"[{i}] anchor loaded: {anchor_box}")
            break
    time.sleep(2)

# 截图
r = p.pcall("Page.captureScreenshot", {"format": "png"})
open("/workspace/gsc-challenge.png", "wb").write(base64.b64decode(r["data"]))
print("saved /workspace/gsc-challenge.png")

# bframe 挑战类型
bf = find_frame(p, "recaptcha/enterprise/bframe")
if bf:
    r1 = p.pcall("Page.createIsolatedWorld", {"frameId": bf["id"], "worldName": "bf"})
    ctx = r1["executionContextId"]
    r2 = p.pcall("Runtime.evaluate", {"expression": """(() => {
      const b = document.body;
      return JSON.stringify({
        tiles: document.querySelectorAll('.rc-image-tile, table.rc-imageselect-table img, img[class*=rc]').length,
        title: (b.innerText||'').slice(0,180).replace(/\\n+/g,'|')
      });
    })()""", "contextId": ctx, "returnByValue": True})
    print("bframe:", r2.get("result", {}).get("value"))
print("挑战页保持打开")
