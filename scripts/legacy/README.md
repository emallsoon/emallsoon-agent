# legacy/ —— Chrome/CDP 时代脚本（已退役）

> 2026-08-31 引擎切换：bare Chrome（CDP :9223）→ **CloakBrowser**（Playwright drop-in，Chromium 146 源码级反指纹补丁）。
> 以下脚本基于已卸载的 Chrome 二进制 / CDP 端口 / Xvfb GUI，仅作历史参考保留，**不要再使用**。

| 脚本 | 当年用途 | 替代品 |
|---|---|---|
| `setup-browser.sh` | 安装 Chrome + 依赖 | `pip install 'cloakbrowser[serve,geoip]'`（见 `../bootstrap.sh` 步骤 7） |
| `browser-shot.sh` | CDP 9223 截图 | `../cloak_check.py`（自带截图 `/workspace/cloak-check-*.png`） |
| `cdp_page.py` / `cdp_cookies.py` | CDP 页面驱动 / cookie backup-restore | `../cloak_common.py`（`restore_cookies` / `backup_cookies`，自动随 serve 退出备份） |
| `gsc_login.py` / `gsc_login9.py` / `gsc_challenge_hold.py` | GSC 登录 / reCAPTCHA 对抗（被风控挡住） | `../cloak_gsc_login.py`（CloakBrowser 下**无挑战**，一次成功） |
| `bing_login.py` | BWT 登录 | 不再需要：cookie 备份恢复即在线，掉线时参考其流程手写 |
| `rc_gui.py` / `rc_probe.py` / `diag_gui.py` | reCAPTCHA GUI/无头探测诊断 | 已无必要 |

当前有效入口见 `../browser-serve.sh`（start/stop/restart/status/check）。
