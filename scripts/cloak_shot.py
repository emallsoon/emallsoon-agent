#!/usr/bin/env python3
"""cloak_shot.py — 网页落盘截图（CloakBrowser 引擎，替代 legacy/browser-shot.sh）

用法:
  python3 scripts/cloak_shot.py <url> <out.png> [宽x高] [等待ms]

- 独立临时 profile（不碰 .browser-profile-cloak 登录态，也不受 serve 的 profile 锁限制）
- 默认 1280x全页，等待入场动画（默认 4000ms）后再截，避免截到半透明过渡帧
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cloak_common import setup_env  # noqa: E402

setup_env()
from cloakbrowser import launch  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    url, out = sys.argv[1], sys.argv[2]
    w, h = (int(x) for x in sys.argv[3].split("x")) if len(sys.argv) > 3 else (1280, 800)
    wait_ms = int(sys.argv[4]) if len(sys.argv) > 4 else 4000

    browser = launch(headless=True)
    try:
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(wait_ms)
        page.screenshot(path=out, full_page=True)
        print(f"OK {out} ({w}x全页) <- {url}")
        return 0
    finally:
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
