#!/usr/bin/env python3
"""容器重置后的一键环境自检/自修复。

用法:
    python3 env_check.py            # 只检查+能安全自动修的直接修(ssh恢复/清陈旧锁)
    python3 env_check.py --no-net   # 跳过需要联网的检查项
    python3 env_check.py --backup-profile  # 顺带打包整份 profile 快照(保留最近2份)

设计目标（2026-09-01 容器重置复盘）:
  重置只清系统层(/root 下的 ~/.ssh、系统 .so 等)，/workspace 全部幸存。
  因此把所有关键资产都锚定在 /workspace，本脚本负责在重置后快速校验+修复:
    1. ~/.ssh 缺失     → 从 /workspace/.ssh-backup 恢复（兼容旧路径）
    2. git push 通道    → 仓库级 core.sshCommand 已指向 workspace 内 ssh 配置,
                          不依赖 ~/.ssh;缺了就自动补
    3. CloakBrowser    → pip 包 / Chromium 二进制 / 5 个系统库 / ldd 缺失数
    4. 浏览器 profile   → 存在、SingletonLock 陈旧清理、cookie 备份新鲜度
    5. 沙盒时钟漂移     → HTTP Date 权威时间 vs 系统时间偏差(>5min 警告)
    6. git 远端连通     → git ls-remote 实测(--no-net 跳过)
退出码: 0=全部健康, 1=存在未解决问题
"""
import os
import sys
import glob
import subprocess

sys.path.insert(0, "/workspace/.pylibs")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cloak_common as cc  # noqa: E402

REPOS = ["/workspace/emallsoon-agent", "/workspace/emallsoon"]
SSH_BACKUP = "/workspace/.ssh-backup"
SNAP_DIR = "/workspace/.profile-snapshots"

problems = []


def ok(msg):
    print(f"  ✅ {msg}")


def warn(msg, fixed=False):
    tag = "已修复" if fixed else "待处理"
    print(f"  ⚠️ {msg} [{tag}]")
    if not fixed:
        problems.append(msg)


def check_ssh():
    print("[1] ~/.ssh")
    need = ("config", "id_ed25519", "id_ed25519.pub", "known_hosts")
    missing = [f for f in need if not os.path.exists(os.path.expanduser(f"~/.ssh/{f}"))]
    if not missing:
        ok("~/.ssh 齐全")
        return
    try:
        os.makedirs(os.path.expanduser("~/.ssh"), exist_ok=True)
        for f in need:
            src = os.path.join(SSH_BACKUP, f)
            if os.path.exists(src):
                subprocess.run(["cp", src, os.path.expanduser(f"~/.ssh/{f}")], check=True)
        os.chmod(os.path.expanduser("~/.ssh/id_ed25519"), 0o600)
        warn(f"~/.ssh 缺 {missing}，已从 {SSH_BACKUP} 恢复", fixed=True)
    except Exception as e:  # noqa: BLE001
        warn(f"~/.ssh 缺失且恢复失败: {e}")


def check_git_ssh():
    print("[2] git push 通道（core.sshCommand 指向 workspace 内配置）")
    want = "ssh -F /workspace/.ssh-backup/config"
    for repo in REPOS:
        if not os.path.isdir(os.path.join(repo, ".git")):
            warn(f"{repo} 不是 git 仓库")
            continue
        cur = subprocess.run(["git", "-C", repo, "config", "core.sshCommand"],
                             capture_output=True, text=True).stdout.strip()
        if want in cur:
            ok(f"{os.path.basename(repo)}: 免 ~/.ssh 通道已配置")
        else:
            subprocess.run(["git", "-C", repo, "config", "core.sshCommand", want], check=True)
            warn(f"{os.path.basename(repo)}: 补配 core.sshCommand", fixed=True)
    if not os.path.exists(os.path.join(SSH_BACKUP, "config")):
        warn(f"{SSH_BACKUP}/config 不存在")


def check_browser():
    print("[3] CloakBrowser 栈")
    if os.path.isdir("/workspace/.pylibs/cloakbrowser"):
        ok("pip 包 cloakbrowser (/workspace/.pylibs)")
    else:
        warn("pip 包缺失: /workspace/.pylibs/cloakbrowser")

    bins = glob.glob("/workspace/.cloakbrowser/chromium-*/chrome") or \
           glob.glob("/workspace/.cloakbrowser/chromium-*/chrome-linux/chrome") or \
           glob.glob("/workspace/.cloakbrowser/chrome-linux/chrome")
    if bins:
        ok(f"Chromium 二进制: {bins[0].replace('/workspace/', '')}")
        r = subprocess.run(["ldd", bins[0]], capture_output=True, text=True,
                           env={**os.environ,
                                "LD_LIBRARY_PATH": "/workspace/.cloakbrowser/libs:"
                                + os.environ.get("LD_LIBRARY_PATH", "")})
        miss = [ln.strip() for ln in r.stdout.splitlines() if "not found" in ln]
        if miss:
            warn(f"ldd 缺 {len(miss)} 个依赖: {miss[:3]}")
        else:
            ok("ldd 无缺失依赖")
    else:
        warn("Chromium 二进制缺失")

    libs = ("libXcomposite.so.1", "libXdamage.so.1", "libatk-1.0.so.0",
            "libatk-bridge-2.0.so.0", "libatspi.so.0")
    lack = [l for l in libs if not os.path.exists(f"/workspace/.cloakbrowser/libs/{l}")]
    if not lack:
        ok(f"5 个系统库齐全 (/workspace/.cloakbrowser/libs)")
    else:
        warn(f"系统库缺 {lack}")


def check_profile():
    print("[4] 浏览器 profile 与登录态")
    if not os.path.isdir(cc.PROFILE):
        warn(f"profile 不存在: {cc.PROFILE}（GSC/BWT 登录态将丢失，需人工重登）")
        return
    ok(f"profile 存在 ({cc.PROFILE})")
    cc.setup_env()  # 顺带清陈旧 SingletonLock
    path, ptr = cc.latest_backup_path()
    if path and os.path.exists(path):
        ok(f"cookie 备份: {os.path.basename(path)} ({ptr.get('total', '?')} 条)")
    else:
        warn("无 cookie 备份可用")


def check_clock():
    print("[5] 沙盒时钟")
    skew = cc.clock_skew_s()
    if skew is None:
        warn("取不到 HTTP Date 权威时间（报告将退回系统时钟）")
        return
    if abs(skew) > 300:
        warn(f"系统时钟偏差 {skew:+.0f}s（>5min）——报告时间已自动改用 HTTP Date，不受影响")
    else:
        ok(f"系统时钟偏差 {skew:+.0f}s（正常）")


def check_remote():
    print("[6] git 远端连通")
    for repo in REPOS:
        r = subprocess.run(["git", "-C", repo, "ls-remote", "origin", "main"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            ok(f"{os.path.basename(repo)}: ls-remote OK")
        else:
            warn(f"{os.path.basename(repo)}: ls-remote 失败: {r.stderr.strip()[:100]}")


def backup_profile():
    print("[7] profile 快照")
    os.makedirs(SNAP_DIR, exist_ok=True)
    ts = cc.bj_date("%Y%m%d-%H%M%S")
    fn = os.path.join(SNAP_DIR, f"profile-{ts}.tar.gz")
    r = subprocess.run(
        ["tar", "czf", fn, "--exclude", "SingletonLock", "--exclude", "SingletonSocket",
         "--exclude", "SingletonCookie", "-C", "/workspace", ".browser-profile-cloak"],
        capture_output=True, text=True)
    if r.returncode == 0:
        size = os.path.getsize(fn) / 1e6
        ok(f"快照已存: {os.path.basename(fn)} ({size:.0f}MB)")
        snaps = sorted(glob.glob(os.path.join(SNAP_DIR, "profile-*.tar.gz")))
        for old in snaps[:-2]:  # 只保留最近 2 份
            os.remove(old)
            print(f"     轮转删除: {os.path.basename(old)}")
    else:
        warn(f"快照失败: {r.stderr.strip()[:100]}")


def main():
    args = sys.argv[1:]
    print(f"== emallsoon 环境自检 {cc.bj_now().strftime('%Y-%m-%d %H:%M')} (北京时间) ==")
    check_ssh()
    check_git_ssh()
    check_browser()
    check_profile()
    if "--no-net" not in args:
        check_clock()
        check_remote()
    if "--backup-profile" in args:
        backup_profile()
    print("=" * 46)
    if problems:
        print(f"结论: ❌ {len(problems)} 项待处理")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("结论: ✅ 环境健康，监控脚本可直接运行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
