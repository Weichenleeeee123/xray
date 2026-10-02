# Progressive Images Implementation Plan

**Goal:** 首页先显示轻量图，再恢复原图画质，并发布、提交、推送。

**Architecture:** 独立串行升级函数负责解码成功后通知 UI；React hook 在页面 load 后的空闲时间开始升级。CSS 变量和 img src 共用一份图片状态。

**Tech Stack:** React 19、TypeScript、WebP、Vite、Node test、Playwright CLI。

- [x] 新建 `research-room/tests/progressive-images.test.mjs`，验证解码完成前不会切换或开始下一张、失败继续、取消停止。运行 `node --experimental-strip-types --test research-room/tests/progressive-images.test.mjs` 观察缺失实现失败。
- [x] 将已保存的无损 WebP 复制到 `research-room/public/*.lossless.webp`，用 Pillow 比较 `convert('RGBA').tobytes()` 与原 PNG 一致，记录哈希用于 URL。
- [x] 新建 `app/progressive-images.ts`：`upgradeImages(assets, decode, apply, signal)` 串行 await 解码，失败跳过，取消停止；导出图片清单。
- [x] 新建 `app/use-progressive-images.ts`：监听页面 load，空闲后启动；通过 `new Image()`、`fetchPriority='low'`、`decode()` 加载，每张超时 45 秒，卸载清理监听和请求。
- [x] 修改 `page.tsx`、`globals.css`、`report-dossier.tsx`，以同一 ready 状态驱动背景 src、拼接图层 CSS 变量和卷宗 src，保留 HTML 轻量预加载。
- [x] 执行 `npm --prefix research-room test` 与 `npm --prefix research-room run build:home`；用 Playwright CLI 检查实际加载顺序、成功切换、失败回退和布局。
- [x] 更新部署文档，备份线上入口，上传新图片及最新构建资源，最后替换入口；检查 HTTPS 和浏览器，不重启后端。
- [x] `git diff --check`，核对差异与不含密钥的暂存清单，提交、推送并核验远端提交。

验证结果：40 项 Node 测试、4 项后端测试、TypeScript 和构建通过；浏览器验证预览/高清成功路径及失败回退；最终线上确认首屏绘制先于高清请求。发布不重启后端，所有旧文件保留。
