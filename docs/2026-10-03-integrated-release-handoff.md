# 企鹅整合发布交接：报告修复、统一案卷、小企私有记忆

基线：`origin/main` 的 `8568c39`（含队友新资料库）。整合分支：`codex/penguin-integration-release`。
本次按用户要求推送并通过 PR 合并；公网部署仍由队友执行，不在本轮自动发布。

## 内容与冲突处理

1. 保留主线资料库、五维雷达、报告布局、研究室动画和阶段超时修复。
2. 报告目录保留边缘光晕，浅色按钮文字始终为深色；悬停、键盘焦点、按下均不使用整体增亮。
3. 雷达标注简化为“定性示意”，不改变数据、规则或解释边界。
4. 正式 `#/cases` 使用报告的深蓝顶栏、左导航、暖纸内容区及可收起小企；展示真实私有列表，保留加载、空状态、错误重试与导航竞态保护。用户指定的标题下浏览器标识已移除，隐私隔离未改变。
5. 合并小企版本化私有记忆、概览/主题卡/原文索引、按需取证与完整材料回退。不会训练模型，不会把材料公开，也不改 Tokendance / Qwen3.8-Max 和长思考默认关闭设置。
6. `assistant.py` 的重叠合并保留主线 `_context_json` 无损去重：在 `full`、`shadow` 和全量回退路径仍去除重复序列化，不删原文。系统提示、结构化 Schema、修复预留和实际请求仍受预算控制。
7. 前端同时保留“部分表述未获依据支持，已省略”和“按需核对相关材料”，只展示单一原文出处入口；处理失败不冒充企业风险结论。内部拦截明细不重新暴露。
8. 静态资源版本号已更新，保留资料库样式和图标，避免新脚本配上旧缓存。

## 部署：新模式不会仅靠合并自动启用

为了兼容旧环境，代码默认 `XRAY_CASE_MEMORY_ENABLED=0`、`XRAY_ASSISTANT_CONTEXT_MODE=full`。
要启用按需取证，在现有后端服务配置中设置（保留已有密钥、模型、签名身份与其他数据路径）：

```dotenv
XRAY_CASE_MEMORY_ENABLED=1
XRAY_ASSISTANT_CONTEXT_MODE=selective
XRAY_CASE_MEMORY_DIR=/var/lib/qier/case_memory
XRAY_ASSISTANT_CONTEXT_CHARS=120000
XRAY_ASSISTANT_EVIDENCE_CHARS=70000
```

记忆路径是生产示例：按实际服务账号设置权限并持久化，不能放入静态资源/CDN 目录。字符预算不是网关 token 容量声明。切勿覆盖或重建现有 `XRAY_PRIVATE_DIR` 身份签名文件，否则旧访客可能失去对原案卷的访问。

部署流程仍按 `docs/deployment.md`：获取实际合并提交、安装锁定依赖、构建首页、重启后端并记录 `XRAY_RELEASE_ID`。检查 `/api/health` 的 `assistant_context` 与发布版本，再用两个独立浏览器测试私有案卷、问答、出处及补材料。

回退：改为 `XRAY_ASSISTANT_CONTEXT_MODE=full` 并重启；如不再构建记忆，再设 `XRAY_CASE_MEMORY_ENABLED=0`。不用删除记忆、原案卷或历史报告。

## 验收

最终整合结果：**575 项后端、206 项前端/研究室测试通过**；TypeScript 类型检查、首页生产构建、差异空白检查通过。针对本次 32 个变更文件检查，未发现凭据字面量或应排除的私有运行数据。

- 后端全量：`python -m pytest -q`（backend 下）。
- 前端及研究室：`node --experimental-strip-types --test web/tests/*.test.cjs research-room/tests/*.test.mjs`。
- TypeScript：`node research-room/node_modules/typescript/bin/tsc --noEmit -p research-room/tsconfig.json`。
- 首页生产构建：research-room 下 `node node_modules/vite/bin/vite.js build --config vite.home.config.ts`。
- 重新验证无损打包与记忆 full/shadow 共存、前端两个披露状态共存、离开案卷进入新资料库时布局正确清理。
- 本机 Edge 使用隔离临时目录和两个访客身份、模型关闭模式：真实接口列表、报告/案卷/资料库/使用说明切换、空状态、模拟读取失败后重试；1440/1600/1920 宽度与助手收起均通过。
- 小企联调：安慰问题没有伪造出处；退款回答保留不退与费用条件；出处打开原文；停止等待、刷新、恢复仅一次 POST；补材料形成第 2 版，旧引用仍打开第 1 版；另一访客列表为空、直链 404；浏览器零脚本异常。

首次全量测试中首页缺少构建产物造成两项失败，完成构建后重跑通过，未跳过测试。保留既有 Starlette 客户端弃用警告和 Vite `/research-assets/` 运行时解析提示。浏览器联调没有调用付费调查或真实模型；先前的真实模型少量对照数据及限制见 `2026-10-03-case-memory-handoff.md`，不作为本轮重新测量或公网验收。

本轮不提交真实案卷、运行日志、模型缓存、访客身份、API 密钥、浏览器凭据或本地验收数据。`design-previews/` 是明确标注的布局示例，不是正式业务路由。
