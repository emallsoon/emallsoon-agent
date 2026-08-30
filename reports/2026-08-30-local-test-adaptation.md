# 2026-08-30 本地测试与环境适配报告

> 执行环境:SOLO 沙箱(AWS EC2 吉隆坡,Ubuntu 22.04,3C/6G)。
> 仓库:`/workspace/emallsoon-agent`(镜像仓库 HTTPS 克隆)。
> 本报告与 AGENTS.md 中"中国大陆出口 + GFW"档案基于不同出口,已按本环境重新适配。

## 一、测试结果汇总

| # | 测试项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | `npm install` | ✅ | 依赖安装正常 |
| 2 | `npm run build` | ✅ | 12 页构建,1.4s,sitemap 自动生成 |
| 3 | 构建产物完整性 | ✅ | 12 HTML + sitemap 12 URL + robots.txt + favicon |
| 4 | 路由可访问性(15 项) | ✅ | 全部 200;未知路径正确 404 |
| 5 | 内链完整性 | ✅ | 12 页全站扫描,0 死链 |
| 6 | SEO 抽查 | ✅ | 独立 title;JSON-LD 存在(WebSite/WebApplication) |
| 7 | 费率落页验证 | ✅ | Shopify Advanced 0.6% 已落页(select option + FAQ 文案) |
| 8 | 浏览器全站测试(11 页) | ✅ | 0 控制台错误,0 失败请求,Google Fonts 直连正常 |
| 9 | 计算器逻辑实测(Etsy) | ✅ | 手工验算一致:$34.50 收入 − 0.20 − 2.24 − 1.29 − 10 − 3.20 = **$17.57**,margin 50.9% |
| 10 | 表单渲染 | ✅ | 9 个计算器页表单齐全(6–12 输入框/页) |
| 11 | 视觉截图 | ✅ | 3 张存档 `docs/screenshots/2026-08-30-local-verify-*.png` |
| 12 | bootstrap.sh 全流程 | ✅ | 7 步中 6 ✅ 1 预期内警告(SSH 通道,见下) |

## 二、环境差异(与 AGENTS.md 档案对照)

| 事项 | 原档案(旧沙箱) | 本环境实测 |
|------|----------------|-----------|
| 出口位置 | 中国大陆(天津电信,GFW) | **AWS 吉隆坡** |
| Google 直连 | ❌ 被墙 | ✅ 直连可用(约 80ms) |
| GitHub HTTPS | ✅ | ✅(0.1s) |
| SSH 22 直连 | ❌ 须经代理 | ❌ 超时 |
| ssh.github.com:443 | 走代理可用 | ❌ 直连与经代理均不通 |
| 沙箱代理 18080 | 出站代理 | 存在;**对回环目标返回 403** |
| /workspace/.ssh-backup | 持久备份 | 不存在(全新环境) |
| 浏览器 profile | 持久 | 不存在(已重建并重新持久化) |

**结论:本环境 git 唯一可靠通道是 HTTPS**(pull/fetch/push 均需 HTTPS 凭据;匿名 pull 已验证可用)。

## 三、发现的问题与适配

### 问题 1:本地页面在浏览器中 403(已修复)
- 现象:Chrome 打开 `localhost:4321` 返回 403,curl 却正常
- 根因链:旧包装器兜底分支 `--proxy-bypass-list="<-loopback>"` 的语义是**移除** Chrome 默认的回环绕过 → localhost 强制走 18080 代理 → 沙箱代理对回环目标 403
- 适配:`setup-browser.sh` 兜底分支改为**直连无代理**(按用户决定;海外出口直连可达),并删除有害参数

### 问题 2:`--proxy-bypass-list` 非法值会静默挂死 Chrome(排障存档)
- 现象:传 `--proxy-bypass-list=*` 后所有页面 Navigation timeout,无任何控制台报错
- 教训:该参数值格式非法时 Chrome 网络栈整体失效,极易误判为"服务挂了"

### 问题 3:astro preview 仅监听 IPv6(适配提醒)
- 现象:`npm run preview` 默认只监听 `[::1]:4321`,Chrome 直连 `127.0.0.1` 被拒
- 适配:本地测试用 `npx astro preview --host 0.0.0.0`,测试脚本一律用 `127.0.0.1`

### 问题 4:bootstrap.sh 硬编码路径与 SSH 假设(已修复)
- `REPO=/workspace/emallsoon` → 改为自动探测(emallsoon → emallsoon-agent 回退)
- SSH 步骤 → 先探测通道可用性,不可用则明确切换 HTTPS 模式提示,不再生成无效配置
- 克隆 URL → 参数化 `$CLONE_URL`

## 四、本次产出变更(git 未提交)

- `M scripts/bootstrap.sh` — 路径探测 + SSH 通道探测 + HTTPS 模式
- `M scripts/setup-browser.sh` — 包装器去代理 + 踩坑存档注释
- `?? docs/screenshots/2026-08-30-local-verify-{home,shopify,compare}.png` — 本地验证截图

## 五、遗留事项

1. **push 通道**:本环境 SSH 全禁,推送需 HTTPS 凭据(token)或换环境;变更已在本地 commit 待推
2. **AGENTS.md 环境档案**:其"网络出口与封锁档案"章节基于旧出口,接手其他环境时以实测为准,勿直接套用
3. 每日费率核查定时任务(schedule `79ZQUNK_X.UX.1`)在本会话不可见,属于平台级资源,无需本地处理
