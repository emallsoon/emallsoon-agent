#!/usr/bin/env bash
# browser-serve.sh — 启动"持久化隐身浏览器"（CloakBrowser 引擎版）
#
# 2026-08-30 起引擎从裸 Chrome 切换为 CloakBrowser：
#   - pip 包 cloakbrowser（Playwright drop-in，Chromium 146 源码级 73 项反检测补丁）
#   - 实测：裸 Chrome 走 GSC 登录被 reCAPTCHA Enterprise 卡死；
#     CloakBrowser(humanize=True) 同流程未触发任何挑战，一次成功
#   - 二进制缓存在 /workspace/.cloakbrowser（CLOAKBROWSER_CACHE_DIR 重定向），
#     容器重置后无需重新下载；pip 包本身重置后需重装（见 bootstrap.sh 第 7 步）
#   - 持久档案 /workspace/.browser-profile-cloak（BWT + GSC 登录态）
#   - 不再暴露 CDP 9223 端口（Playwright 内部 pipe 通信）；
#     cookie 读写一律走 Playwright API（scripts/cloak_common.py）
#
# 用法：
#   bash scripts/browser-serve.sh start    # 启动常驻上下文（幂等）
#   bash scripts/browser-serve.sh status   # 查看进程与最近日志
#   bash scripts/browser-serve.sh stop     # 优雅关闭（退出前自动备份 cookie）
#   bash scripts/browser-serve.sh check    # 双平台登录态巡检（cloak_check.py）
#
# 产物：
#   /workspace/.browser-profile-cloak/           持久档案（登录态本体）
#   /workspace/.browser-auth/cookies-cloak-*.json cookie 备份（Playwright 格式）

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTH_DIR="/workspace/.browser-auth"
LOG="$AUTH_DIR/cloak-serve.log"
HOLD="$HERE/cloak_hold.py"
export CLOAKBROWSER_CACHE_DIR="${CLOAKBROWSER_CACHE_DIR:-/workspace/.cloakbrowser}"
export CLOAKBROWSER_SUPPRESS_FONT_WARNING=1

# 注意：pgrep 模式用 cloak_hol[d] 防自匹配（本脚本命令行里含 cloak_hold 字样）
hold_pid() {
  pgrep -f "cloak_hol[d]\\.py" | head -1
}

alive() {
  local pid; pid=$(hold_pid)
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

ensure_deps() {
  if ! python3 -c "import cloakbrowser" >/dev/null 2>&1; then
    echo "cloakbrowser 未安装，正在安装（pip）..."
    pip install 'cloakbrowser[serve,geoip]' pyotp --break-system-packages >/dev/null 2>&1 \
      || { echo "ERROR: cloakbrowser 安装失败（网络？）"; exit 1; }
  fi
  if ! ls "$CLOAKBROWSER_CACHE_DIR"/chromium-*/chrome >/dev/null 2>&1; then
    echo "首次运行：下载 stealth Chromium（~200MB，缓存在 $CLOAKBROWSER_CACHE_DIR）..."
  fi
}

# chrome-devtools MCP 在 Linux 只认 /opt/google/chrome/chrome。
# Chrome 已卸载 → 放包装脚本指向 cloakbrowser 的 Chromium 二进制（无 X server，
# root 运行，需追加沙箱/无头参数）。MCP 实例=独立临时 profile，仅作调试；
# 登录态在 .browser-profile-cloak，由本脚本 start 持有。
ensure_mcp_wrapper() {
  local bin
  bin=$(ls "$CLOAKBROWSER_CACHE_DIR"/chromium-*/chrome 2>/dev/null | head -1) || return 0
  [[ -n "$bin" ]] || return 0
  if [[ ! -x /opt/google/chrome/chrome ]] || ! grep -q "CloakBrowser" /opt/google/chrome/chrome 2>/dev/null; then
    mkdir -p /opt/google/chrome
    printf '#!/bin/bash\n# wrapper: chrome-devtools MCP -> CloakBrowser Chromium (2026-08-31, Chrome 已卸载)\n# 无 X server，root 运行：追加沙箱/无头必需参数后透传\nexec "%s" --no-sandbox --disable-gpu --disable-dev-shm-usage --headless=new "$@"\n' "$bin" \
      > /opt/google/chrome/chrome && chmod +x /opt/google/chrome/chrome \
      && echo "OK mcp-wrapper -> $bin" || echo "WARN mcp-wrapper 写入失败（MCP 调试不可用，不影响 serve）"
  fi
}


case "${1:-status}" in
  start)
    ensure_deps
    ensure_mcp_wrapper
    if alive; then
      echo "OK already-running pid=$(hold_pid)"
      tail -1 "$LOG" 2>/dev/null || true
      exit 0
    fi
    mkdir -p "$AUTH_DIR"
    nohup python3 "$HOLD" >"$LOG" 2>&1 &
    local_pid=$!
    for _ in $(seq 1 60); do   # 最长 30s：含可能的二进制首载
      sleep 0.5
      grep -q "OK cloak-hold" "$LOG" 2>/dev/null && break
      kill -0 "$local_pid" 2>/dev/null || { echo "ERROR: cloak_hold 退出，日志："; tail -5 "$LOG"; exit 1; }
    done
    if grep -q "OK cloak-hold" "$LOG" 2>/dev/null; then
      echo "OK started pid=$(hold_pid)"
      grep "OK cloak-hold" "$LOG" | tail -1
    else
      echo "WARN 启动慢或异常，最近日志："; tail -3 "$LOG"
      exit 1
    fi
    ;;
  stop)
    pid=$(hold_pid)
    if [[ -z "$pid" ]]; then echo "OK not-running"; exit 0; fi
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do sleep 0.5; kill -0 "$pid" 2>/dev/null || break; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    echo "OK stopped（退出前已备份 cookie，见日志尾部）"
    tail -2 "$LOG" 2>/dev/null || true
    ;;
  restart)
    "$0" stop; sleep 1; "$0" start
    ;;
  status)
    if alive; then
      echo "RUNNING pid=$(hold_pid)"
      grep "OK cloak-hold" "$LOG" 2>/dev/null | tail -1
      exit 0
    else
      echo "STOPPED（bash scripts/browser-serve.sh start 启动）"
      exit 1
    fi
    ;;
  check)
    exec python3 "$HERE/cloak_check.py"
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|check}"
    exit 2
    ;;
esac
