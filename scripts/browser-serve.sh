#!/usr/bin/env bash
# browser-serve.sh — 启动"持久化浏览器"
#
# 目的：沙箱/集成浏览器的登录态无法导出（httpOnly cookie 读不到），
#       因此用一个我们完全掌控的本地 Chrome：
#         1. 用户数据目录放在 /workspace/.browser-profile（跨沙箱重置持久）
#         2. CDP 端口 9223，可完整读取/写入 cookie（含 httpOnly）
#         3. 通过 127.0.0.1:18080 代理上网
#
# 容器重置后的自动恢复（2026-08-30 实验验证）：
#   - /root/.cache 下的 Chrome 二进制可能丢失 → 多级回退（151 → 131 → /opt）
#   - 备用 Chrome 版本读取旧 profile 可能崩溃（版本降级路径）→ 自动清理
#     Cache/Code Cache 后重试（登录态在 Cookies/Login Data，不在缓存中）
#   - Cookies DB 若损坏/为空 → 自动从 /workspace/.browser-auth/latest.json 兜底恢复
#   - Singleton 锁残留 → 启动前清理
#
# 用法：
#   bash scripts/browser-serve.sh start   # 启动（幂等 + 自动恢复）
#   bash scripts/browser-serve.sh status  # 检查 CDP 是否可达
#   bash scripts/browser-serve.sh stop    # 优雅关闭
#
# 产物：
#   /workspace/.browser-profile/            Chrome 用户数据（登录态本体）
#   /workspace/.browser-auth/cookies-*.json cookie 备份（cdp_cookies.py backup）

set -euo pipefail

PROFILE="/workspace/.browser-profile"
AUTH_DIR="/workspace/.browser-auth"
CDP_PORT="${CDP_PORT:-9223}"
PROXY="${PROXY:-http://127.0.0.1:18080}"
COOKIE_TOOL="/workspace/emallsoon-agent/scripts/cdp_cookies.py"

# 选择最新可用的 Chrome 二进制（多级回退，容器重置后二进制可能丢失）
CHROME=""
for c in \
  /root/.cache/puppeteer/chrome/linux-151.0.7922.71/chrome-linux64/chrome \
  /root/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome \
  /opt/google/chrome/chrome; do
  if [[ -x "$c" ]]; then CHROME="$c"; break; fi
done
[[ -n "$CHROME" ]] || { echo "ERROR: no chrome binary found"; exit 1; }

cdp_alive() {
  curl -s --max-time 3 "http://127.0.0.1:${CDP_PORT}/json/version" | grep -q Browser
}

launch() {
  local bin="$1"
  rm -f "$PROFILE/SingletonLock" "$PROFILE/SingletonSocket" "$PROFILE/SingletonCookie"
  nohup "$bin" \
    --headless=new \
    --user-data-dir="$PROFILE" \
    --remote-debugging-port="$CDP_PORT" \
    --remote-allow-origins='*' \
    --proxy-server="$PROXY" \
    --user-agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36' \
    --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --disable-blink-features=AutomationControlled \
    --window-size=1440,900 \
    about:blank >/workspace/.browser-chrome.log 2>&1 &
  for i in $(seq 1 20); do
    sleep 0.5
    cdp_alive && return 0
  done
  return 1
}

# cookie 兜底恢复：Cookies DB 缺失或近乎为空时，从最新备份恢复
restore_cookies_if_needed() {
  local db="$PROFILE/Default/Cookies"
  local latest="$AUTH_DIR/latest.json"
  [[ -f "$latest" ]] || { echo "  (no cookie backup found, skip)"; return 0; }
  local n=0
  if [[ -f "$db" ]]; then
    n=$(python3 - "$db" <<'EOF' 2>/dev/null || echo 0
import sqlite3, sys
try:
    con = sqlite3.connect(sys.argv[1])
    n = con.execute("SELECT COUNT(*) FROM cookies").fetchone()[0]
    con.close()
    print(n)
except Exception:
    print(0)
EOF
)
  fi
  if [[ -z "$n" || "$n" -lt 10 ]]; then
    echo "  Cookies DB empty/invalid ($n) -> restoring from backup"
    python3 "$COOKIE_TOOL" restore --port "$CDP_PORT" --file "$latest" 2>&1 | sed 's/^/    /' || true
  else
    echo "  Cookies DB ok ($n cookies)"
  fi
}

case "${1:-start}" in
  start)
    mkdir -p "$PROFILE" "$AUTH_DIR"
    chmod 700 "$AUTH_DIR" 2>/dev/null || true
    if cdp_alive; then
      echo "OK already-running port=${CDP_PORT} profile=${PROFILE}"
      exit 0
    fi
    echo "Using chrome: $CHROME"
    if launch "$CHROME"; then
      echo "OK started port=${CDP_PORT} chrome=${CHROME} profile=${PROFILE}"
    else
      echo "WARN first launch failed; cleaning cache and retrying..."
      # 版本降级时旧缓存结构可能导致崩溃；缓存不含登录态，可安全清理
      rm -rf "$PROFILE/Default/Cache" "$PROFILE/Default/Code Cache" \
             "$PROFILE/Default/Service Worker/CacheStorage" 2>/dev/null || true
      if launch "$CHROME"; then
        echo "OK started (after cache cleanup) port=${CDP_PORT} chrome=${CHROME}"
      else
        echo "FAILED to start; log:"; tail -n 20 /workspace/.browser-chrome.log
        exit 1
      fi
    fi
    restore_cookies_if_needed
    ;;
  status)
    if cdp_alive; then
      echo "UP $(curl -s "http://127.0.0.1:${CDP_PORT}/json/version" | head -c 200)"
    else
      echo "DOWN"
    fi
    ;;
  stop)
    if cdp_alive; then
      PID=$(ss -ltnp 2>/dev/null | awk -v p=":${CDP_PORT}" '$4 ~ p {print $NF}' | grep -oP 'pid=\K[0-9]+' | head -1 || true)
      [[ -n "${PID:-}" ]] && kill "$PID" && echo "OK stopped pid=$PID" || echo "no pid found"
    else
      echo "already down"
    fi
    ;;
  *)
    echo "usage: $0 {start|status|stop}"; exit 1;;
esac
