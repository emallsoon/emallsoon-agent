#!/usr/bin/env python3
"""费率联网校对：站点展示的费率 vs 官方来源（用于周期监控）。

用法：
  python3 scripts/fee_verify_monitor.py            # 联网抓官方页并比对
  python3 scripts/fee_verify_monitor.py --selftest # 仅验证环境

输出（/workspace/seo-monitor/）：
  fee-check-YYYYMMDD.json   结构化比对结果（逐项 matched / 差异 / 无法核验）
  fee-<source>-YYYYMMDD.png 各官方页截图证据

基准值来源：/workspace/emallsoon/src/data/fees.ts（站点唯一数据源）。
比对规则：|官方值 - 站点值| > 0.05 记差异；抓取/提取失败记 unable_to_verify（不算差异，
等待人工确认，避免把页面改版误报为费率变化）。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, "/workspace/.pylibs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloak_common import setup_env  # noqa: E402

setup_env()

OUT = "/workspace/seo-monitor"
DATE = time.strftime("%Y%m%d")
UA_WIN = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")

# ---- 站点基准值（镜像 src/data/fees.ts，修改数据时必须同步此处）----
BASELINE = {
    "amazon_referral_default": 15.0,      # fees.ts referralDefault
    "ebay_most_fvf_individual": 13.6,     # ebayCategories[most].individualPct
    "ebay_most_fvf_store": 12.7,          # ebayCategories[most].storePct
    "ebay_most_tier_threshold": 7500.0,   # individualThreshold
    "ebay_most_tier_over": 2.35,          # individualOverPct
    "ebay_per_order_under10": 0.30,
    "ebay_per_order_over10": 0.40,
    "etsy_listing_fee": 0.20,
    "etsy_transaction_pct": 6.5,
    "etsy_offsite_ads_cap": 100.0,
    "shopify_processing_pct": 2.9,        # Basic plan, US online standard card
    "tiktok_referral_default": 6.0,
}


def num_after(text, keywords, window=90, want_float=False):
    """在关键词后 window 字符内找第一个数字（容忍千分位逗号）。返回 str 或 None。"""
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, re.I):
            seg = text[m.end():m.end() + window]
            mm = re.search(r"[\d,]+(?:\.\d+)?", seg)
            if mm:
                return mm.group(0).replace(",", "")
    return None


def percent(text, keywords, window=60):
    """关键词后 window 内找百分比（含 % 的数值）。"""
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text, re.I):
            seg = text[m.end():m.end() + window]
            mm = re.search(r"([\d.]+)\s*%", seg)
            if mm:
                return float(mm.group(1))
    return None


def snippet(text, keywords, width=160):
    for kw in keywords:
        i = text.lower().find(kw.lower())
        if i >= 0:
            return text[max(0, i - 40):i + width].replace("\n", " ").strip()
    return ""


def fetch_text(page, url, timeout=45000, wait=3500):
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    page.wait_for_timeout(wait)
    return page.inner_text("body")


def check_amazon(page, res):
    urls = [
        "https://sellercentral.amazon.com/help/hub/reference/external/GP3TQJQJMB8PGB3K",
        "https://sell.amazon.com/pricing",
    ]
    body, ok_url = None, None
    for u in urls:
        try:
            body = fetch_text(page, u)
            ok_url = u
            break
        except Exception:
            continue
    if body is None:
        res["amazon_referral_default"] = {"status": "unable_to_verify", "url": urls[0],
                                          "verify_with": "webfetch", "note": "浏览器被反爬/JS 拦截时用 WebFetch 打开上方 URL 核对"}
        return
    v = percent(body, ["referral fee", "referral fees", "category referral"])
    page.screenshot(path=os.path.join(OUT, f"fee-amazon-{DATE}.png"))
    res["amazon_referral_default"] = {
        "status": "matched" if v is not None and abs(v - BASELINE["amazon_referral_default"]) <= 0.05
        else "diff" if v is not None else "unable_to_verify",
        "url": ok_url, "site": BASELINE["amazon_referral_default"],
        "official": v, "snippet": snippet(body, ["referral fee"]),
    }


def check_ebay(page, res):
    # 页面较慢，容忍 60s
    urls = [
        "https://www.ebay.com/help/selling/fees-credits-invoices/selling-fees?id=4822",
        "https://www.ebay.com/help/selling/fees-credits-invoices/store-selling-fees?id=4809",
    ]
    bodies = []
    for u in urls:
        try:
            bodies.append(fetch_text(page, u, timeout=60000, wait=5000))
        except Exception:
            bodies.append("")
    main, store = (bodies + ["", ""])[:2]

    def rec(key, v, text, kws, url):
        res[key] = {
            "status": "matched" if v is not None and abs(v - BASELINE[key]) <= 0.05
            else "diff" if v is not None else "unable_to_verify",
            "url": url, "site": BASELINE[key],
            "official": v, "snippet": snippet(text, kws),
        }

    fvf = percent(main, ["most categories", "most items", "final value fee"])
    rec("ebay_most_fvf_individual", fvf, main, ["most categories"], urls[0])
    # 非商店页可能给区间而非单值；此时标记待人工
    if res["ebay_most_fvf_individual"]["status"] != "matched":
        res["ebay_most_fvf_individual"]["note"] = "页面可能以区间展示，已标 unable_to_verify 待人工核对"

    store_fvf = percent(store, ["store", "final value fee", "basic store"])
    rec("ebay_most_fvf_store", store_fvf, store, ["store"], urls[1])

    per_u = num_after(main, ["$0.30", "0.30", "orders under", "order totals of"])
    per_o = num_after(main, ["$0.40", "0.40", "orders over"])
    rec("ebay_per_order_under10", float(per_u) if per_u else None, main, ["0.30"], urls[0])
    rec("ebay_per_order_over10", float(per_o) if per_o else None, main, ["0.40"], urls[0])
    page.screenshot(path=os.path.join(OUT, f"fee-ebay-{DATE}.png"))


def check_etsy(page, res):
    u = "https://www.etsy.com/legal/fees/"
    try:
        body = fetch_text(page, u, timeout=60000, wait=5000)
    except Exception:
        res["etsy_transaction_pct"] = {"status": "unable_to_verify", "url": u}
        res["etsy_listing_fee"] = {"status": "unable_to_verify", "url": u}
        return
    tx = percent(body, ["transaction fee", "transaction fees"])
    listing = num_after(body, ["listing fee", "listing fees", "fee per listing"])
    page.screenshot(path=os.path.join(OUT, f"fee-etsy-{DATE}.png"))
    res["etsy_transaction_pct"] = {
        "status": "matched" if tx is not None and abs(tx - BASELINE["etsy_transaction_pct"]) <= 0.05
        else "diff" if tx is not None else "unable_to_verify",
        "url": u, "site": BASELINE["etsy_transaction_pct"], "official": tx,
        "snippet": snippet(body, ["transaction fee"]),
    }
    lv = float(listing) if listing else None
    res["etsy_listing_fee"] = {
        "status": "matched" if lv is not None and abs(lv - BASELINE["etsy_listing_fee"]) <= 0.02
        else "diff" if lv is not None else "unable_to_verify",
        "url": u, "site": BASELINE["etsy_listing_fee"], "official": lv,
        "snippet": snippet(body, ["listing fee"]),
    }


def check_shopify(page, res):
    """注意：shopify.com/pricing 按出口 IP 地区化返回不同货币版本（SGD/CAD/EUR...）。
    US 版官方在线标准卡费率 = 2.9% + $0.30（2026-08-31 多源确认）。
    抓到非 US 货币数字时标记 region_ambiguous，提示用 WebFetch 核 US 版。"""
    u = "https://www.shopify.com/pricing"
    try:
        body = fetch_text(page, u, timeout=60000, wait=5000)
    except Exception:
        res["shopify_processing_pct"] = {"status": "unable_to_verify", "url": u}
        return
    v = percent(body, ["online standard card rates", "online standard", "standard card rates", "card rates"])
    region_kw = ("SGD", "CAD", "AUD", "EUR", "GBP", "NZD", "HKD")
    region_hint = next((r for r in region_kw if r in body), None)
    page.screenshot(path=os.path.join(OUT, f"fee-shopify-{DATE}.png"))
    rec = {
        "url": u, "site": BASELINE["shopify_processing_pct"], "official": v,
        "snippet": snippet(body, ["online"]),
    }
    if region_hint:
        rec["status"] = "region_ambiguous"
        rec["note"] = (f"页面为 {region_hint} 地区版（出口 IP 定位），非 US 数值。"
                       "请用 WebFetch/WebSearch 核实 US Basic 在线标准卡费率（2026-08-31 已核为 2.9% + $0.30）")
    elif v is not None and abs(v - BASELINE["shopify_processing_pct"]) <= 0.05:
        rec["status"] = "matched"
    elif v is not None:
        rec["status"] = "diff"
    else:
        rec["status"] = "unable_to_verify"
    res["shopify_processing_pct"] = rec


def check_tiktok(page, res):
    # TikTok 官方费率说明位于 Seller Center 教育中心，结构多变；抓不到不算差异
    u = "https://seller-us.tiktok.com/university/essay/learn?mod_id=1012"
    try:
        body = fetch_text(page, u, timeout=45000, wait=4000)
    except Exception:
        res["tiktok_referral_default"] = {"status": "unable_to_verify", "url": u,
                                          "verify_with": "webfetch",
                                          "note": "TikTok 卖家中心为 SPA 且常需登录；官方费率（2026-08-31 已核：标准类目 6%，含支付处理）建议人工复核"}
        return
    v = percent(body, ["referral fee", "commission", "6%"])
    res["tiktok_referral_default"] = {
        "status": "matched" if v is not None and abs(v - BASELINE["tiktok_referral_default"]) <= 0.05
        else "diff" if v is not None else "unable_to_verify",
        "url": u, "site": BASELINE["tiktok_referral_default"], "official": v,
        "snippet": snippet(body, ["referral fee"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        from cloakbrowser import launch
        b = launch(headless=True)
        p = b.new_page()
        p.goto("https://example.com", timeout=30000)
        print(f"浏览器可用 ✓（{p.title()}）")
        b.close()
        print("SELFTEST PASS")
        return 0

    os.makedirs(OUT, exist_ok=True)
    res = {"date": time.strftime("%Y-%m-%d %H:%M"), "checks": {}, "issues": [],
           "webcheck_baseline": {
               "date": "2026-08-31",
               "conclusion": "首轮 WebFetch/WebSearch 人工核验：全部站点费率与官方一致（eBay 个体+店铺全表 / Amazon 类目 referral / Etsy / Shopify US Basic 2.9%+$0.30 / TikTok 6%）",
               "sources": [
                   "https://www.ebay.com/help/selling/fees-credits-invoices/selling-fees?id=4822",
                   "https://www.ebay.com/help/selling/selling-fees/store-fees?id=4809",
                   "https://sell.amazon.com/pricing",
                   "https://www.etsy.com/legal/fees/",
                   "https://www.shopify.com/pricing",
               ],
           }}
    checks = res["checks"]

    from cloakbrowser import launch
    browser = launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        user_agent=UA_WIN,
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page = ctx.new_page()
    try:
        check_amazon(page, checks)
        check_ebay(page, checks)
        check_etsy(page, checks)
        check_shopify(page, checks)
        check_tiktok(page, checks)
    finally:
        ctx.close()
        browser.close()

    for k, v in checks.items():
        if v.get("status") == "diff":
            res["issues"].append(
                f"{k}: 站点 {v['site']} vs 官方 {v['official']}（{v['url']}）——需更新 fees.ts 并部署")
        elif v.get("status") in ("unable_to_verify", "region_ambiguous"):
            res["issues"].append(
                f"{k}: 浏览器未能可靠提取（{v.get('url','')}）——请用 WebFetch 打开该 URL 人工核对；"
                f"首轮基线: {res['webcheck_baseline']['conclusion']}")

    fn = os.path.join(OUT, f"fee-check-{DATE}.json")
    with open(fn, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "fee-latest.json"), "w") as f:
        json.dump({k: v.get("status") for k, v in checks.items()}, f, indent=1)

    print("=" * 56)
    for k, v in checks.items():
        print(f"{k:28s} {v.get('status','?'):18s} 站点={v.get('site')} 官方={v.get('official')}")
    for i, msg in enumerate(res["issues"], 1):
        print(f"  ⚠️ [{i}] {msg}")
    print(f"报告: {fn}")
    return 0 if not res["issues"] else 1


if __name__ == "__main__":
    sys.exit(main())
