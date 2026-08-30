#!/bin/bash
# ============================================================
# 网页截图工具（Chrome 原生 headless 截图，零依赖）
# 用法：bash scripts/browser-shot.sh <url> <output.png> [宽x高]
# 示例：bash scripts/browser-shot.sh https://emallsoon.com /tmp/home.png 1280x3000
#
# 说明：
#   - 使用 /opt/google/chrome/chrome（setup-browser.sh 安装的包装器）
#   - --virtual-time-budget 让入场动画/字体加载播完再截屏，
#     避免捕获到 rise-in 动画中途的半透明卡片
#   - 为什么不用 MCP 的 take_screenshot filePath：
#     本环境 chrome-devtools-mcp 未配置任何可写工作区根目录，
#     filePath 一律 Access denied；内联截图可见但无法落盘
# ============================================================
set -euo pipefail

URL="${1:?用法: browser-shot.sh <url> <output.png> [宽x高]}"
OUT="${2:?缺少输出路径}"
SIZE="${3:-1280x3000}"

CHROME=/opt/google/chrome/chrome
if [ ! -x "$CHROME" ]; then
  echo "❌ 未找到 $CHROME，先执行: bash scripts/setup-browser.sh"
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
# dbus/GLib 报错为沙箱无害噪音，过滤之
"$CHROME" \
  --screenshot="$OUT" \
  --window-size="$SIZE" \
  --hide-scrollbars \
  --virtual-time-budget=8000 \
  "$URL" 2>&1 | grep -v "dbus\|GLib-GIO" || true

if [ -f "$OUT" ]; then
  SIZE_BYTES=$(du -h "$OUT" | cut -f1)
  echo "✅ 截图完成: $OUT ($SIZE_BYTES, viewport $SIZE)"
else
  echo "❌ 截图失败"
  exit 1
fi
