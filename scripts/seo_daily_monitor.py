#!/usr/bin/env python3
"""SEO 日检：GSC（Google Search Console）+ BWT（Bing Webmaster Tools）数据监控。

用法：
  python3 scripts/seo_daily_monitor.py            # 全量监控（定时任务调用）
  python3 scripts/seo_daily_monitor.py --selftest # 仅验证环境（不抓数据）

输出（/workspace/seo-monitor/）：
  monitor-YYYYMMDD.json   结构化结果（指标 + 异常清单，供 AI 分析与修复）
  gsc-*-YYYYMMDD.png      GSC 各页截图证据
  bwt-YYYYMMDD.png        BWT 仪表盘截图证据
  latest.json             最新一次运行指针（diff 友好，只保留关键状态）

环境说明：完全本地化，沙盒重置后无需任何安装步骤（详见 cloak_common.py 头部注释）。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, "/workspace/.pylibs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloak_common import setup_env, PROFILE, restore_cookies, backup_cookies  # noqa: E402

setup_env()

OUT = "/workspace/seo-monitor"
GSC_RID = "sc-domain:emallsoon.com"
GSC_BASE = f"https://search.google.com/search-console"
BWT_BASE = "https://www.bing.com/webmasters"
SITE = "https://emallsoon.com"
DATE = time.strftime("%Y%m%d")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="仅验证环境，不抓数据")
    return ap.parse_args()


def selftest():
    """验证本地化浏览器链路：包 → 二进制 → 库 → profile。"""
    import cloakbrowser
    print(f"[1] 包: {os.path.dirname(cloakbrowser.__file__)}")
    print(f"[2] 缓存: {os.environ.get('CLOAKBROWSER_CACHE_DIR')}")
    print(f"[3] LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', '(未设置)')}")
    print(f"[4] profile: {PROFILE} 存在={os.path.isdir(PROFILE)}")
    t0 = time.time()
    from cloakbrowser import launch_persistent_context
    ctx = launch_persistent_context(PROFILE, headless=True)
    print(f"[5] 浏览器启动 {time.time() - t0:.1f}s ✓")
    ctx.close()
    print("SELFTEST PASS")
    return 0


def num(text, label):
    """从页面文本尽力提取 'label 后跟数字'（GSC/BWT 数字带千分位逗号）。"""
    m = re.search(re.escape(label) + r"[^\d\-]*([\d,]+(?:\.\d+)?)", text)
    return m.group(1).replace(",", "") if m else None


def grab_gsc(ctx, res, issues, shots):
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    g = res["gsc"]

    def visit(url, shot_name, wait=7000):
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(wait)
        p = os.path.join(OUT, f"gsc-{shot_name}-{DATE}.png")
        page.screenshot(path=p)
        shots.append(p)
        return page.inner_text("body")

    # ---- 概览/效果 ----
    body = visit(f"{GSC_BASE}?resource_id={GSC_RID}", "overview")
    g["logged_in"] = "accounts.google.com" not in page.url
    if not g["logged_in"]:
        issues.append("GSC: 登录态失效（被重定向到 Google 登录页），需人工重新登录")
        g["status"] = "login_required"
        return
    g["overview_url"] = page.url[:100]
    # 概览卡片真实文案："共有 N 次网页搜索点击"。注意后面紧跟日期(如 2026/8/29)，
    # 不能用宽松的"点击后取数字"，否则会把年份当成点击数。
    m = re.search(r"共有\s*([\d,]+)\s*次(?:网页搜索)?点击", body) or re.search(r"([\d,]+)\s+Clicks\b", body)
    g["clicks_28d"] = m.group(1).replace(",", "") if m else None
    m = re.search(r"共有\s*([\d,]+)\s*次展示", body) or re.search(r"([\d,]+)\s+Impressions\b", body)
    g["impressions_28d"] = m.group(1).replace(",", "") if m else None

    # ---- 索引覆盖率 ----
    try:
        body = visit(f"{GSC_BASE}/index?resource_id={GSC_RID}", "index", 8000)
        if "正在处理数据" in body:
            g["index_state"] = "processing"  # 新站常态：Google 仍在处理索引数据，非异常
        else:
            g["index_state"] = "ready"
            g["indexed_pages"] = num(body, "已编入索引") or num(body, "Indexed pages")
        err_m = re.search(r"(?:错误|Errors)[^\d]*(\d+)", body)
        g["index_errors"] = err_m.group(1) if err_m else None
        if g["index_errors"] and int(g["index_errors"]) > 0:
            issues.append(f"GSC: 索引覆盖存在 {g['index_errors']} 个错误项，需打开页面定位具体 URL")
    except Exception as e:
        issues.append(f"GSC: 索引页抓取失败 {type(e).__name__}")

    # ---- 站点地图 ----
    try:
        body = visit(f"{GSC_BASE}/sitemaps?resource_id={GSC_RID}", "sitemaps")
        bad = re.search(r"无法读取|Couldn't fetch|error", body, re.I)
        g["sitemap_ok"] = not bad
        if bad:
            issues.append("GSC: sitemap 状态异常（无法读取/错误），应重新提交 " + SITE + "/sitemap-index.xml")
    except Exception as e:
        issues.append(f"GSC: sitemap 页抓取失败 {type(e).__name__}")

    # ---- 手动操作 / 安全问题 ----
    try:
        body = visit(f"{GSC_BASE}/manual-actions?resource_id={GSC_RID}", "manual", 5000)
        # 页面真实文案："未检测到任何问题"（check_circle）
        no_issue = bool(re.search(r"未检测到任何问题|未发现|No issues|no manual", body, re.I))
        g["manual_actions_clean"] = no_issue
        if not no_issue:
            issues.append("GSC: 手动操作/处罚页面未确认干净，需人工查看截图")
    except Exception as e:
        issues.append(f"GSC: 手动操作页抓取失败 {type(e).__name__}")

    g["status"] = "ok"


def grab_bwt(ctx, res, issues, shots):
    page = ctx.new_page()
    b = res["bwt"]
    page.goto(f"{BWT_BASE}/dashboard?siteUrl={SITE}", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    p = os.path.join(OUT, f"bwt-dashboard-{DATE}.png")
    page.screenshot(path=p)
    shots.append(p)
    b["logged_in"] = not any(d in page.url for d in ("login.live.com", "login.microsoftonline.com"))
    if not b["logged_in"]:
        issues.append("BWT: 登录态失效（被重定向到微软登录页），需人工重新登录")
        b["status"] = "login_required"
        return
    body = page.inner_text("body")
    b["overview_url"] = page.url[:100]
    # BWT 仪表盘卡片：爬取信息/索引页数（尽力提取，DOM 多变）
    b["body_hint"] = body[:300].replace("\n", " ")
    b["status"] = "ok"

    # 站点地图
    try:
        page.goto(f"{BWT_BASE}/sitemap?siteUrl={SITE}", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        p2 = os.path.join(OUT, f"bwt-sitemap-{DATE}.png")
        page.screenshot(path=p2)
        shots.append(p2)
        b["sitemap_body"] = page.inner_text("body")[:300].replace("\n", " ")
    except Exception as e:
        issues.append(f"BWT: sitemap 页抓取失败 {type(e).__name__}")
    page.close()


def main():
    args = parse_args()
    if args.selftest:
        return selftest()

    os.makedirs(OUT, exist_ok=True)
    res = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "status": "ok",
        "gsc": {}, "bwt": {},
        "issues": [],
        "screenshots": [],
    }
    issues, shots = res["issues"], res["screenshots"]

    # ---- 站点本身可达性（监控前置：站挂了其他都无意义）----
    try:
        from cloakbrowser import launch
        b = launch(headless=True)
        pg = b.new_page()
        r = pg.goto(SITE, timeout=30000, wait_until="domcontentloaded")
        res["site_http"] = r.status if r else None
        if r and r.status >= 400:
            issues.append(f"站点不可达: HTTP {r.status} —— 需立即检查 Cloudflare Pages 部署状态")
        b.close()
    except Exception as e:
        issues.append(f"站点访问异常: {type(e).__name__} {str(e)[:80]}")
        res["site_http"] = None

    from cloakbrowser import launch_persistent_context
    try:
        ctx = launch_persistent_context(PROFILE, headless=True)
    except Exception as e:
        print(f"浏览器启动失败: {e}")
        res["status"] = "error"
        res["issues"].append(f"浏览器启动失败: {type(e).__name__}")
        return 2
    restore_cookies(ctx)

    try:
        grab_gsc(ctx, res, issues, shots)
        grab_bwt(ctx, res, issues, shots)
        backup_cookies(ctx)  # 顺带保鲜登录态
    except Exception as e:
        res["status"] = "error"
        issues.append(f"抓取过程异常中断: {type(e).__name__} {str(e)[:80]}")
    finally:
        ctx.close()

    # 注意：这里是元组成员判断（str in tuple），不要包 any() —— any(bool) 会 TypeError
    if "login_required" in (res["gsc"].get("status", ""), res["bwt"].get("status", "")):
        res["status"] = "login_required"
    elif res["status"] != "error" and issues:
        res["status"] = "issue"

    fn = os.path.join(OUT, f"monitor-{DATE}.json")
    with open(fn, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "latest.json"), "w") as f:
        json.dump({k: res[k] for k in ("date", "status", "site_http", "issues")},
                  f, ensure_ascii=False, indent=1)

    print("=" * 50)
    print(f"状态: {res['status']}  站点HTTP: {res['site_http']}")
    print(f"GSC: 登录={res['gsc'].get('logged_in')} 点击28d={res['gsc'].get('clicks_28d')} "
          f"已索引={res['gsc'].get('indexed_pages')} sitemap_ok={res['gsc'].get('sitemap_ok')}")
    print(f"BWT: 登录={res['bwt'].get('logged_in')}")
    for i, msg in enumerate(issues, 1):
        print(f"  ⚠️ [{i}] {msg}")
    if not issues:
        print("  ✅ 无异常")
    print(f"报告: {fn}")
    return 0 if res["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
