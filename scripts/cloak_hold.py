#!/usr/bin/env python3
"""CloakBrowser 常驻服务（供 browser-serve.sh start 调用，也可单独跑）。

打开持久化上下文 -> 按需恢复 cookie -> 保持运行 -> 收到 SIGTERM/SIGINT 时备份 cookie 退出。
注意：不再暴露 CDP 9223 端口（Playwright 走内部 pipe）；cookie 备份用本模块的 backup_cookies()。
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloak_common import setup_env, PROFILE, restore_cookies, backup_cookies

setup_env()
from cloakbrowser import launch_persistent_context

ctx = launch_persistent_context(PROFILE, headless=True, humanize=True)
page = ctx.pages[0] if ctx.pages else ctx.new_page()

n = restore_cookies(ctx)
jar = len(ctx.cookies())
print(f"OK cloak-hold profile={PROFILE} cookie恢复={n} 当前罐={jar} "
      f"pid={os.getpid()} chrome={page.evaluate('navigator.userAgent')}", flush=True)

_stop = {"flag": False}


def _term(sig, frame):
    _stop["flag"] = True


signal.signal(signal.SIGTERM, _term)
signal.signal(signal.SIGINT, _term)

while not _stop["flag"]:
    time.sleep(1)

try:
    fn, total = backup_cookies(ctx, tag="cloak-hold")
    print(f"BYE 退出前备份 {total} 条 -> {fn}", flush=True)
except Exception as e:
    print(f"BYE 备份失败: {e}", flush=True)
ctx.close()
