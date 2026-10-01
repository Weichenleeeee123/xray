# X-Ray 后端 A 执行交接

- 角色：业务、证据、任务运行与部署后端。
- 主文档：[X-Ray PRD](../superpowers/specs/2026-10-02-xray-prd.md)。冲突时以 PRD 为准。
- 技术方案：FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL/pgvector、Celery、Redis、私有 OSS、Caddy、Docker Compose。
- 主改目录：`apps/server/app/{api,contracts,domain,db,worker}/`、`infra/`。负责公共契约与迁移合并，不替 B 另造分析引擎。

## 1 交给后端 A 开发 Agent 的开工提示词

> 你负责 X-Ray 业务与证据后端以及公网部署。先完整阅读 PRD 第 4、8、10—14、16—20 章和本交接文档，检查仓库状态，保留其他成员改动。与 B 共用一个 Python 代码库、数据库和账户体系；你维护 /api/v1、Pydantic/OpenAPI、数据模型、鉴权、证据存储、Run/SSE、版本原子发布与部署。B 通过授权服务访问资料并返回 CandidateAnalysis，不直接更新当前 assessment。按 A-01 至 A-11 开发完整功能。H3 前给 F/B 契约和匿名样例，H10 前共同跑通公网真实链路。模型统一由 B 的比赛 Tokendance Provider 接入。不要硬编码秘密、建立虚假成功接口或略过权限/输入版本校验。先确认实际部署与存储配置；无配置时如实记录，继续可并行的本地工作。

## 2 前三个小时的输出

1. 记录部署域名/地域、HTTPS、OSS、数据库、Redis、邮件资源的实际状态；密钥留在后端秘密配置。
2. 启动 API 健康检查与基础运行环境，向 F 提供同源访问方式，公网健康页在 H3 前可用。
3. 与 B 确认 case、context、evidence、claim、assessment、artifact、run 的 Pydantic Schema。
4. 输出统一错误信封、分页、UUID/时间/Decimal、枚举、Idempotency-Key 和 revision 规则。
5. 发布 OpenAPI 与至少以下匿名样例：创建 case、实体候选、带引用 assessment、六类 artifact、diff、SSE、错误。
6. 向 B 提供 CaseService/EvidenceService/RunService 的方法签名及可用于测试的适配实现；样例不得当作正式分析。

## 3 服务职责

| 服务 | 你负责的能力 | 不应交给模型决定的事项 |
| --- | --- | --- |
| AccountService | 账户、会话、邮箱、找回、权限 | 用户身份、会话有效期、跨账号授权 |
| CaseService | 生命周期、上下文版本、主体/方案、画像授权 | owner_id、输入 revision、历史授权范围 |
| EvidenceService | 上传、原文、版本、引用、访问、撤回和清理 | 文件所有权、哈希、来源 ID、可见性 |
| RunService | outbox、队列、状态、取消重试、事件恢复 | 幂等、终态、重试上限、并发预算 |
| PublicationService | 校验 B 的候选结果、事务发布、更新 head | 版本竞争、引用存在性、唯一发布 |
| ArtifactService | 保存、依赖、失效状态、导出 | 私有访问、依据版本、派生内容清理 |
| WatchService | 已授权关注、刷新调度、去重通知 | 是否允许定时执行、通知收件人 |

你可以调用 B 提供的语义校验，但必须自己执行外键、所有权、状态、数值计算记录和输入版本等确定性校验。

## 4 必须固定的契约

- 业务对象叫 case，执行对象叫 run，用户核验待办叫 action_item。
- 接口全部在 `/api/v1`，字段和枚举遵从 PRD 第 4、11—13 章。
- 成功 `{data, request_id, page?}`；失败 `{error:{code,message,retryable,details}, request_id}`。
- 请求不接受客户端指定 owner_id；所有服务通过 session 获取用户。
- exact 数字使用 Decimal，API 金额/精确数值用字符串；未知为 null 并保留原因。
- 发布版不可静默覆盖；更正追加版本，隐私删除另走清理程序。
- 写操作有必要的幂等键和基准版本；同键不同 payload 返回冲突，不重复计费/发布。
- SSE 持久化 seq，以 Last-Event-ID/after_seq 恢复；终态不可被迟到事件逆转。

## 5 数据与运行的关键实现顺序

### 5.1 基础库

先建 users/sessions/cases/case_context_versions/entities/case_entities/runs/run_events/outbox。随后扩展 documents/document_versions/evidence/observations，再到 assessments/claims/claim_versions/dependencies/artifacts/actions。

PRD 第 11 章给出完整表集合。此顺序只用于迁移组织，不表示可以忽略其他表和功能。公共迁移由你串行管理；B 提交字段需求和样例，不各自生成冲突迁移。

### 5.2 证据入口

H8—H10 优先打通真实网页证据登记和首轮结果发布需要的最小持久化方法，让 B-04/F-03 不等待整个文件系统做完；H12 前补齐私有文件上传、授权访问与文档版本处理。

上传流程：申请上传 → 校验完成 → 建立不可覆盖版本 → 投递解析 → B 登记定位证据 → 更新文档处理状态。鉴权、MIME/大小/页数、哈希与解析状态分开；文档 availability 与 processing_status 不混用。

### 5.3 分析与发布

1. 创建 run 和 outbox 同事务提交，固定授权上下文与输入基准。
2. worker 调用 B，分析期间事件持久化，不依赖浏览器连接。
3. run 自己采集的来源进入本轮 staging；按照 PRD 采集屏障规则形成冻结快照，不为每个网页触发无限过期。
4. 接收 CandidateAnalysis，检查引用、用户范围、Schema、数字和依赖。
5. 校验输入基准、active_attempt、最新 snapshot 和 run 状态；同事务激活有效 staging，必要时增加 input_revision，再创建 assessment/changes、更新 head、处理成果新版本或过期状态。
6. 事务成功后通过 outbox 发 assessment.published；同一 run 最多发布一次。
7. 若外部输入已变更，旧 run 进入 superseded，安排有上限的最新输入复核；不覆盖新结果。通过 adopt_staging 重新授权并承接旧 run 的有效来源，保留沿袭、去重、重新冻结；不把旧候选直接当新结果。

首轮发布同样使用 PublicationService。早期可以先实现无历史差异的分支，后续扩展差异和传播；不能先由 B 直接写 head 再期待未来重构消除竞态。

### 5.4 删除和历史

撤回表示不用于当前分析，不等于清空文件。彻底删除先使资料不可访问、取消/隔离受影响运行，再清理文件、OCR、切片、向量、引用原文、回答、成果和导出缓存等派生内容。允许保留不含敏感内容的删除占位和审计记录。

删除后的历史不得通过旧版本、消息、下载链接或备份恢复重新暴露内容。备份策略和恢复删除清单按 PRD 第 8、16 章执行。

## 6 工作包

| ID | 时间 | 工作 | 核心完成证据 |
| --- | --- | --- | --- |
| A-01 | H0—H1 | 资源核验与健康服务 | 公网健康地址、配置状态；不得虚报资源已开通 |
| A-02 | H1—H3 | 共享契约、基础迁移、错误与幂等 | OpenAPI、样例、可运行迁移 |
| A-03 | H3—H6 | 账户、case/context、主体/候选 | 双账号隔离与登录恢复测试 |
| A-04 | H6—H8 | Run、outbox、Celery、事件、SSE | 重复投递和断线恢复测试 |
| A-05 | H8—H12 | 证据登记、首轮发布基础、文件与版本 | H10 首轮闭环；H12 文件私有访问通过 |
| A-06 | H12—H17 | 画像、复用、消息、输入 revision、基础成果/待办保存 | 授权范围生效，改输入可检测；H18 前成果真写回 |
| A-07 | H17—H23 | 依赖、差异与发布事务完善 | 并发运行不覆盖，部分失败不污染旧版 |
| A-08 | H23—H28 | 成果/待办、历史、失效联动 | 发布后所有成果都有正确依据状态 |
| A-09 | H28—H35 | 导出、关注、提醒、重试、撤回删除 | 私密内容清理和通知去重测试 |
| A-10 | H35—H41 | 限流、审计、脱敏、备份恢复 | 权限/安全/故障 AC 有证据 |
| A-11 | H41—H46 | 固定部署与恢复包 | 重启恢复演练和配置交接 |

表中公共服务须渐进交付，不要等整个 A-07 做完才允许首次发布结果。所有功能最终仍须满足 PRD 的一致性要求。

## 7 你的专项验收

- 所有 ID 型接口、文件访问、导出、SSE 都做 owner 检查，猜中 UUID 也不能越权。
- Argon2 密码哈希；随机会话 token 服务端存 hash；安全 Cookie 和 CSRF/Origin 检查。
- 登录/找回错误不泄露账户存在性，邮件 token 单次有效，退出撤销 session。
- 同一上传/启动请求重放不产生重复材料、run 或 assessment。
- Celery 重复消费、进程重启、Redis 暂时故障可恢复，不丢失数据库中的已排队任务。
- 两次并发上传、上传与改目标并发、取消与发布并发都有确定处理。
- SSE 断线后补齐事件不重复消息，终态不倒退。
- 撤回后不再作为当前依据；删除后所有读取路径立即失效，派生清理可查询结果。
- SSRF 防护在实际请求与重定向各跳生效；不允许访问内网、localhost、metadata 地址。
- 日志无 Key、密码、会话、完整私有材料或长期签名 URL。
- 数据库/Redis 不开公网；学校 Wi-Fi 和蜂窝访问均验证登录、上传和 SSE。

## 8 给其他成员的每次交接

提供：任务 ID、改动目录、契约版本、完整端点或内部方法、请求响应样例、生成类型命令、测试命令与结果、已知问题、配置说明。不要把密钥或演示用户密码写入 Git。

正式验收以 PRD 第 18 章 AC-01—AC-58 为准。本文件是待执行清单，不是已经部署或测试通过的报告。
