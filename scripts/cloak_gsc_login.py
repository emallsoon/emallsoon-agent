#!/usr/bin/env python3
"""CloakBrowser 版 GSC 登录/验证（幂等）。

用法：
  python3 scripts/cloak_gsc_login.py           # 已登录则只验证+备份；未登录则走完整流程
  python3 scripts/cloak_gsc_login.py --force   # 强制重新走登录流程

2026-08-30 实测：CloakBrowser(146, humanize=True) 恢复 cookie 后走
账号选择器 -> 密码 -> 直接进 Search Console，未触发 reCAPTCHA Enterprise
（裸 Chrome 同流程被 reCAPTCHA 卡死）。TOTP 为备用分支，正常密码后直达。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloak_common import setup_env, PROFILE, AUTH, restore_cookies, backup_cookies, load_creds

setup_env()
import pyotp
from cloakbrowser import launch_persistent_context

FORCE = "--force" in sys.argv
creds = load_creds()
EMAIL = creds["GSC_EMAIL"]
PASSWORD = creds["GSC_PASSWORD"]
TOTP = creds.get("GSC_TOTP_SECRET", "")


def shot(p, name):
    p.screenshot(path=f"/workspace/gsc-cloak-{name}.png")


ctx = launch_persistent_context(PROFILE, headless=True, humanize=True)
page = ctx.pages[0] if ctx.pages else ctx.new_page()
restored = restore_cookies(ctx)
print(f"cookie 恢复: {restored} 条（罐内现有 {len(ctx.cookies())}）")

LOGIN = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fsearch.google.com%2Fsearch-console&hl=en"
page.goto(LOGIN, timeout=90000, wait_until="domcontentloaded")
page.wait_for_timeout(3500)

logged_in = "accounts.google.com" not in page.url
if logged_in and not FORCE:
    print(f"✅ 已是登录态，直接进入: {page.url}")
else:
    # 1) 账号选择器（恢复过 cookie 常见）
    cho = page.query_selector(f"div[data-email='{EMAIL}']")
    if cho:
        print("→ 账号选择器：点击已有账号")
        cho.click()
        page.wait_for_timeout(3000)
        shot(page, "02-chooser")

    # 2) 邮箱（没有选择器时）
    try:
        page.wait_for_selector("input[type=email]", timeout=6000)
        page.fill("input[type=email]", EMAIL)
        page.wait_for_timeout(800)
        page.locator("#identifierNext button, #identifierNext").first.click()
        print("→ 邮箱已填，点了 Next")
        page.wait_for_timeout(4000)
        shot(page, "03-email-next")
    except Exception:
        pass  # 走了选择器就没有邮箱页

    # 3) 密码
    page.wait_for_selector("input[type=password]", timeout=12000)
    page.fill("input[type=password]", PASSWORD)
    page.wait_for_timeout(900)
    page.locator("#passwordNext button, #passwordNext").first.click()
    print("→ 密码已填，点了 Next")
    page.wait_for_timeout(5000)
    shot(page, "04-pwd-next")

    # 4) 轮询挑战：TOTP / reCAPTCHA / 直达
    totp_done = False
    for i in range(30):
        page.wait_for_timeout(3000)
        u = page.url
        if "accounts.google.com" not in u:
            print(f"✅ 登录成功：{u}")
            break
        if not totp_done and page.query_selector("input#totpPin"):
            code = pyotp.TOTP(TOTP).now()
            page.fill("input#totpPin", code)
            page.wait_for_timeout(700)
            page.locator("#totpNext button, #totpNext").first.click()
            totp_done = True
            print(f"→ TOTP {code} 已填")
            continue
        if i in (4, 10, 16, 22, 29):
            err = page.evaluate("""() => {
              for (const s of ['.o6cuMc', '[role=alert]', '.yKBrSe']) {
                const el = document.querySelector(s);
                if (el && el.innerText.trim().length > 8) return el.innerText.trim().slice(0, 150);
              }
              return '';
            }""")
            print(f"  [{i}] url={u[:70]} err={err!r}")

shot(page, "07-final")
final = page.url
print("最终 URL:", final)

if "accounts.google.com" not in final:
    fn, total = backup_cookies(ctx, tag="cloak-gsc")
    print(f"✅ 已备份 {total} 条 cookie -> {fn}")
    # 顺手验证资源页可打开
    page.goto("https://search.google.com/search-console?resource_id=sc-domain:emallsoon.com",
              timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    shot(page, "08-console")
    print("GSC 页面标题:", page.title(), "| URL:", page.url)
    rc = 0
else:
    print("❌ 仍停留在 Google 登录域，未成功（查看 /workspace/gsc-cloak-07-final.png）")
    rc = 1

ctx.close()
sys.exit(rc)
