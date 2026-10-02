# 文档索引

冲突时以代码和 [黑客松版 PRD](2026-10-02-xray-hackathon-prd.md) 为准。

## 现行：照着做

| 文档 | 给谁 | 内容 |
|---|---|---|
| [黑客松版 PRD（H2）](2026-10-02-xray-hackathon-prd.md) | 全员 | 主线、判断原则、功能范围和取舍；开头有当前进展 |
| [三分钟演示操作单](demo-runbook.md) | 上台演示的人 | 演示前准备、讲稿和点击顺序、断网预案、排练检查表 |
| [证据采集清单](evidence-collection.md) | 去官方网站查证的队友 | 案例 A、B 上台前要截图核实的记录，以及怎么存进证据包 |
| [backend/README.md](../backend/README.md) | 开发 | 运行、配置项、接口、数据来源、规则约定 |
| [qier.asia 部署与维护](deployment.md) | 部署与演示负责人 | 服务器、HTTPS、免登录访问、数据目录、维护操作与上线验收 |
| [桌面生成提示与卷宗动效](2026-10-03-scene-feedback.md) | 前端与部署负责人 | 已确认动效、保存状态边界、回归验收及本次发布交接 |
| [前端交接](frontend.md) | 改 `web/` 的人 | 页面结构、界面上要守的规则、自测清单 |
| [等待动画的进度事件](progress-events.md) | 做等待动画的人 | `/api/cases/stream` 的事件格式；和 `app/progress.py` 一一对应，改格式先改代码 |
| [Tokendance 网关](tokendance.md) | 接模型的人 | 网关能力实测、长思考超时的修法、探针命令 |
| [后端 B 接入说明](backend-b-integration.md) | 改模型、材料读取、小企的人 | 版本化引用格式、引用校验、缓存与回放；其中测试数字和 PR 记录是当时快照 |
| [用户评价设计](superpowers/specs/2026-10-02-user-reviews-design.md) | 改评价功能的人 | 评价为什么只能让人多留意、不能让人放心 |
| [判断更新契约](2026-10-02-judgment-update-contract.md) | 改判断追踪的人 | 判断的数据结构和 `/resolve` 接口；界面上先藏起来了，见文首说明 |

## 记录：某个时刻的结果，不再更新

| 文档 | 内容 |
|---|---|
| [浏览器验收记录](2026-10-02-browser-acceptance.md) | 10-02 15:25 企鹅做的本机完整浏览器验收。之后接了企查查、评价、进度事件，数字以重新跑的为准 |
| [sample-case.json](sample-case.json) | 早期的案卷样例，用来看返回长什么样；后来加的字段（`glance`、`terms`、`charts`、`judgments` 等）不在里面，字段以 `backend/app/models.py` 为准 |

## 历史：比赛前的方案，不要照着做

这几份在磁盘上设成了只读，留着只为看当初的原则。里面的 Postgres、Celery、登录、SSE、六类成果、36 项检查等，黑客松版全部砍掉了，对照表见 [H2 第 13 节](2026-10-02-xray-hackathon-prd.md#13-砍掉了什么和旧-prd-对照)。

| 文档 | 内容 |
|---|---|
| [完整版 PRD](2026-10-02-xray-prd.md) | 比赛前写的完整产品方案 |
| [后端 A 交接](backend-a.md)、[后端 B 交接](backend-b.md) | 按完整版 PRD 写的分工，目录结构（`apps/server/…`）和现在的仓库对不上；其中 `/api/v1` 是旧方案，当前接口统一为 `/api/` |
| [企鹅后端 B 实施计划](superpowers/plans/2026-10-02-penguin-backend-b.md) | 企鹅动手前的计划；实际做成什么样以后端 B 接入说明为准 |

把文档喂给自己的 Agent 时，只给"现行"那一栏的。
