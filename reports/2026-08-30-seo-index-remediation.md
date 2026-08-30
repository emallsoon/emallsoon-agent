# emallsoon.com SEO 收录治理报告（2026-08-30）

## 背景

在 Bing Webmaster 中发现 `www.emallsoon.com` 的站点地图异常：当前站点地图仅显示「已发现 1 个 URL」。排查与治理过程如下。

## 根因

- 线上 `sitemap-index.xml` 是一个索引文件，内含 1 个子站点地图引用（`sitemap-0.xml`，实际 11 个 URL）；
- Bing 统计时只按索引文件的条目数计数（1 条），未展开子文件，导致显示「1 URL discovered」；
- 另有两个 2025 年遗留站点地图（`sitemap.rss` 50 URLs、`sitemap.xml` 5 URLs），属于域名前身的旧站数据，产生干扰。

## 处置与结果

### 1. Bing：清理遗留站点地图 + 直提子站点地图 ✅

- 删除 `sitemap.rss`（2025，50 URLs）与 `sitemap.xml`（2025，5 URLs）；
- 直接提交子站点地图 `https://emallsoon.com/sitemap-0.xml`；
- 结果：**Success，已发现 11 个 URL**；当前已知站点地图 2 个（`sitemap-index.xml` + `sitemap-0.xml`）。

### 2. www / 非 www 主机统一 ✅（无需改动）

- 线上：`www.emallsoon.com` → 301 → `emallsoon.com`（规范主机为非 www，站点地图内 URL 均为非 www，与 canonical 一致）；
- GSC：账号中已存在**域名级资源 `sc-domain:emallsoon.com`**，天然覆盖 www/非 www、http/https 全部变体，无需新建资源或验证标签；
- Bing：站点记录按域名去重（手动添加 `emallsoon.com` 提示 "Site already added."），www 与非 www 同属一个站点记录（2025 年 3 月的检查历史中两种主机的 URL 都在同一记录下），无需新增站点、部署 `msvalidate.01` 标签或删除旧站点。

### 3. GSC：逐页核查 11/11 ✅（全部已收录，无需请求）

在域名资源下通过「网址检查」逐页核查全部 11 个规范 URL，结果一致：

- ✅ 网址已收录到 Google
- ✅ 网页索引编制：网页已编入索引
- ✅ HTTPS：网页采用 HTTPS 协议
- ✅ 增强功能：路径（面包屑）检测到 1 项有效内容（工具页与 /about/）

**结论：Google 侧收录完整，无需消耗「请求编入索引」配额。**

### 4. Bing：逐页请求索引 10/11 ✅（受每日配额限制）

- 现状：多数 URL 的 Bing Index 历史状态为 `Blocked` / `Discovered but not crawled`（域名 2025 年前身为旧内容站的历史判定，非当前页面问题）；
- Live URL 实测：`URL can be indexed by Bing`、`No SEO/GEO issues found`、`2 Markup types found` —— 实时页面健康；
- 今日已通过 URL Inspection → Request indexing 提交 **10 个 URL**（每日配额 10 条，已用尽）：

| # | URL | 提交结果 |
|---|-----|---------|
| 1 | `https://emallsoon.com/` | ✅ submitted successfully |
| 2 | `/tools/amazon-fba-profit-calculator/` | ✅ |
| 3 | `/tools/break-even-units-calculator/` | ✅ |
| 4 | `/tools/discount-pricing-calculator/` | ✅ |
| 5 | `/tools/ebay-fee-calculator/` | ✅ |
| 6 | `/tools/etsy-fee-calculator/` | ✅ |
| 7 | `/tools/platform-fee-comparison/` | ✅ |
| 8 | `/tools/roas-break-even-calculator/` | ✅ |
| 9 | `/tools/shopify-profit-margin-calculator/` | ✅ |
| 10 | `/tools/tiktok-shop-fee-calculator/` | ✅ |
| 11 | `/about/` | ⏳ 待明日配额恢复后补提（对话框确认 Quota left: 0） |

## 遗留待办

1. **明日**：Bing URL Inspection 补提 `https://emallsoon.com/about/`；
2. **观察期（1–2 周）**：复查 Bing Index 状态是否由 Blocked → Indexed；GSC「网页索引编制」报告数据正在处理中（提示约 1 天后可查看），届时核对 11/11；
3. 无需任何代码改动（验证标签、canonical 均无需调整）。

## 附：11 个规范 URL 清单（非 www + 尾斜杠）

```
https://emallsoon.com/
https://emallsoon.com/about/
https://emallsoon.com/tools/amazon-fba-profit-calculator/
https://emallsoon.com/tools/break-even-units-calculator/
https://emallsoon.com/tools/discount-pricing-calculator/
https://emallsoon.com/tools/ebay-fee-calculator/
https://emallsoon.com/tools/etsy-fee-calculator/
https://emallsoon.com/tools/platform-fee-comparison/
https://emallsoon.com/tools/roas-break-even-calculator/
https://emallsoon.com/tools/shopify-profit-margin-calculator/
https://emallsoon.com/tools/tiktok-shop-fee-calculator/
```
