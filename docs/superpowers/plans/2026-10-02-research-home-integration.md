# 研究室正式首页接入计划

**目标：** 按用户已确认的方向，用队友完成的研究室替换旧首页，接真实后台任务，以真实阶段驱动鹅的移动，保留案卷、报告及问答。

**架构：** 直接复用研究室 React 页面，增加独立 Vite 静态构建入口。FastAPI 根路径提供此构建，`/xray/` 提供原业务页面，图片统一 `/research-assets/`。生产使用同源接口，不依赖开发代理或另一个前端常驻进程。

**约束：** 不删除任何文件；构建 `emptyOutDir: false`；保留工作区已有后端修复；不提交其他人的改动。沿用既有视觉与动画，不重新设计场景。

## 执行顺序

- [x] 首页挂载回归：GET `/` 是研究室，GET `/xray/` 是报告壳，图片与构建脚本可访问，源代码不被公开。
- [x] 任务与动画回归：无真实阶段不出发；查询未结束不前进；未查跳过、失败不伪造成功；处理阶段留在桌前，保存确认后才开放报告；断线只恢复已有任务。
- [x] 静态入口：添加 `research-room/home/index.html`、`main.tsx`、`vite.home.config.ts`；输出到 `research-room/home-dist`，不清空已有文件。
- [x] 后端挂载：根路径返回构建首页，`/office/` 提供构建文件，`/xray/` 保留业务页；兼容旧 hash 报告链接。
- [x] 页面连通：首页增加案卷与说明入口；报告同标签打开；主站“查企”与品牌返回新首页；统一图片路径；保持旧表单可在明确的材料入口使用。
- [x] 任务接入：继续使用 `/api/runs`、`/api/runs/{id}` 和 `/api/cases/{id}`；传递取消信号、保存 run 编号；可重连、不自动重发创建；后端阶段决定动作。
- [x] 验收：执行 Node 回归、后端挂载及进度测试、TypeScript 检查和静态构建；在隔离数据目录启动后端，用虚构案例走真实 HTTP 创建 → 进度 → 报告 → 刷新恢复 → 案卷往返。
- [x] 文档：更新启动和页面结构说明，说明构建一次后只需启动后端，明确动画阶段映射。

## 取舍

保留独立 Vinext 预览供队友继续开发，但正式入口不依赖它；避免将 FastAPI 首页重定向到仅本机可用的 3000 端口。报告继续使用已有成熟实现，避免这次接入扩大成报告重写。

## 验证命令

```powershell
node --experimental-strip-types --test research-room/tests/*.test.mjs web/tests/*.test.cjs
cd research-room
node node_modules/vite/bin/vite.js build --config vite.home.config.ts
node node_modules/typescript/bin/tsc --noEmit --incremental false
cd ../backend
.venv/Scripts/python -m pytest tests/test_home_integration.py tests/test_research_assets.py tests/test_runs.py tests/test_progress.py -q --basetemp=../.tmp/home-integration-tests-<唯一编号>
```

测试临时目录每轮使用新编号，不覆盖或清理旧目录。通过真实 API 验收使用隔离 cases/reviews/cache/runs 目录及关闭外部收费服务的进程环境，不更改后端 `.env`。
