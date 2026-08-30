#!/usr/bin/env python3
# cdp_cookies.py — 通过 CDP Storage API 完整备份/恢复浏览器 cookie（含 httpOnly）
#
# 为什么不用 document.cookie：拿不到 httpOnly 的会话 cookie（Google 的
# __Secure-1PSID、Bing 的 ANON/_SS 等），无法真正恢复登录态。
# CDP Storage.getCookies / Storage.setCookies 可按 browserContext 完整读写。
#
# 用法：
#   python3 scripts/cdp_cookies.py backup  [--port 9223] [--out DIR]   # 备份全部 cookie
#   python3 scripts/cdp_cookies.py restore [--port 9223] --file F      # 幂等恢复
#   python3 scripts/cdp_cookies.py list    [--port 9223]               # 概览
#
# 备份文件含敏感凭据，默认写入 /workspace/.browser-auth/（chmod 700，不在 git 仓库内）。

import argparse
import datetime
import json
import os
import sys
import urllib.request

try:
    import websocket  # pip install websocket-client
except ImportError:
    sys.exit("需要 websocket-client：pip install websocket-client --break-system-packages")

DEFAULT_OUT = "/workspace/.browser-auth"

# setCookies 接受的字段白名单
SET_FIELDS = (
    "name", "value", "domain", "path", "secure", "httpOnly",
    "sameSite", "expires", "sourceScheme", "sourcePort",
    "priority", "sameParty", "partitionKey",
)


class CDP:
    def __init__(self, port):
        ver = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version"))
        self.ws = websocket.create_connection(
            ver["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self._id = 0
        self.browser = ver.get("Browser", "?")

    def call(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def contexts(self):
        return self.call("Target.getBrowserContexts").get("browserContextIds", [])

    def get_cookies(self, ctx=None):
        return self.call("Storage.getCookies", {"browserContextId": ctx} if ctx else {}).get("cookies", [])

    def set_cookies(self, cookies, ctx=None):
        clean = [{k: c[k] for k in SET_FIELDS if k in c and c[k] is not None} for c in cookies]
        params = {"cookies": clean}
        if ctx:
            params["browserContextId"] = ctx
        return self.call("Storage.setCookies", params)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def cmd_backup(port, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    os.chmod(out_dir, 0o700)
    cdp = CDP(port)
    payload = {
        "kind": "cdp-cookies-backup",
        "browser": cdp.browser,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "contexts": {"default": None, **{cid: cid for cid in cdp.contexts()}},
        "cookies_by_context": {},
    }
    total = 0
    for label, cid in payload["contexts"].items():
        cs = cdp.get_cookies(cid)
        payload["cookies_by_context"][label] = cs
        total += len(cs)
        print(f"[{label}] {len(cs)} cookies")
    name = f"cookies-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    path = os.path.join(out_dir, name)
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.chmod(path, 0o600)
    # 同时维护 latest.json 指向最新备份
    latest = os.path.join(out_dir, "latest.json")
    with open(latest, "w") as f:
        json.dump({"file": name, "created_at": payload["created_at"], "total": total}, f)
    os.chmod(latest, 0o600)
    print(f"OK backup -> {path} ({total} cookies)")
    cdp.close()
    return 0


def cmd_restore(port, file):
    with open(file) as f:
        payload = json.load(f)
    if payload.get("kind") != "cdp-cookies-backup":
        sys.exit("文件格式不正确（缺少 kind=cdp-cookies-backup）")
    cdp = CDP(port)
    existing = {c["name"] + "|" + c["domain"] + "|" + c.get("path", "/") for c in cdp.get_cookies()}
    restored = skipped = 0
    for label, cid in payload["contexts"].items():
        cookies = payload["cookies_by_context"].get(label, [])
        if not cookies:
            continue
        cdp.set_cookies(cookies, cid)
        for c in cookies:
            key = c["name"] + "|" + c["domain"] + "|" + c.get("path", "/")
            if key in existing:
                skipped += 1
            else:
                restored += 1
    print(f"OK restore: {restored} new, {skipped} already-present (idempotent)")
    cdp.close()
    return 0


def cmd_list(port):
    cdp = CDP(port)
    print("Browser:", cdp.browser)
    for label, cid in {"default": None, **{c: c for c in cdp.contexts()}}.items():
        cs = cdp.get_cookies(cid)
        domains = {}
        http_only = 0
        for c in cs:
            domains.setdefault(c["domain"].lstrip("."), 0)
            domains[c["domain"].lstrip(".")] += 1
            if c.get("httpOnly"):
                http_only += 1
        print(f"[{label}] {len(cs)} cookies (httpOnly={http_only})")
        for d, n in sorted(domains.items(), key=lambda x: -x[1]):
            print(f"    {d}: {n}")
    cdp.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backup", "restore", "list"])
    ap.add_argument("--port", type=int, default=9223)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--file", help="restore 用的备份文件")
    a = ap.parse_args()
    if a.cmd == "backup":
        return cmd_backup(a.port, a.out)
    if a.cmd == "restore":
        if not a.file:
            a.file = os.path.join(a.out, "latest.json")
            if os.path.exists(a.file):
                with open(a.file) as f:
                    a.file = os.path.join(a.out, json.load(f)["file"])
        return cmd_restore(a.port, a.file)
    return cmd_list(a.port)


if __name__ == "__main__":
    sys.exit(main())
