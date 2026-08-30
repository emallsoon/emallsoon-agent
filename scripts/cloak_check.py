#!/usr/bin/env python3
"""双平台登录态巡检：GSC（Google）+ BWT（Microsoft/Bing）。

用法：python3 scripts/cloak_check.py
输出：两个平台的登录判定 + 截图 /workspace/cloak-check-{gsc,bwt}.png
退出码：0 全部在线；1 至少一个离线
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloak_common import setup_env, PROFILE, restore_cookies

setup_env()
from cloakbrowser import launch_persistent_context

results = {}
ctx = launch_persistent_context(PROFILE, headless=True, humanize=True)
page = ctx.pages[0] if ctx.pages else ctx.new_page()
n = restore_cookies(ctx)
print(f"cookie 恢复: {n} 条")

# ---- GSC ----
try:
    page.goto("https://search.google.com/search-console?resource_id=sc-domain:emallsoon.com",
              timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.screenshot(path="/workspace/cloak-check-gsc.png")
    on_google_login = "accounts.google.com" in page.url
    body = page.inner_text("body")[:400].replace("\n", " ")
    gsc_ok = (not on_google_login) and ("Start now" not in body or "emallsoon" in body)
    results["GSC"] = ("✅ 在线" if gsc_ok else "❌ 离线") + f" | {page.url[:80]}"
    if on_google_login:
        results["GSC"] = "❌ 被重定向到 Google 登录页"
except Exception as e:
    results["GSC"] = f"❌ 异常: {type(e).__name__} {str(e)[:80]}"

# ---- BWT ----
try:
    page.goto("https://www.bing.com/webmasters", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    page.screenshot(path="/workspace/cloak-check-bwt.png")
    on_ms_login = any(d in page.url for d in ("login.live.com", "login.microsoftonline.com"))
    name = page.evaluate("""() => {
      // SERP 用 #id_l；webmasters/microsoft 域用 meControl（#mectrl_main / #msameHeader）
      const el = document.querySelector('#id_l, #mectrl_main, #msameHeader, #mectrl_currentAccount');
      return el ? el.innerText.trim() : '';
    }""")
    body_l = page.inner_text("body")[:400].lower()
    dashboard_markers = ("legacy soap", "url inspection", "sitemaps", "performance", "emallsoon")
    if on_ms_login:
        results["BWT"] = "❌ 被重定向到微软登录页"
    elif name and ("ren jie" in name.lower() or "@" in name or len(name) < 40):
        results["BWT"] = f"✅ 在线（账号名: {name!r}）"
    elif any(m in body_l for m in dashboard_markers):
        results["BWT"] = "✅ 在线（仪表盘内容可见，账号控件未渲染完）"
    else:
        results["BWT"] = f"❌ 离线（无账号名）body={body_l[:60]!r}"
except Exception as e:
    results["BWT"] = f"❌ 异常: {type(e).__name__} {str(e)[:80]}"

ctx.close()
print("=" * 46)
for k, v in results.items():
    print(f"  {k}: {v}")
print("=" * 46)
sys.exit(0 if all(v.startswith("✅") for v in results.values()) else 1)
