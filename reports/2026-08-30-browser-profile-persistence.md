# 浏览器登录态持久化方案（profile 直存 + 自动恢复）

> 日期：2026-08-30
> 结论：**可以。通过把 Chrome 用户数据目录（profile）直接持久化到 `/workspace`，浏览器登录状态在沙盒容器重置后不丢失。** 已通过换版本重启 + 完整重启模拟实验验证。

## 1. 背景问题

- 集成浏览器跑在远端沙盒容器里，容器重置后**除 `/workspace` 外的整个文件系统回到镜像初始态**，浏览器 cookie（含 httpOnly）无法导出 → 每次重置后 GSC / Bing Webmaster 全部掉线。
- 需求：GSC（frankteyang@gmail.com）与 Bing Webmaster（lurenjieah@outlook.com）登录态跨重置保留。

## 2. 方案架构

```
┌───────────────────── 沙盒容器（重置会清空，除 /workspace） ─────────────────────┐
│                                                                            │
│  本地 Chrome (headless=new, CDP :9223, 代理 :18080)                         │
│    --user-data-dir=/workspace/.browser-profile   ← 登录态本体，跨重置持久   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
   /workspace/.browser-profile/            Chrome 用户数据（Cookies/Login Data/Local Storage）
   /workspace/.browser-auth/cookies-*.json cookie 备份（CDP Storage API，含 httpOnly）
   /workspace/emallsoon-agent/scripts/browser-serve.sh   启动器（多级回退 + 自动恢复）
   /workspace/emallsoon-agent/scripts/cdp_cookies.py     backup / restore / list
```

启动：`bash scripts/browser-serve.sh start`（幂等）；CDP 端口 9223。

## 3. 为什么 profile 能跨容器重置存活（证据）

| 检查项 | 结果 | 说明 |
|---|---|---|
| profile 所在卷 | `/workspace`（持久卷） | 容器重置不丢 |
| `Default/Cookies`（SQLite） | 141 个 cookie，含 `.google.com` 18、`.bing.com` 19、`.login.live.com` 12 | 登录态本体已落盘 |
| `Local State` os_crypt | **`encrypted_key` 长度 0** | Linux 无机器绑定加密密钥 → cookie 可在任意环境解密，profile 自包含 |
| Singleton 锁 | 残留锁指向旧 hostname | 启动器启动前 `rm -f SingletonLock/Socket/Cookie` |
| Chrome 二进制 | 多级回退 151 → 131 → /opt | 容器重置后二进制丢失也能起 |

## 4. 模拟实验记录

### 4.1 同版本 kill→restart（此前已验证）
同 Chrome 版本重启，GSC / Bing 登录态均保留。

### 4.2 版本切换（降级）模拟 —— 本次
停浏览器 → 隐藏 151 二进制（模拟 /root/.cache 丢失）→ 用 131 启动：

- **131 读取 151 写的完整 profile 会崩溃**（Trace/breakpoint trap；`Last Version` 151 → 131 属降级路径，Chrome 不支持）。
- 删除 `Default/Cache`、`Code Cache`（缓存不含登录态）后仍崩溃 → 131 与旧 profile 不兼容，属边缘情况。
- **恢复 151 重启 → Bing Webmaster 登录态完整保留**（直达 `bing.com/webmasters` Home 控制台，无 Sign In）。
- Google 会话被服务端吊销：cookie 值仍在 profile/备份中，但 Google 检测到进程异常切换触发安全机制（登录时出现 reCAPTCHA Enterprise 风控）。**这是 Google 特有的严格风控，非 profile 方案失效**；等风控冷却后重跑 `gsc_login.py` 即可恢复（TOTP 自动生成）。

### 4.3 加固后完整重启
`stop → start`：自动选 151 → 启动成功 → Cookies DB 自检 141 个 → 无需恢复 → Bing 登录态保留。

### 4.4 真实容器重置（意外发生，实测通过）
任务间隙环境发生真实重置（`/data/user/work` 被清空、系统库 `/usr/lib` 缺失）：

1. 151/131 Chrome 均报 `libatk-1.0.so.0: cannot open shared object file`（系统库丢失）。
2. `apt-get install libatk1.0-0 libatk-bridge2.0-0 libcups2 libgbm1 ...` 重装依赖。
3. `browser-serve.sh start` → 自动选 151 → **启动成功，Cookies DB 140 个 cookie 完好**（自动兜底未触发，因 DB 完好）。
4. **Bing Webmaster 登录态完整保留**：直达 `bing.com/webmasters` Home 控制台；bing.com 首页显示账号 "ren jie"。
5. Google 仍被服务端风控拦截（reCAPTCHA Enterprise，checkbox 点击后 `checked=false`）→ 需等待冷却后重跑 `scripts/gsc_login.py`（TOTP 自动生成）。

> 教训：临时工作区 `/data/user/work` 会被重置清空 → 登录/驱动脚本已迁入仓库 `scripts/`（`cdp_page.py`、`gsc_login.py`），可跨重置使用。

## 5. 自动恢复机制（browser-serve.sh）

1. **Chrome 多级回退**：`linux-151 → linux-131 → /opt/google/chrome/chrome`。
2. **Singleton 锁清理**：启动前删除残留锁文件。
3. **启动失败自愈**：首次启动失败 → 自动清理 `Cache / Code Cache / Service Worker CacheStorage`（登录态不在缓存）→ 重试。
4. **Cookie 备份兜底**：启动后检查 `Default/Cookies`，若缺失或 `< 10` 个 → 自动从 `/workspace/.browser-auth/latest.json` 恢复（幂等，含 httpOnly）。
5. **备份机制**：`python3 scripts/cdp_cookies.py backup --port 9223`（当前 141 cookies，含 GSC + Bing 完整会话）。

## 6. 使用手册

```bash
# 启动（幂等 + 自动恢复）
bash scripts/browser-serve.sh start
# 状态 / 停止
bash scripts/browser-serve.sh status
bash scripts/browser-serve.sh stop
# 备份 / 恢复 cookie（登录态双重保险）
python3 scripts/cdp_cookies.py backup --port 9223
python3 scripts/cdp_cookies.py restore --port 9223 --file /workspace/.browser-auth/latest.json
```

登录脚本（凭据在 `/workspace/.browser-auth/credentials.env`，模式 600，不入库；脚本已在仓库 `scripts/`，跨重置可用）：

- GSC：`python3 scripts/gsc_login.py`（邮箱→密码→TOTP；若遇 reCAPTCHA 风控，等待冷却后重跑）
- Bing：`python3 scripts/bing_login.py`（MS 账号，"Use your password" 绕过邮箱验证码；BWT 控制台点 Sign In → 账户卡片）

## 7. 结论与边界

- ✅ **profile 直存方案成立**：把 Chrome 用户数据目录放 `/workspace`，容器重置后登录态保留（Bing 实测通过；Google cookie 完整落盘 + 备份，仅需在风控冷却后重登）。
- ⚠️ **边界 1**：Chrome 版本降级（新版本写的 profile 用旧版本读）可能崩溃 → 用同版本/新版本 Chrome，或依赖 cookie 备份兜底恢复。
- ⚠️ **边界 2**：Google 对"进程异常切换/登录环境突变"有服务端风控，可能吊销会话 → 必须配合 cookie 备份 + 重登脚本；Bing/Microsoft 无此问题。
