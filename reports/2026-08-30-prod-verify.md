# 2026-08-30 线上部署验证报告

> 目标:emallsoon.com(Cloudflare Pages 免费层)
> 触发:本地测试与适配完成后(commit de5ff7b),验证线上状态
> 结论:**全部通过,线上与本地构建 11/11 页零偏差**

## 一、可用性与性能

| 指标 | 实测值 | 评价 |
|------|--------|------|
| HTTP 状态 | 全站 200 | ✅ |
| 边缘节点 | Cloudflare 新加坡(cf-ray SIN) | 就近分发 |
| 缓存命中 | cf-cache-status: HIT | ✅ 静态资源已缓存 |
| 首页响应(curl) | 0.18–0.43s | ✅ |
| TTFB(浏览器) | 29ms | ✅ 优秀 |
| LCP(浏览器) | 144ms | ✅ 远优于 2.5s 阈值 |
| DOM Ready | 58ms | ✅ |
| 首页传输量 | 6.9KB(gzip) | ✅ 极轻 |

## 二、全页面扫描(16 项)

- 12 内容页 + robots.txt + sitemap-index.xml + sitemap-0.xml + favicon.svg → 全部 **200**
- 未知路径 → 正确 **404**(自定义 404 页生效)

## 三、线上 vs 本地构建一致性(11/11 零偏差)

规范化(去时间戳)后逐页 MD5 对比:

| 页面 | 一致性 |
|------|--------|
| 首页 + 9 工具页 + about | ✅ 全部 hash 一致 |

**说明:生产部署与镜像仓库 main 分支构建完全同步,费率数据(含 Shopify Advanced 0.6% 修正)已是线上最新。**

## 四、浏览器实测(Chrome 151 直连)

| 检查项 | 结果 |
|--------|------|
| 11 页控制台错误 | **0** |
| 失败网络请求 | **0**(Google Fonts 正常加载) |
| 计算器表单渲染 | 9 页全部正常(6–12 输入框/页) |
| 页面加载耗时 | 601–2003ms/页 |

## 五、产出

- 线上首页截图:`docs/screenshots/2026-08-30-prod-verify-home.png`
- 本报告:`reports/2026-08-30-prod-verify.md`

## 六、后续建议(非阻塞)

1. `content-type: text/html` 未带 `charset=utf-8`——Cloudflare Pages 层面行为,如需精确控制可加 `_headers` 文件
2. Google Search Console 提交 sitemap 后可持续观察收录(9 个工具页均已具备独立 title/canonical/JSON-LD)
3. 商业路线:流量过万后按计划接入 Ezoic
