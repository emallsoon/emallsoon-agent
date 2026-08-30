#!/bin/bash
# ============================================================
# 新会话环境一键恢复脚本
# 用途：沙箱/环境重置后，一条命令恢复全部工作能力
# 用法：bash /workspace/emallsoon/scripts/bootstrap.sh
#
# 环境重置规律（实测 2026-08-27）：
#   ✅ 存活：git 跟踪的文件、/workspace 下非 gitignore 位置（如 .ssh-backup/）
#   ❌ 清除：~/.ssh（家目录）、node_modules/、dist/、.astro/（gitignore 项）
# ============================================================
set -uo pipefail

# 仓库路径自动探测：生产目录优先，镜像克隆（emallsoon-agent）回退
if [ -d /workspace/emallsoon/.git ]; then
  REPO="/workspace/emallsoon"
  CLONE_URL="https://github.com/emallsoon/emallsoon.git"
elif [ -d /workspace/emallsoon-agent/.git ]; then
  REPO="/workspace/emallsoon-agent"
  CLONE_URL="https://github.com/emallsoon/emallsoon-agent.git"
else
  REPO="/workspace/emallsoon"
  CLONE_URL="https://github.com/emallsoon/emallsoon.git"
fi
BACKUP="/workspace/.ssh-backup"
TOTAL=7
PASS=0; WARN=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
warn() { echo "  ⚠️  $1"; WARN=$((WARN+1)); }

echo "=========================================="
echo " emallsoon 环境恢复（共 $TOTAL 步）"
echo "=========================================="

# ---------- 1. SSH 恢复 ----------
echo "[1/$TOTAL] SSH 密钥与代理配置"
# 通道探测(2026-08-30 实测):直连 22/443 被拦,但代理 CONNECT 到
# github.com:22 与 ssh.github.com:443 均可达(nc -X connect 验证)。
# curl telnet:// 方式测代理会误报失败,勿用。
SSH_CHANNEL_OK=0
if timeout 6 bash -c "echo > /dev/tcp/github.com/22" 2>/dev/null \
   || timeout 6 bash -c "echo > /dev/tcp/ssh.github.com/443" 2>/dev/null; then
  SSH_CHANNEL_OK=1
elif command -v nc >/dev/null \
   && timeout 10 nc -z -X connect -x 127.0.0.1:18080 ssh.github.com 443 >/dev/null 2>&1; then
  SSH_CHANNEL_OK=1
fi
if [ "$SSH_CHANNEL_OK" -eq 0 ]; then
  warn "出站 SSH 通道不可用(直连与代理均被拦)→ git 走 HTTPS 模式"
  echo "     → pull/fetch 用 HTTPS origin;push 需 HTTPS 凭据或环境提供 SSH 通道"
elif [ -f ~/.ssh/id_ed25519 ] && [ -f ~/.ssh/config ]; then
  ok "SSH 已存在,跳过"
else
  if [ -f "$BACKUP/id_ed25519" ]; then
    mkdir -p ~/.ssh && chmod 700 ~/.ssh
    cp "$BACKUP/id_ed25519" "$BACKUP/id_ed25519.pub" "$BACKUP/config" ~/.ssh/
    [ -f "$BACKUP/known_hosts" ] && cp "$BACKUP/known_hosts" ~/.ssh/
    chmod 600 ~/.ssh/id_ed25519 ~/.ssh/config
    ok "已从 /workspace/.ssh-backup 恢复"
  else
    warn "备份不存在！生成新密钥（公钥需用户添加到 GitHub 后才能 push）："
    ssh-keygen -t ed25519 -C "emallsoon-agent-deploy" -f ~/.ssh/id_ed25519 -N "" -q
    cat > ~/.ssh/config << 'EOF'
Host github-proxy
  HostName ssh.github.com
  Port 443
  User git
  ProxyCommand nc -X connect -x 127.0.0.1:18080 %h %p
  StrictHostKeyChecking accept-new
EOF
    chmod 600 ~/.ssh/config ~/.ssh/id_ed25519
    mkdir -p "$BACKUP" && cp ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub ~/.ssh/config "$BACKUP/" 2>/dev/null
    echo "  ⬇️  请让用户把此公钥添加到 GitHub（Settings → SSH keys）："
    cat ~/.ssh/id_ed25519.pub
  fi
fi

# ---------- 2. GitHub 认证 ----------
echo "[2/$TOTAL] GitHub 认证测试"
if [ "$SSH_CHANNEL_OK" -eq 0 ]; then
  if timeout 15 git ls-remote https://github.com/emallsoon/emallsoon-agent.git HEAD >/dev/null 2>&1; then
    ok "HTTPS 匿名访问 GitHub 正常（pull/fetch 可用）"
  else
    warn "HTTPS 访问 GitHub 失败，检查网络"
  fi
else
  AUTH=$(timeout 20 ssh -T github-proxy 2>&1 || true)
  if echo "$AUTH" | grep -q "successfully authenticated"; then
    ok "认证成功，可 push"
  else
    warn "认证未通过：$AUTH"
    echo "     → 若刚生成新密钥，需用户添加公钥后重跑本脚本"
  fi
fi

# ---------- 3. 仓库与工作区状态 ----------
echo "[3/$TOTAL] 仓库状态"
if [ -d "$REPO/.git" ]; then
  cd "$REPO"
  DIRTY=$(git status --short | wc -l)
  [ "$DIRTY" -eq 0 ] && ok "工作区干净" || warn "有 $DIRTY 个未提交变更（先 git add/commit）"
  ok "当前提交: $(git log --oneline -1)"
else
  warn "仓库不存在！克隆中（公开仓库，无需认证）："
  git clone "$CLONE_URL" "$REPO" && ok "克隆完成" || warn "克隆失败，检查网络/代理"
  cd "$REPO" 2>/dev/null || exit 1
fi

# ---------- 4. 依赖安装 ----------
echo "[4/$TOTAL] Node 依赖"
if [ -x node_modules/.bin/astro ]; then
  ok "node_modules 已存在"
else
  npm install --no-audit --no-fund 2>&1 | tail -1 && ok "依赖安装完成" || warn "安装失败"
fi

# ---------- 5. 构建验证 ----------
echo "[5/$TOTAL] 构建验证"
BUILD=$(npm run build 2>&1 | tail -2)
if echo "$BUILD" | grep -q "Complete!"; then
  ok "构建通过（$(echo "$BUILD" | grep -o '[0-9]* page' | head -1)）"
else
  warn "构建异常：$BUILD"
fi

# ---------- 6. 远程同步状态 ----------
echo "[6/$TOTAL] 远程对比"
timeout 30 git fetch origin 2>/dev/null && \
  ok "origin 同步: $(git rev-list --count origin/main..main 2>/dev/null || echo '?') 个本地未推送" || \
  warn "fetch 失败（认证或网络）"

# ---------- 7. 真实浏览器恢复（Chrome DevTools MCP） ----------
echo "[7/$TOTAL] 真实浏览器（chrome-devtools-mcp）"
if [ -x /opt/google/chrome/chrome ] && /opt/google/chrome/chrome --version >/dev/null 2>&1; then
  ok "浏览器就绪: $(/opt/google/chrome/chrome --version 2>/dev/null)"
else
  if bash "$REPO/scripts/setup-browser.sh" >/dev/null 2>&1; then
    ok "已通过 setup-browser.sh 恢复浏览器"
  else
    warn "浏览器恢复失败（不影响构建/部署，仅影响真实浏览器验证）"
    echo "     → 手动排查: bash $REPO/scripts/setup-browser.sh"
  fi
fi

echo "=========================================="
echo " 完成：$PASS 项通过"
echo " 下一步：bash $REPO/scripts/backup-ssh.sh 可刷新密钥备份"
echo "        bash $REPO/scripts/browser-shot.sh <url> <png> 网页截图"
echo "=========================================="
