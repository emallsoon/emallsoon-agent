#!/usr/bin/env python3
"""cdp_page.py — 轻量 CDP 页面驱动：navigate / evaluate / attach（供登录自动化复用）"""
import json, sys, time, urllib.request
import websocket

def get_ws_browser(port):
    ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version"))
    return ver["webSocketDebuggerUrl"], ver.get("Browser", "?")

class Page:
    def __init__(self, port, attach=None, create=True):
        bws, browser = get_ws_browser(port)
        self.browser_name = browser
        self.bws = websocket.create_connection(bws, timeout=60, suppress_origin=True)
        self._bid = 0
        self.attached = False
        if attach:
            targets = self.bcall("Target.getTargets").get("targetInfos", [])
            t = next((t for t in targets if t.get("type") == "page" and attach in t.get("url", "")), None)
            if t:
                self.tid = t["targetId"]
                self.attached = True
        if not self.attached and create:
            r = self.bcall("Target.createTarget", {"url": "about:blank"})
            self.tid = r["targetId"]
        self.sess = None
        r3 = self.bcall("Target.attachToTarget", {"targetId": self.tid, "flatten": True})
        self.sess = r3["sessionId"]
        self.pcall("Runtime.enable")
        self.pcall("Page.enable")

    def bcall(self, method, params=None):
        self._bid += 1
        self.bws.send(json.dumps({"id": self._bid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.bws.recv())
            if m.get("id") == self._bid:
                if "error" in m: raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def pcall(self, method, params=None):
        self._bid += 1
        self.bws.send(json.dumps({"id": self._bid, "method": method,
                                  "params": params or {}, "sessionId": self.sess}))
        while True:
            m = json.loads(self.bws.recv())
            if m.get("id") == self._bid:
                if "error" in m: raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def goto(self, url, timeout=45):
        self.pcall("Page.navigate", {"url": url})
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(0.7)
            try:
                st = self.eval_js("document.readyState", await_promise=False)
                if st in ("interactive", "complete"):
                    time.sleep(0.6)
                    return self.eval_js("location.href", await_promise=False)
            except Exception:
                pass
        return self.eval_js("location.href", await_promise=False)

    def eval_js(self, expr, await_promise=True):
        r = self.pcall("Runtime.evaluate", {
            "expression": expr, "awaitPromise": await_promise,
            "returnByValue": True, "userGesture": True})
        if "exceptionDetails" in r:
            return {"__error__": r["exceptionDetails"].get("exception", {}).get("description", "error")}
        return r.get("result", {}).get("value")

    def close(self):
        if not self.attached:
            try: self.bcall("Target.closeTarget", {"targetId": self.tid})
            except Exception: pass
        self.bws.close()

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9223)
    ap.add_argument("--url", default="https://www.google.com/")
    ap.add_argument("--js", default="null")
    a = ap.parse_args()
    p = Page(a.port)
    print("goto:", p.goto(a.url))
    time.sleep(1.5)
    print("title:", p.eval_js("document.title"))
    if a.js != "null":
        print("js:", p.eval_js(a.js))
    p.close()

if __name__ == "__main__":
    main()
