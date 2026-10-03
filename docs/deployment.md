# qier.asia 部署与维护

当前验收版本：`20261003T052451Z-7ac82b1`，发布于 2026-10-03 13:26 左右（Asia/Taipei），在 PR #12 版本上加入资料库（名词收藏复习）。详见文末；更早的发布见 [性能与部署](2026-10-03-performance-and-deployment.md)。

> 当前站点无需登录，案卷、材料、聊天和生成结果按浏览器身份隔离。无法确认归属的历史案卷隐藏但保留，只有主动提交的评价公开。`XRAY_PRIVATE_DIR` 已持久化；公网验证了 HttpOnly、Secure、SameSite=Lax 和 API 的 private/no-store。维护时仍需遵循 [小企与私有案卷交接](2026-10-03-assistant-privacy-handoff.md)。

首次部署验收于 2026-10-03 00:23，00:27 移除全站访问口令；最初版本曾使用共享案卷，后续升级已改为上述隔离方式。下方按日期保留历次部署记录，不把旧验收状态当作当前状态。

## 访问与架构

- 网站：https://qier.asia ，另支持 https://www.qier.asia 。Cloudflare DNS 中两个 A 记录均指向 `47.82.79.13`，已开启代理；公网解析会返回 Cloudflare 边缘地址。
- 2026-10-03 10:49 已验证 Cloudflare 接管、Universal SSL、Full (strict)，以及两个域名静态缓存命中和 API 绕过缓存。详见 [本轮性能与发布记录](2026-10-03-performance-and-deployment.md)。
- 阿里云轻量应用服务器，中国香港，Ubuntu 24.04，2 核、1GB 内存、30GB 系统盘；增加了 1GB swap。
- 首页在开发机执行 `research-room` 的 `npm run build:home` 后上传。服务器运行单个 FastAPI/Uvicorn 进程，同时提供首页、报告、演示页和 API。
- Caddy 在 80/443 端口处理 HTTP→HTTPS、自动申请/续期证书和反向代理。Uvicorn 仅监听 `127.0.0.1:8000`。
- systemd 管理 `qier` 和 `caddy`，均已设为开机启动。qier 故障时自动重启，最多同时运行 2 个研究任务。
- 静态缓存：带内容哈希的 `/office/assets/` JS/CSS 缓存 1 年；`/research-assets/` 图片缓存 1 天；API 使用 `no-store`，HTML 使用 `no-cache` 重新验证。更新图片时要同步更新引用中的内容哈希查询参数。

网站不再要求用户名或密码。原口令文件按不删除文件的要求保留为历史记录，已不参与网站鉴权；SSH 密钥及服务器私有配置仍用于服务器维护。

## 服务器文件

| 路径 | 用途 |
|---|---|
| `/opt/qier/releases/20261002T152239Z` | 本次部署的代码、页面和公开资料 |
| `/opt/qier/current` | 当前版本链接，指向 `/opt/qier/releases/20261003T052451Z-7ac82b1` |
| `/opt/qier/venv` | 独立 Python 环境 |
| `/opt/qier/current/requirements-deployed.txt` | 服务器实际安装的完整依赖版本 |
| `/etc/qier/backend.env` | 私有模型/企查查配置，由 systemd 加载，不在网站静态目录中 |
| `/etc/systemd/system/qier.service` | 后端服务定义 |
| `/etc/caddy/Caddyfile` | HTTPS 及反向代理配置；无登录要求 |
| `/var/lib/qier/cases` | 案卷与聊天 |
| `/var/lib/qier/reviews` | 用户评价 |
| `/var/lib/qier/cache` | 模型与商业数据缓存 |
| `/var/lib/qier/runs` | 查询进度与恢复记录 |
| `/var/backups/qier/qier-20261002T162318Z.tar.gz` | 首次验收备份，含运行数据及私有配置，仅 root 可读 |
| `/etc/qier/verification-20261003.json` | HTTPS、鉴权及重启后数据完整性的验收结果 |

本次没有上传本机历史案卷、评价、运行记录和缓存。生产数据独立于发布目录，新版本发布应继续使用 `/var/lib/qier`。

## 维护

在开发机用已绑定的密钥以 root 登录。当前可用的本机密钥副本为 `C:/Users/Weichen Li/.ssh/qier-ww-20261002.pem`；该副本已限制为当前用户可访问。

```powershell
ssh -i "C:/Users/Weichen Li/.ssh/qier-ww-20261002.pem" root@47.82.79.13
```

登录后查看服务状态和日志：

```sh
systemctl status qier caddy --no-pager
journalctl -u qier -n 100 --no-pager
journalctl -u caddy -n 100 --no-pager
curl --fail http://127.0.0.1:8000/api/health
```

调整 `/etc/qier/backend.env` 后需要重启 qier；修改 Caddyfile 后先校验，再 reload。先确认没有进行中的查询和问答，避免中断请求。

```sh
systemctl restart qier
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy
```

本地改代码、提交或推送 Git 不会自动更新网站。下一次发布应创建新的版本目录，重新构建首页，保留旧版本和现有配置，验证后切换版本并重启服务。不要覆盖运行数据，不要把本机 `.venv` 或 `node_modules` 上传到服务器。

没有配置定期备份；上述备份是本次验收时的一次性快照。不要把包含密钥或用户数据的备份提交到 Git。按工作区要求，不删除任何文件；清理历史版本或备份须由用户自行执行。

## 本次验证

- 00:27 免登录变更：两个域名的首页、报告、健康接口、示例与案卷列表均在无凭据情况下返回 200；不合法的匿名创建查询请求返回正常参数校验错误 422，无登录拦截。HTTPS、HTTP 跳转及私有配置路径的 404 检查通过。变更前 Caddyfile 已备份为 `/etc/caddy/Caddyfile.before-public-20261002T162702Z`。
- 首页构建成功，必需图片存在，后端 Python 源码语法检查通过。
- 首次验收时两个域名的 HTTPS 证书有效，访问口令校验通过；此登录要求已在 00:27 移除，上条为当前匿名访问结果。HTTP 返回 308 跳转到 HTTPS。
- `.env`、后端配置和前端源码路径未通过网站暴露，检查路径返回 404。
- 真实浏览器访问首页、点击虚构示例、提交查询、查询中刷新恢复、打开报告完成。查询编号 `1b0fdd2baf1749e5b8a5ee61`，案卷 `8eb78fd87c3b`。
- 小企“持牌名单是什么意思？”返回模型回答，包含 1 个有效名词引用，无引用被丢弃。另一个较宽泛问题的引用未通过校验，界面如实显示无法支持该回答；未将其视作有效事实回答。
- 完成备份后重启后端，重新读取案卷、两轮聊天和查询结果；案卷 JSON 内容及文件 SHA-256 与重启前一致。
- 普通浏览器网络设置下可打开域名；早期命令行直连受到本机代理使用的 `198.18.*` 地址影响，显式解析到服务器 IP 后成功，浏览器正常设置访问也成功。
- 首次问答验收曾返回 500：Ubuntu 无人值守更新重启服务，超过 45 秒的退出等待后中断了请求。系统更新日志在 00:19:48 确认完成，之后问答及主动重启验收通过。没有关闭系统自动更新。
- 本次为部署冒烟验收，没有重跑完整单元测试或完成并发压测。虚构案例中两个外部数据查询失败仍按产品原逻辑显示，没有掩盖为查询成功。

本地证据：`.tmp/deploy-20261002T152239Z/` 下的 HTTP 检查和浏览器快照；截图在 `output/playwright/`。这些本机验收文件不进入仓库。

## 小企动画更新（2026-10-03）

- 已发布 Git 提交 `656634d` 的报告前端、小企动作图及逐帧轮廓样式。当前 `/opt/qier/current` 指向 `/opt/qier/releases/20261002T163911Z-xiaoqi-656634d`。
- 新目录复制自上一生产版本，只覆盖该提交的六个文件，复用原首页构建；没有发布开发机上其他尚未提交的首页优化。
- 切换前确认研究任务租约已结束且没有正在处理的 HTTP 连接，切换后重启 `qier`，健康接口与静态文件校验通过。
- 原版本和原链接都保留：`/opt/qier/releases/20261002T152239Z`、`/opt/qier/current.before-xiaoqi-656634d`。没有删除文件。
- 发布前后首页 SHA-256 相同，现有 14 个案卷、评价及进度文件内容相同。验收记录位于 `/etc/qier/verification-xiaoqi-656634d.json`。
- 已通过公网 HTTPS 打开既有演示报告，确认小企站在输入区上方分隔线、角色外无色块；公网资源哈希与发布文件一致。

## 2026-10-03 00:36 首页加载优化

定位到首次首页图片约 5.18MB，且部署时全局 `private, no-store` 让静态资源无法复用缓存。服务器内部健康检查约 2ms、服务器访问公开首页约 59ms，瓶颈在图片传输和客户端建连。

- 7 张首页/动画/卷宗图片新增高质量 WebP 编码版本（quality=90），保留全部 PNG 原图，尺寸和 alpha 通道逐像素一致。首页最初请求的 4 张主图片从 5,180,486 字节缩小到 820,646 字节，减少 84.2%。
- CSS、React 图片引用加入内容哈希查询参数；HTML 提前 preload 背景图，使其与 JS/CSS 并行下载。
- 分开配置静态缓存与 API 缓存。验证图片和脚本缓存头正确，携带 ETag 的条件请求返回 304。
- 增量发布仅覆盖本次首页构建产物并新增 WebP 图片，旧入口备份在 `/etc/qier/home-before-speed-20261002T163643Z.html`，原图片和旧带哈希构建文件保留。没有发布其他任务正在改动的 `web/` 文件，没有重启后端。
- 验证：首页相关 Node 测试 36 项、后端静态接入测试 4 项通过；浏览器无控制台错误，截图检查通过。

本机单次网络测量（不是并发压测或所有地区保证）：

| 测量 | 首次内容绘制 | 背景图就绪 | 子资源实际传输 |
|---|---:|---:|---:|
| 优化前，普通代理网络 | 12.14s | 图片单次下载约 32s | 主图片约 5.18MB |
| 优化后，无缓存、普通代理网络 | 9.20s | 8.65s | 约 959KB |
| 优化后，无缓存、绕过本机代理并显式解析服务器 IP | 4.44s | 3.48s | 约 959KB |
| 优化后，普通代理网络再次打开、缓存命中 | 0.57s | 0.48s | 约 3.5KB |

普通代理网络首次 TLS 建连测得约 6.49s，直连对照约 1.36s；剩余首次访问延迟受访问线路影响。没有修改用户系统代理、系统 DNS 或 hosts。测量原始记录为本机验收目录下的 `speed-cold.txt`、`speed-warm.txt`、`speed-direct.txt`。

## 2026-10-03 两级加载与原图画质

- 第一层继续使用上述 quality=90 WebP 和背景 preload；不降低像素尺寸。背景预览加载结束、页面 load 完成并绘制后，浏览器在空闲时启动第二层。
- 第二层为 7 张 `.lossless.webp`，经 RGBA 字节比较，与对应 PNG 原图逐像素相同，包括透明通道。背景无损图约 1.43MB，全部无损图约 7.03MB；首次完整升级会在轻量层之外增加这些流量，后续访问可使用缓存。
- 高清图使用低下载优先级、串行加载，解码成功后逐张替换。背景与门叶、桌椅遮挡层共享同一状态，一起切换；图片下载/解码失败或超过 45 秒保留预览，继续加载下一张；页面卸载取消剩余升级。
- 实现位于 `research-room/app/progressive-images.ts` 和 `use-progressive-images.ts`。变更图片时，需同步更新清单中的 URL 哈希、CSS 预览回退 URL，背景预览还需更新 `home/index.html` 的 preload。
- 40 项 Node 测试、4 项后端静态接入测试、TypeScript 检查和生产构建通过。本地浏览器通过延迟真实图片请求验证先显示预览，再切换高清；故意中断高清背景请求后，预览与表单仍可用，其余高清图继续升级。切换前后背景矩形完全相同，无页面脚本错误。失败场景的网络错误为人工注入。
- 本次仅增量上传 14 张 WebP 和当前 JS/CSS/HTML。两次发布前入口分别保存在 `/etc/qier/home-before-progressive-20261002T165355Z.html`、`/etc/qier/home-before-progressive-20261002T165801Z.html`；原 PNG、旧构建文件和当前报告前端均保留，后端 PID 未变化。服务器逐一核对线上文件 SHA-256、缓存头、两个域名首页及健康接口，通过；最终记录为 `/etc/qier/progressive-verification-20261002T165801Z.json`。
- 初次线上测量发现双 requestAnimationFrame 仍可能早于首次内容绘制，因此在支持 Paint Timing 的浏览器上增加首次内容绘制观察，再安排空闲下载。最终普通代理网络单次冷启动：首次内容绘制 9.48s，首次高清请求 9.50s，背景切为原图画质 10.79s，全部高清图约 16s 下载完成；没有页面脚本错误。此流程保留了之前的首屏轻量层，不能消除代理建连等待。页面整体 CLS 为 0.01345；本地受控切换验证背景矩形未发生变化，未将整页表述为零位移。
- 本地证据：`progressive-browser-final.txt`、`progressive-live-final.txt`，截图 `output/playwright/qier-two-stage-*.png`；它们位于忽略目录，不提交。

## 2026-10-03 12:00 五维雷达发布

- 发布提交 `b3b052f`（含 `f723b1b` 五维雷达、`1ee0b2b` 脚本版本号），服务器版本 `/opt/qier/releases/20261003T035908Z-b3b052f`，`XRAY_RELEASE_ID` 同名。复制上一版本后覆盖本次提交的代码，首页用本次提交重新构建；依赖未变，未删除文件。
- 报告雷达去掉“宣传承诺”一维：这一维只来自用户提交的宣传、合同或聊天，没交材料的报告都缺一角。原有条目随风险信号计入经营资格，不丢记录；某一维没有记录时用虚线跨过，不再凹回中心。
- Cloudflare 按版本查询参数缓存 `/xray/*.js` 4 小时（`max-age=14400`），因此改了 `case-design.js` 的 `?v=`。以后改报告脚本或样式，也要同步改 `web/index.html` 里对应的 `?v=`，否则访客最多 4 小时内仍拿到旧文件。
- 切换前确认没有进行中的查询和 8000 端口连接；运行数据和私有配置先备份为 `/var/backups/qier/qier-before-20261003T035908Z-b3b052f.tar.gz`（仅 root 可读），配置备份为 `/etc/qier/backend.env.before-b3b052f-*`，旧链接保留为 `/opt/qier/current.before-b3b052f`。预制示例包沿用 `/var/lib/qier/demo_prebuilt`，`XRAY_QCC_MAX_POINTS` 未改。
- 验证：后端 537、报告页 91、研究室 92 项测试通过；候选版本以服务用户在临时数据目录冒烟，A、B、C 三个示例均由预制包回放，无“没查成”。切换后本机与公网健康接口均报告新版本，首页哈希与构建一致；公网取到的新脚本 `cf-cache-status: MISS`，含“企业五维轮廓”。浏览器在公网新建一份 A 示例报告，雷达为闭合五边形，页面请求均为 200。
- 上传时 SSH 多次被重置，改为逐个上传、校验 SHA-256，并在服务器上用 `setsid nohup` 执行，避免连接中断打断切换。

## 2026-10-03 12:44 合入 PR #12 发布

- 发布提交 `4dd8fa6`（合并 fanmeilinn 的 PR #12），服务器版本 `/opt/qier/releases/20261003T044254Z-4dd8fa6`。合并时只有 `web/index.html` 的版本号冲突：PR 改过的三个样式表和 `case-design.js` 统一换成 `?v=pr12-halo-20261003`，`research-progress.js`、`app.js` 沿用主分支版本号；五维雷达保留。首页按本次提交重新构建；后端代码与依赖未变。
- 运行数据与私有配置先备份为 `/var/backups/qier/qier-before-20261003T044254Z-4dd8fa6.tar.gz`，旧链接保留为 `/opt/qier/current.before-4dd8fa6`，配置备份为 `/etc/qier/backend.env.before-4dd8fa6-*`。
- 验证：后端 537、报告页 91、研究室 98 项测试与类型检查通过；候选版本冒烟时 A、B、C 示例均由预制包回放、无“没查成”。切换后公网健康接口报告新版本，首页哈希一致，新样式与脚本 `cf-cache-status: MISS` 且含新代码；浏览器打开公网报告为五维雷达，无失败请求。
- 同时清理分支：本地只保留 `main`，远端只有 `main`（PR #12 的分支合并后已删除）。删除工作区前，工作区独有的报告、运行记录、缓存与路演文件已复制到开发机被忽略的 `.tmp/worktree-archive/`；Codex 未提交的代码保存为本地标签 `archive/codex-office-live-research-wip`。Codex 工作区里的 `node_modules` 等是指向主项目和 `D:/codex-artifacts` 的目录联接，删除前已先单独移除联接，目标未受影响。

## 2026-10-03 13:26 资料库发布

- 发布提交 `7ac82b1`，服务器版本 `/opt/qier/releases/20261003T052451Z-7ac82b1`，`XRAY_RELEASE_ID` 同名。以上一版本为底，只覆盖 `web/` 和 `research-room/app/page.tsx`；首页按本次提交重新构建（`index-5NGHxHZL.js`）。后端代码与依赖未变。
- 新功能：名词弹窗可以「收藏复习」，新分区「资料库」（`#/library`）。收藏只存在浏览器的 localStorage 里（`xray.library`），不经过服务器，不跨设备。设计见 [资料库设计](2026-10-03-library-design.md)。
- 同时修复：新配色下名词弹窗里"对你意味着什么"那段字几乎看不见；窄屏（420px 以下）的四个分区和状态徽标挤在一起。
- 版本号：`app.js`、`style.css`、`case-palette.css`、`report-workspace.css` 改为 `?v=library-20261003`。
- 运行数据与私有配置先备份为 `/var/backups/qier/qier-before-20261003T052451Z-7ac82b1.tar.gz`；旧链接保留为 `/opt/qier/current.before-7ac82b1`，配置备份为 `/etc/qier/backend.env.before-7ac82b1-*`。
- 验证：报告页 100 项、研究室 98 项测试通过；候选版本冒烟时，A、B、C 三个示例都由预制包回放，没有"没查成"。切换后公网健康接口报告新版本，首页哈希一致；公网新脚本 `cf-cache-status: MISS`，内容是新代码。在公网浏览器里实际操作了一遍：「我的」页面词表收藏 → 资料库显示 → 移出 → 空状态，首页菜单有「资料库」。测完已清掉测试收藏，没有在生产环境新建案卷。
