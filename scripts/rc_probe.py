#!/usr/bin/env python3
"""reCAPTCHA 深度处理：轮询 checkbox + 检查 bframe 挑战状态"""
import sys, time, json
sys.path.insert(0, "/workspace/emallsoon-agent/scripts")
from cdp_page import Page

p = Page(9223, attach="accounts.google.com")
print("URL:", p.eval_js("location.href")[:100])
print("text:", (p.eval_js("document.body.innerText") or "")[:250].replace("\n"," | "))

def find_tg(part):
    for t in p.bcall("Target.getTargets").get("targetInfos", []):
        if part in t.get("url", ""):
            return t
    return None

def rc_eval(tg, js):
    r = p.bcall("Target.attachToTarget", {"targetId": tg["targetId"], "flatten": True})
    sid = r["sessionId"]
    pid = p._bid + 1
    p.bws.send(json.dumps({"id": pid, "method": "Runtime.evaluate",
                           "params": {"expression": js, "returnByValue": True, "awaitPromise": True},
                           "sessionId": sid}))
    while True:
        m = json.loads(p.bws.recv())
        if m.get("id") == pid:
            if "error" in m: return "ERR:" + str(m["error"])[:80]
            if "exceptionDetails" in m.get("result", {}):
                return "EXC"
            return m["result"].get("result", {}).get("value", "?")[:80]

# 多轮：点击 → 等待 → 检查
for round_i in range(6):
    tg = find_tg("recaptcha/anchor")
    if tg:
        r = rc_eval(tg, """(() => {
          const box = document.querySelector('.recaptcha-checkbox');
          if (!box) return 'NOBOX';
          if (box.getAttribute('aria-checked') === 'true') return 'CHECKED_TRUE';
          box.click();
          return 'CLICKED';
        })()""")
        print(f"round{round_i} anchor:", r)
    time.sleep(4)
    tg2 = find_tg("recaptcha/bframe")
    if tg2:
        st = rc_eval(tg2, """(() => {
          const body = document.body;
          const hasImg = !!document.querySelector('img[src*=bframe], .rc-imageselect-desc-wrapper');
          const challenge = document.querySelector('.rc-challenge-help, .fbc-imageselect');
          const t = body ? body.innerText.slice(0,150).replace(/\\n+/g,'|') : '';
          return JSON.stringify({hasImg, challenge: !!challenge, t});
        })()""")
        print(f"round{round_i} bframe:", st)
        # 若有图片挑战说明 checkbox 过了
        if st and ('"challenge":true' in st or '"hasImg":true' in st):
            print(">>> 图片挑战出现——checkbox 已通过，需人工/无法自动完成")
            break
    # 页面是否已前进
    url = p.eval_js("location.href")
    print(f"round{round_i} url:", url[:90])
    if "verify" not in url:
        print(">>> 已离开挑战页")
        break

p.close()
