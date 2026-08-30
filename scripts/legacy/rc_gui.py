#!/usr/bin/env python3
"""GUI 模式 reCAPTCHA：frame tree 定位 anchor/bframe → 点击 checkbox → 检查挑战"""
import sys, time, json, base64
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page

def body_text(p, n=400):
    return (p.eval_js("document.body ? document.body.innerText : ''") or "")[:n].replace("\n", " | ")

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
        return "EXC:" + str(r2["exceptionDetails"].get("exception", {}).get("description", "?"))[:80]
    return r2.get("result", {}).get("value", "?")[:120]

p = Page(9223, attach="challenge/recaptcha")
print("URL:", p.eval_js("location.href")[:90])

# 找 anchor frame 点 checkbox
fr = find_frame(p, "recaptcha/enterprise/anchor")
print("anchor frame:", bool(fr))
if fr:
    st = frame_eval(p, fr["id"], """(() => {
      const box = document.querySelector('.recaptcha-checkbox');
      if (!box) return 'NOBOX';
      const a = box.getAttribute('aria-checked');
      if (a === 'true') return 'ALREADY';
      box.click();
      return 'CLICKED';
    })()""")
    print("click:", st)
    time.sleep(4)
    st2 = frame_eval(p, fr["id"], """(() => {
      const box = document.querySelector('.recaptcha-checkbox');
      return box ? 'checked=' + box.getAttribute('aria-checked') : 'gone';
    })()""")
    print("state:", st2)

# 检查 bframe 是否有图片挑战
bf = find_frame(p, "recaptcha/enterprise/bframe")
print("bframe:", bool(bf))
if bf:
    bt = frame_eval(p, bf["id"], """(() => {
      const b = document.body;
      const img = document.querySelector('.rc-image-tile, .rc-imageselect, img[src*="bframe"]');
      const help = document.querySelector('.rc-challenge-help');
      return JSON.stringify({img: !!img, help: !!help,
                             txt: (b?b.innerText:'').slice(0,150).replace(/\\n+/g,'|')});
    })()""")
    print("bframe-state:", bt)

# 截图
r = p.pcall("Page.captureScreenshot", {"format": "png"})
open("/workspace/.browser-auth/rc-gui.png", "wb").write(base64.b64decode(r["data"]))
print("shot: /workspace/.browser-auth/rc-gui.png")
print("page:", body_text(p, 300))
p.close()
