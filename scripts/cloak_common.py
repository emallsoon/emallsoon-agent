#!/usr/bin/env python3
"""CloakBrowser 公共模块：环境变量、profile/备份路径、cookie 恢复与备份。

引擎说明（2026-08-30 起替代裸 Chrome；2026-08-31 完成全量本地化）：
  - pip 包   : cloakbrowser 0.5.10（Playwright drop-in，Chromium 源码级 73 项反检测补丁）
               安装于 /workspace/.pylibs（pip --target），重置后免重装，
               用法: sys.path.insert(0, "/workspace/.pylibs")
  - 二进制   : /workspace/.cloakbrowser/chromium-<ver>/chrome（CLOAKBROWSER_CACHE_DIR 重定向，
               容器重置后无需重新下载 200MB）
  - 系统库   : /workspace/.cloakbrowser/libs（5 个 Chromium 依赖 .so，共 644K，
               经 LD_LIBRARY_PATH 注入——重置后系统缺 libatk 等也不影响启动；
               2026-08-31 实测:重置清掉系统库后,仅靠该目录即可跑通 chrome）
  - 持久档案 : /workspace/.browser-profile-cloak（BWT + GSC 登录态都在里面）
  - 免费版   : tier=free，无 license key，单并发；UA = Chrome/146 Windows
"""
import os
import json
import time
from datetime import datetime, timedelta, timezone

CLOAK_CACHE = "/workspace/.cloakbrowser"
PROFILE = "/workspace/.browser-profile-cloak"
AUTH = "/workspace/.browser-auth"

# ---- 报告时间统一按北京时间 ----
# 背景（2026-09-01 发现）：不同沙盒会话的系统时区/时钟不一致（有的 UTC、有的滞后），
# time.strftime("%Y%m%d") 会取到错误日期 → 报告文件名串日并覆盖前日存档。
BJ_TZ = timezone(timedelta(hours=8))


def bj_now():
    """当前北京时间 datetime。"""
    return datetime.now(BJ_TZ)


def bj_date(fmt="%Y%m%d"):
    """当前北京时间日期串（报告文件名统一用它）。"""
    return bj_now().strftime(fmt)


def launch_profile_ctx(retries=3, wait_s=20):
    """启动持久化 profile 浏览器上下文（GSC/BWT 登录态），失败自动重试。

    多个会话可能争用同一 profile（SingletonLock）：定时任务与人工会话
    同时跑监控时，后启动方会失败；重试可等先启动方释放。
    """
    from cloakbrowser import launch_persistent_context
    last = None
    for _ in range(retries):
        try:
            return launch_persistent_context(PROFILE, headless=True)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(wait_s)
    raise last

GSC_URL = "https://search.google.com/search-console?resource_id=sc-domain:emallsoon.com"
BWT_URL = "https://www.bing.com/webmasters"


def setup_env():
    """必须在 import cloakbrowser 前调用（其实随时调用都行，config 每次读 env）。

    2026-08-31 起同时注入 LD_LIBRARY_PATH：Chromium 的 5 个系统依赖库存于
    /workspace/.cloakbrowser/libs，容器重置后系统目录被清也能正常启动浏览器。
    """
    os.environ.setdefault("CLOAKBROWSER_CACHE_DIR", CLOAK_CACHE)
    os.environ.setdefault("CLOAKBROWSER_SUPPRESS_FONT_WARNING", "1")
    libs = os.path.join(CLOAK_CACHE, "libs")
    if os.path.isdir(libs):
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        paths = [p for p in existing.split(":") if p]
        if libs not in paths:
            os.environ["LD_LIBRARY_PATH"] = ":".join([libs] + paths)
    _clear_stale_profile_lock()


def _clear_stale_profile_lock():
    """清除 profile 残留的 SingletonLock（容器重置强杀 Chromium 会留下）。

    仅当锁指向的 pid 已不存在时才清，正常运行中的浏览器不受影响。
    """
    import glob
    lock = os.path.join(PROFILE, "SingletonLock")
    if not os.path.islink(lock) and not os.path.exists(lock):
        return
    try:
        target = os.readlink(lock) if os.path.islink(lock) else ""
        # 锁格式通常是 "hostname-PID"
        pid = None
        for part in (target or "").split("-"):
            if part.isdigit():
                pid = int(part)
                break
        stale = pid is None or not os.path.exists(f"/proc/{pid}")
        if stale:
            for f in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                p = os.path.join(PROFILE, f)
                if os.path.lexists(p):
                    os.remove(p)
    except OSError:
        pass


def load_creds():
    """读取 /workspace/.browser-auth/credentials.env（mode 600）。"""
    creds = {}
    with open(f"{AUTH}/credentials.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds


def _cdp_to_playwright(raw):
    """CDP Storage.getCookies 格式 -> Playwright add_cookies 格式。"""
    out = []
    for c in raw:
        cc = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "expires": max(int(c.get("expires", -1) or -1), -1),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
        }
        if c.get("sameSite") in ("Strict", "Lax", "None"):
            cc["sameSite"] = c["sameSite"]
        out.append(cc)
    return out


def latest_backup_path(prefer_cloak=True):
    """返回 (cookie 备份文件路径, 指针 dict)。latest-cloak.json 优先（Playwright 格式）。"""
    for ptr_name in ("latest-cloak.json", "latest.json") if prefer_cloak else ("latest.json",):
        p = os.path.join(AUTH, ptr_name)
        if os.path.exists(p):
            ptr = json.load(open(p))
            return os.path.join(AUTH, ptr["file"]), ptr
    return None, None


def load_backup_cookies(path=None):
    """读取备份文件，统一返回 Playwright 格式 cookie 列表。"""
    path = path or latest_backup_path()[0]
    if not path or not os.path.exists(path):
        return []
    data = json.load(open(path))
    if "cookies_by_context" in data:            # CDP 备份格式（旧 cdp_cookies.py）
        cbc = data["cookies_by_context"]
        raw = cbc.get("default") or next(iter(cbc.values()))
        return _cdp_to_playwright(raw)
    return data.get("cookies", [])              # Playwright 格式（新备份）


def restore_cookies(ctx, force=False):
    """把备份 cookie 恢复进上下文。

    force=False 时仅在当前 cookie 罐少于 10 条时恢复，
    避免旧值覆盖档案里已更新的新会话。
    返回恢复条数（0 = 无需恢复）。
    """
    existing = ctx.cookies()
    if not force and len(existing) >= 10:
        return 0
    cookies = load_backup_cookies()
    if not cookies:
        return 0
    ctx.add_cookies(cookies)
    return len(cookies)


def backup_cookies(ctx, tag="cloak"):
    """备份上下文全部 cookie（Playwright 格式），更新 latest-cloak.json 指针。"""
    cookies = ctx.cookies()
    ts = time.strftime("%Y%m%d-%H%M%S")
    fn = os.path.join(AUTH, f"cookies-{tag}-{ts}.json")
    with open(fn, "w") as f:
        json.dump({
            "kind": "cloakbrowser-playwright",
            "engine": "cloakbrowser",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(cookies),
            "cookies": cookies,
        }, f, ensure_ascii=False, indent=1)
    os.chmod(fn, 0o600)
    with open(os.path.join(AUTH, "latest-cloak.json"), "w") as f:
        json.dump({
            "file": os.path.basename(fn),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(cookies),
            "engine": "cloakbrowser",
        }, f)
    return fn, len(cookies)
