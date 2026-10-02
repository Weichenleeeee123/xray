# 后端全面排查与提升路线

审计日期：2026-10-02。代码基线：`9496ea5`。对象：企er / X-Ray 当前 FastAPI 后端及两套前端的后端接入契约。

**结论：主业务链路和测试基础已经具备，但“报告可信、版本不丢、数据持续更新”这三个核心承诺仍存在可复现缺口。应先修复正确性与数据完整性，再推进多人使用和功能扩展。**

本次仅做审计、隔离验证和报告，没有修改业务代码、真实案卷或密钥配置，没有删除文件。下面的模拟输入与供应商响应全部用于本地验证，不能理解为针对真实企业的事实。

## 1. 范围、证据和边界

| 项目 | 结果 |
|---|---|
| 后端规模 | `app/` 39 个 Python 模块，7,467 行；25 个 API 路由，另有静态页面挂载及根路径兜底 |
| 测试规模 | 32 个后端测试模块；319 项后端测试通过 |
| 关联前端验证 | `web` 27 项通过；`research-room` 13 项通过 |
| 依赖一致性 | `pip check` 通过；Python 实际为 3.13；FastAPI 0.142.2、Pydantic 2.13.5、Starlette 1.7.0、HTTPX 0.28.1 |
| 定向实验 | 24 组隔离探针，包括存储交错写入、状态机、规则语义、假供应商响应、假模型输出、缓存及事件循环实验；不是24项正式回归测试 |
| 当前默认案卷目录 | 20 份现存案卷均通过当前 Case Schema 校验；没有发现已经存在的 `recheck` 格式损坏 |
| 当前默认运行时数据 | 案卷约 1.60 MB；缓存 88 个文件约 0.67 MB；只统计，不展示用户内容 |
| 数据名单日期 | 银行、保险名单截至 2025-06-30；期货截至 2026-08；支付和私募截至 2026-10-02。这是本地元数据日期，未核验上游是否已有新版 |

检查覆盖 API、需求识别、文档读取、名单索引、工商/财务/新闻适配器、模型与缓存、规则抽取和判定、信号/图表/报告、版本差异、人工判断、聊天、评价、后台任务、存储、配置和测试/部署文件。

没有调用真实计费接口，没有进行生产压测、真实供应商在线验收、漏洞库扫描或法规有效性复核。关于网络供应商的边界结论由代码与模拟响应支持，不能据此断言供应商已经实际返回过这些异常。当前仓库明确定位为单进程演示；无账号和简化部署原本就是取舍，上线需求单独列出。

测试运行器关闭外网，并保留测试文件以遵守“不删除文件”的要求；它不适合验证文件清理逻辑。首次网络拦截误拦了 Windows asyncio 的本机 socketpair，修正为允许回环后，最终 319 项全部通过。仅有 Starlette 对 HTTPX TestClient 的弃用提醒，不是用例失败。

证据：

- [基线测试输出](<D:/company research/.tmp/backend-audit-20261002/baseline.txt>)、[JUnit XML](<D:/company research/.tmp/backend-audit-20261002/baseline.xml>)。
- [定向复现脚本](<D:/company research/.tmp/backend-audit-20261002/probes.py>)、[结构化复现结果](<D:/company research/.tmp/backend-audit-20261002/probe-results.json>)。
- [范围及存量 Schema 检查](<D:/company research/.tmp/backend-audit-20261002/inventory.json>)。
- [Web 测试](<D:/company research/.tmp/backend-audit-20261002/web-tests.txt>)、[研究室测试](<D:/company research/.tmp/backend-audit-20261002/research-tests.txt>)。

## 2. 现有设计值得保留的部分

- 规则判定与模型解释分层；业务逻辑已经从路由中拆到 analysis、sources、assistant 等模块。
- `Coverage` 分开表达查到、查无、未查、失败，`CompanyProfile.checked` 尝试避免把缺失字段当作零记录。这是正确的基础，需要让适配器和差异逻辑贯彻到底。
- RawRecord、版本化引用、逐字引文校验、历史版本聊天、材料与用户评价的来源区分已有实现。
- 模型输出 Schema 校验、有限次数修复、回放和规则模板兜底都已建立。
- 文档读取不是仅凭后缀：图片验证、像素限制、PDF 页数限制、DOCX XML 大小及压缩比检查已经存在。
- 319 项测试覆盖了正常流程及不少模型输出异常；改进应在此基础上补业务不变量和持久化回读测试。

## 3. 首轮必须解决的正确性问题

P1 表示会造成案卷不可用、已成功数据丢失或关键事实/判定错误，建议下一个修复批次完成；P2 表示重要的可靠性、溯源或扩展问题。它们是本次审计优先级，不沿用黑客松 PRD 的 P0/P1 含义。

### A01 · P1 · “重新核实”成功后，案卷无法再次读取

**已复现，真实 API 路径。** `POST /resolve` 传 `action=recheck` 返回 200；随后 `GET /cases/{id}` 返回 500，列表也不再显示该案卷。

根因：`ResolveIn` 接受 `recheck`，`resolve()` 直接赋给 `Judgment.state`，但持久化模型的 state 枚举只允许 `needs_check` 等值，不允许 `recheck`。赋值时未校验，保存时序列化成功；重新从 JSON 校验时失败。列表捕获 ValueError 并跳过，所以表现得像“消失”，文件实际还在。

位置：[models.py:397](<D:/company research/backend/app/models.py:397>)、[pipeline.py:257](<D:/company research/backend/app/analysis/pipeline.py:257>)、[store.py:24](<D:/company research/backend/app/store.py:24>)。现有 `test_recheck_keeps_the_open_questions` 只检查响应，未重新读取。

建议：明确区分操作 `recheck` 和持久化状态 `needs_check`；保存前重新验证完整对象。对关键状态启用赋值验证或使用显式状态转换函数。已有坏文件如将来出现，应先复制备份，再迁移修复，不能删除或静默忽略。

验收：三个 resolve 动作都经过“提交→独立读取→重启后读取→继续补充”完整链路；非法状态不能落盘。

### A02 · P1 · 聊天会覆盖刚生成的新版本和材料

**已复现，真实 API 的确定性交错。** 聊天先读取 v1，等待回答；另一个请求补充材料并成功保存 v2；聊天回答完成后，把它先前读到的整份 v1 保存回去。两次都是 200，最终 current=1，新材料不存在。

根因：所有修改都采用“读整个 Case→修改→覆盖整个 Case”，没有 revision 检查、事务或覆盖整个读改写过程的锁。原子文件替换只能避免半份 JSON，不能防止丢更新；固定 `.tmp` 文件名还会使同时保存互相干扰。评价存储有同类读改写结构。

位置：[main.py:290](<D:/company research/backend/app/main.py:290>)、[main.py:123](<D:/company research/backend/app/main.py:123>)、[store.py:17](<D:/company research/backend/app/store.py:17>)、[reviews.py:78](<D:/company research/backend/app/reviews.py:78>)。

建议：立即给每个 Case 加 revision / expected_revision；聊天追加独立消息，不覆盖报告。短期单进程锁必须覆盖读取和提交，不能只锁 save；模型或网络请求期间避免长时间占用写锁。持久化层采用短事务与乐观并发，冲突返回 409 或重新合并。

验收：chat+supplement、supplement+supplement、resolve+supplement、评价并发各自验证；所有成功操作均保留，版本号不回退。

### A03 · P1 · 否定和禁止语句被当作正向宣称

**已复现，真实建案卷 API。**

| 材料原句 | 当前结果 |
|---|---|
| 招聘入职不收取任何押金或培训费 | A9：不合规承诺，解释为要求先交费 |
| 禁止转账到个人账户 | A7：收款信息与公司不符 |
| 不承诺零风险 | A2：不合规承诺 |
| 不能随时退款，合同以约定为准 | A8：声称“随时退”但无法核验 |

根因：多数抽取只判断关键词存在；否定处理只覆盖部分收益词，且按前四个字粗略判别。最终规则是确定性的，并不代表前置语义提取正确。

位置：[extract.py:49](<D:/company research/backend/app/analysis/extract.py:49>)、[extract.py:104](<D:/company research/backend/app/analysis/extract.py:104>)。

建议：抽取结构至少包含主体、动作、否定/禁止、条件、时间范围和原文定位。先补有限领域的否定规则和反例语料；若用模型抽取，仍需原文对齐并允许“无法确定”，不能直接让模型决定判定。

验收：正反成对测试、引用他人说法、风险教育文案、条件句、历史与当前说法、跨行 OCR；正向句与其否定句不得得到同一指控。

### A04 · P1 · 差异清单把失去数据说成风险减轻

**已复现，差异函数。** “行政处罚有1条”变为“查询失败”，输出 `clarified` 和“比上一版轻了”；1条变10条，仍输出 `unchanged` 和“没变”。

根因：diff 主要比较严重程度的数字排序；`none` 比 `bad` 小，所以查询失败被算作改善；同等级即使事实值发生变化也被判为没变。`need` 触发还直接写“事实没变”，但实际会重查外部来源。

位置：[diff.py:12](<D:/company research/backend/app/analysis/diff.py:12>)、[diff.py:43](<D:/company research/backend/app/analysis/diff.py:43>)、[pipeline.py:210](<D:/company research/backend/app/analysis/pipeline.py:210>)。

建议：分别比较证据覆盖状态、事实值、规则结论和展示文本。新增“数据暂不可用/过期”“事实更新”“查看范围变化”等变化类型；证据丢失时保留上次记录并标明时效，不能推导为澄清。变化原因应指向真正变动的数据源，不能一律归因于新材料。

验收：任何 found→failed/not_covered 都不能输出“改善”；同等级的数量、主体、金额、日期变化必须可见。

### A05 · P1 · 引用校验不能阻止模型反转事实

**已复现，假模型输出经过真实 answer 流程。** 案卷登记状态为“存续”，模型回答“这家公司已经停止营业”，引用真实存在的登记记录 R5，没有伪造数字。系统以 `mode=model` 返回，`dropped=0`。另外 `_short_ok('已登记', '未登记', ...)` 返回 True，说明首屏短句可以反转否定。

现有校验保证引用存在、部分数字和判定词一致、引文逐字对应；它并未证明解释语句被证据支持。代码注释已承认一般语义蕴含的限制，但用户可见内容仍需要更窄的事实输出边界。

位置：[assistant.py:206](<D:/company research/backend/app/assistant.py:206>)、[assistant.py:245](<D:/company research/backend/app/assistant.py:245>)、[plain.py:104](<D:/company research/backend/app/plain.py:104>)。

建议：企业状态、牌照、金额、处罚等关键事实由服务端从结构化字段渲染，模型选择 fact_id 并解释，不自由改写事实值；短句保留字段状态及否定极性。对自由解释做额外检查并维持兜底，但不能把再加几个禁词当成完备保证。

验收：存续/注销、已/未、可以/禁止、有/无、部分/全部、历史/当前的对抗输出都不能错误放行；引用真实但结论错误也必须被拦下。

### A06 · P1 · 商业数据的附属查询没有统一主体校验

**已复现，模拟供应商响应。** 工商主查询返回目标公司；风险扫描明确返回另一家公司并含失信条目，最终目标公司仍被标记 `dishonest=True`。

根因：工商主查询检查名称，财务层也有局部名称核对；风险扫描、明细、股东、分支、上市和新闻没有同等的统一约束。

位置：[qcc_agent.py:354](<D:/company research/backend/app/sources/qcc_agent.py:354>)、[qcc_agent.py:379](<D:/company research/backend/app/sources/qcc_agent.py:379>)、[news.py:65](<D:/company research/backend/app/sources/news.py:65>)。

建议：先确立企业实体 ID/统一社会信用代码，对每个来源结果验证主体及角色。供应商返回不匹配时必须降为未采用/失败；结果未提供主体信息时记录其关联依据和可信边界。

验收：主查询正确、任一附属查询主体错误时，错误记录不能影响目标公司任何信号。

### A07 · P1 · 部分明细被当作全量，产生错误的绿色结果

**已复现，模拟响应。** 风险扫描说有100条经营异常，明细只给1条且已移出，系统最终显示“未列入”，状态为 `ok`。

根因：`_details()` 对返回行做 `all(移出日期)` 就撤销 abnormal 标记，没有证明这些行覆盖全部记录。股权出质/动产抵押还可能将扫描总数替换为已返回、已核对的自有记录数，未返回部分不能据此当零。

位置：[qcc_agent.py:444](<D:/company research/backend/app/sources/qcc_agent.py:444>)。

建议：数据契约增加 total、returned_count、has_more、complete、role_verified。只有明确全量或权威当前状态才能下“无/未列入”；部分结果保留“已核对部分，其他未知”。

验收：分页未取完、总数与明细不一致、第一页全为已解除记录，都不能错误输出全量无风险。

### A08 · P1 · 金额解析丢失币种，需求金额也会识别错

**已复现。** `100万美元` 经商业适配器后在财务信号显示 `¥100 万`；需求“付1,200元”识别为200元，“投资1亿元”识别不到，“月薪2万元，先交500元押金”选择了工资金额。

根因：注册资本解析只保留数字和万/亿倍数，CompanyProfile 没有币种；展示默认人民币。需求解析选第一个正则命中，没有金额角色。

位置：[commercial.py:38](<D:/company research/backend/app/sources/commercial.py:38>)、[models.py:95](<D:/company research/backend/app/models.py:95>)、[scenarios/__init__.py:79](<D:/company research/backend/app/scenarios/__init__.py:79>)。

建议：使用带 Decimal、currency、unit、raw_text 的 Money 对象；不同币种不直接比较，转换必须记录汇率日期和来源。需求提取区分投资额、押金、工资、收益，多金额时让用户确认涉及本次交易的金额。

验收：千分位、亿、中文金额、零、币种、区间及多金额输入均有正确结果或明确待确认状态。

### A09 · P1 · 命中银行业名单被误当作拥有信托牌照

**已复现，合成名单记录。** 机构 type 明确为“商业银行”，输入宣称“信托”，`claimed_licenses_check` 输出“信托：有”，状态 `ok`。

根因：银行、信托都映射到同一份名单，验证只看名单是否命中，没有核对名单内机构类型。

位置：[verify.py:104](<D:/company research/backend/app/analysis/verify.py:104>)。

建议：验证“主体→名单→机构类型→授权业务范围→有效期”的匹配关系；机构资格与特定产品、交易资格分别呈现。法规适用范围另需专门复核，本次不代替法律有效性审查。

验收：名单包含多种机构类型时，命中一种不能自动证明拥有其他类型资格。

### A10 · P1 · 9名自然人股东就能使图表构建崩溃

**已复现，图表函数。** `holders_chart` 接收9名自然人股东抛 `IndexError`。固定别名字母表只有 `ABCDEFGH`，按股东下标取值；主流程无隔离，图表失败会中断报告生成。

位置：[charts.py:18](<D:/company research/backend/app/analysis/charts.py:18>)、[charts.py:118](<D:/company research/backend/app/analysis/charts.py:118>)。

建议：用不限长度的序号/别名；展示可聚合小股东，原始完整数据保留。非核心图表失败应有显式降级，不影响核心证据与报告保存。

验收：0、1、8、9、30、100名股东；未知持股比例、超长机构名、比例合计不足/超过100%均处理明确。

### A11 · P1 · 不完整工商响应会穿透适配器并打断整个报告

**已复现，模拟响应。** 返回仅有企业名称时，QCC 仍构造 `CompanyProfile(founded='', reg_capital=0)`；信用信号计算成立时间时抛 ValueError。

根因：缺失数据用空串/零补齐，BASIC 又整体记为查过；日期字符串在下游才真正解析。部分字段不可用时没有独立覆盖状态。

位置：[qcc_agent.py:374](<D:/company research/backend/app/sources/qcc_agent.py:374>)、[signals.py:350](<D:/company research/backend/app/analysis/signals.py:350>)、[fmt.py:20](<D:/company research/backend/app/analysis/fmt.py:20>)。

建议：边界层严格验证，日期使用 date，可缺失字段使用 None；checked 按实际成功解析字段生成。一个来源不完整应让该项 failed/partial，其他来源继续出报告。

验收：缺日期、非法日期、字段改类型、资本空值/非有限值时不崩溃、不伪造零。

## 4. 数据、运行和工程性问题

### B01 · P1 · 商业缓存永久命中，补充分析不会自动更新旧工商/风险

**已复现。** 放入2000年的缓存，客户端在当前查询中直接返回它，真实查询函数调用次数为0。QCC 及旧商业适配器没有 TTL、force_refresh、缓存 schema 版本；“重查”可以一直使用很久以前的结果。

位置：[qcc_agent.py:327](<D:/company research/backend/app/sources/qcc_agent.py:327>)、[commercial.py:147](<D:/company research/backend/app/sources/commercial.py:147>)。

建议：每类来源有独立 freshness policy；保留 fetched_at、source_as_of、expires_at、cache/replay 标记；提供定向刷新与 stale-if-error，既不重复无意义计费，也不把永久缓存当成当前状态。历史版本绑定当时的快照。

验收：过期后成功取新数据；取新失败时显示“旧数据+日期+失败原因”；用户强制刷新不命中过期缓存。

### B02 · P1 · 缓存损坏直接中断查询

**已复现。** QCC 缓存只写入一个 `{`，查询直接抛 JSONDecodeError，未转换为来源失败。写入也是直接 write_text；并发或中断可能留下半写文件。Web、旧商业缓存也存在直接读写路径。

位置：[qcc_agent.py:327](<D:/company research/backend/app/sources/qcc_agent.py:327>)、[web.py:144](<D:/company research/backend/app/sources/web.py:144>)。

建议：带格式版本的缓存验证、唯一临时文件和原子提交；损坏时保留原文件并记录隔离状态，可重新获取或降级。不能让非核心缓存导致整份报告失败。

验收：空文件、半写、旧Schema、缺键、磁盘写入异常都得到明确状态；其余来源仍可完成。

### B03 · P1 · “个人信息不存”的声明没有覆盖商业原始缓存

**已复现，合成个人信息。** QCC `call()` 在调用 `clean()` 之前将原始 payload 写入缓存，法定代表人、联系电话均仍在磁盘。后续案卷脱敏不等于缓存脱敏；旧商业适配器还会将原始记录用于 RawRecord。

位置：[qcc_agent.py:327](<D:/company research/backend/app/sources/qcc_agent.py:327>)、[qcc_agent.py:151](<D:/company research/backend/app/sources/qcc_agent.py:151>)、[commercial.py:94](<D:/company research/backend/app/sources/commercial.py:94>)。

建议：先明确保留政策；一般缓存只存业务必需且已脱敏的字段。若必须保留原始响应，应单独限制访问、明确保留范围并更正文档承诺。测试应检查缓存、日志、RawRecord、导出各层，而非仅检查报告。现有历史文件的处理需由用户决定，不在本次删除或改写。

验收：供应商响应含个人字段时，所有允许持久化的位置符合声明，且输出不含密钥。

### B04 · P1（启用商业源且并发时） · 积分上限可以被突破

**已复现。** 上限设3积分，同时发两个每次3分的查询，两者都成功，累计6分。

根因：费用检查、请求和记账不在同一预算预留机制内。客户端是进程级单例，所以文档中的“本次运行”实际更接近服务进程生命周期，而非单个研究任务。Key 因429等被移出后也无恢复冷却逻辑。

位置：[qcc_agent.py:279](<D:/company research/backend/app/sources/qcc_agent.py:279>)、[qcc_agent.py:314](<D:/company research/backend/app/sources/qcc_agent.py:314>)、[qcc_agent.py:327](<D:/company research/backend/app/sources/qcc_agent.py:327>)。

建议：原子预留预算，分别记录任务、用户/租户、日预算和供应商账单；相同缓存键的并发查询合并；区分鉴权、配额、暂时限流，限流采用冷却和受控重试。模型也记录调用次数和token用量。

验收：并发不能越过预算；取消/失败后的预留释放符合计费语义；统计口径与界面一致。

### B05 · P2 · 非官方网页能进入“政府网站点名”分组

**已复现，模拟搜索返回。** 官方搜索返回一个普通商业域名，结果的 `official=False`，但仍进入 `out.official`，报告显示“政府网站点名”“1份文件提到它，没有处罚或警示”。

根因：分组采用请求类型 `k`，没有在接收结果时强制校验域名。搜索请求里的 include 不能代替后端信任边界。

位置：[web.py:190](<D:/company research/backend/app/sources/web.py:190>)、[signals.py:110](<D:/company research/backend/app/analysis/signals.py:110>)。

建议：规范 URL 解析与主机名白名单；对非官方命中拒收或明确进入普通网页组；来源类型与展示标签一致。

验收：普通域名、仿冒后缀、userinfo、端口、重定向等测试不能被标成官方。

### B06 · P2 · 证据去重丢失新的采集时间与来源位置

**已复现。** 同样的内容在2025和2026两次采集，URL也发生变化，`attach` 返回同一个R1，仅保留2025的时间和旧URL。

根因：去重只比较 source_id、title、coverage、content，忽略采集时间、数据截止日、URL、来源类型等。补充后 `case.sources` 又整体替换，历史 onepager API 和聊天仍可能使用最新来源目录。

位置：[pipeline.py:73](<D:/company research/backend/app/analysis/pipeline.py:73>)、[pipeline.py:217](<D:/company research/backend/app/analysis/pipeline.py:217>)、[main.py:300](<D:/company research/backend/app/main.py:300>)。

建议：分开不可变证据内容与每次采集 observation；版本绑定 observation 和 sources 快照。内容可以按hash去重，但新一次查询确实发生过的时间、来源和状态不能丢。

验收：旧版本显示旧来源，新版本显示新采集；内容未变和根本没重查能够区分。

### B07 · P2 · 人工撤回与报告各个展示面不一致

**已复现。** 撤回 `check.A7` 后 judgment 为 withdrawn，但断言仍为 red/mismatch，tally和保存的onepager与上一版完全一致。代码只给 assertion.plain 加文字前缀，未同步重建所有展示。

这是展示一致性问题，不能用“用户撤回”直接把客观记录变成安全结论。需要区分规则的原判断、人工处置和当前有效提醒。

位置：[pipeline.py:257](<D:/company research/backend/app/analysis/pipeline.py:257>)、[report.py:27](<D:/company research/backend/app/analysis/report.py:27>)、[web/app.js:707](<D:/company research/web/app.js:707>)。

建议：用统一报告投影生成短句、统计、问答上下文、一页纸；规则历史保留，人工处置单独标明人、时间、理由与证据。required note/by不能只靠客户端自报。

验收：同一版本各视图对“仍需处理的提醒”口径一致；历史事实不被擦除；再补材料后处置状态按明确规则延续。

### B08 · P2；多进程前必修 · 后台运行仅能恢复页面，不能可靠恢复执行

**已复现进程状态差异。** 相同任务日志，在拥有 `_active_runs` 的工作进程里是 running；模拟另一个进程的空集合时变成 interrupted。

根因：持久化的是事件日志，运行状态仍放进程内；daemon thread没有任务队列、租约、心跳、断点或服务停止时的排空。线程创建没有上限，重试也没有幂等键。浏览器刷新恢复不等于服务重启恢复。

位置：[main.py:128](<D:/company research/backend/app/main.py:128>)、[main.py:163](<D:/company research/backend/app/main.py:163>)、[main.py:204](<D:/company research/backend/app/main.py:204>)、[runs.py:20](<D:/company research/backend/app/runs.py:20>)。

建议：短期有界执行池、排队/忙碌返回、总超时、幂等键、优雅退出；随后持久化 task/step 状态、owner/lease/heartbeat、重试与取消。三个执行入口（同步、stream、run）共享同一个任务服务。流式传输只是订阅任务进度。

验收：重复提交不会重复计费；任意worker查询状态一致；服务中断后有明确失败/恢复策略；超负载时不无限创建线程。

### B09 · P2 · 上传读取阻塞事件循环，限制也不一致

**已复现事件循环阻塞。** 用250ms同步解析替身调用实际异步上传函数，原本20ms的事件循环计时器延后至约251ms执行。这是受控调度实验，不是实际PDF性能基准。

根因：`async read_file` 直接调用同步PDF/图片处理与同步HTTP模型调用；先 `await file.read()` 整份读入，再检查大小。路由限制15MB，底层默认10MB；对外 ReadResult 丢失 pages/status 等结构化信息。

位置：[main.py:92](<D:/company research/backend/app/main.py:92>)、[readers.py:101](<D:/company research/backend/app/readers.py:101>)、[readers.py:168](<D:/company research/backend/app/readers.py:168>)。

建议：分块限量读取，统一上传与解析上限；同步工作放入有界线程池，重CPU解析必要时使用可终止的独立进程。保留页级成功/失败和OCR来源，部分失败应在报告中持续可见。FastAPI不会自动将异步函数内部直接调用的同步工具函数卸载到线程池，参见[官方并发说明](https://fastapi.tiangolo.com/async/)。

验收：慢OCR/PDF期间健康检查和任务查询保持响应；10–15MB行为统一；部分页面未读出不能被当作整份已读。

### B10 · P2 · 输入约束和配置验证不足

**已复现。** 两个空格的企业名通过 CaseIn；`amount='Infinity'` 通过后序列化为null，造成内存与持久化值不一致。CaseIn.need/material_text、SupplementIn.text等无总长度上限。

位置：[models.py:318](<D:/company research/backend/app/models.py:318>)、[models.py:489](<D:/company research/backend/app/models.py:489>)、[config.py:33](<D:/company research/backend/app/config.py:33>)。

建议：去首尾空白、有限数、明确场景枚举、字段/材料/版本/refs数量上限；非法配置在启动时统一列明，参数需要范围和来源版本。不要用静默回退掩盖拼错场景或数据源名。

验收：空白、极长文本、非有限数、非法日期、无效枚举在边界明确拒绝；不会写入无法回读的数据。

### B11 · P2 · 存储和返回体随历史增长，缺少分页与按需加载

**已测量，合成普通案卷。** 1版约50,136字节，10版378,360字节，30版1,109,520字节。30次材料均很短，此数据只说明当前快照重复带来的增长，不能外推成生产容量上限。

列表会读取并校验所有完整案卷；单个案卷与stream结束返回所有版本、原始数据和聊天；每次聊天都重写它。模型上下文虽有120,000字符保护，超限后只能拒答，当前没有按证据范围检索机制。

位置：[store.py:31](<D:/company research/backend/app/store.py:31>)、[main.py:236](<D:/company research/backend/app/main.py:236>)、[assistant.py:163](<D:/company research/backend/app/assistant.py:163>)。

建议：分开 CaseSummary、Version、RawRecord、Message 表/集合；列表游标分页，详情默认当前版，原始记录与历史按需获取。长案卷先做明确来源的选择和预算分配，保持可追溯，不静默截断关键材料。

验收：案卷数量和版本数增长时列表不读取全部历史；建立可重复的分页、响应大小、p95延迟基准。

## 5. 从本地演示到长期服务需要补齐什么

以下主要是明确的设计缺口/上线条件，没有假装已经做过生产攻击或在线负载测试。

| 能力 | 当前证据与影响 | 建议及验收 |
|---|---|---|
| 访问与数据归属 | main没有鉴权或owner约束，案卷列表可直接返回所有记录；CORS为通配。只要接口可访问就可读写；不声称当前已暴露公网 | 内部试用先加访问控制；多人版给Case、Run、Review绑定owner/tenant，每次读取和写入都验证。跨用户测试不能访问彼此案卷；收紧CORS，但CORS不替代鉴权 |
| 反滥用 | /intake、/read、/cases、/chat、GET /companies/profile可触发外部调用；评价author完全由客户端提供 | 请求限额、并发上限、幂等、成本预算；资料查询改成明确的受控动作，避免GET预取/重试触发付费 |
| 配置与生命周期 | 模块import时加载来源、配置和存储；依赖难隔离，客户端生命周期分散 | create_app/settings/lifespan；按生命周期初始化可复用HTTP客户端；服务启动验证必需资源 |
| 可观测性 | 主要只有stream/run异常日志，进度事件不是完整运维指标，health固定ok | request_id、case_id、run_id、provider、step耗时、缓存状态、错误分类、重试/费用、LLM回退率；日志脱敏；分开liveness/readiness与来源新鲜度 |
| 回归与发布 | 依赖大多未锁定，pytest混在运行时依赖；未发现仓库CI工作流、迁移机制和明确回滚路径 | 锁定经过验证的依赖；dev/runtime分组；CI执行现有测试+本报告回归；Schema/OpenAPI差异检查；发布前备份并演练恢复。pip check通过不代表没有漏洞 |
| 数据更新运维 | 本地银行/保险名单日期较早，无代码级新鲜度闸门；证据包在启动时加载 | 名单更新校验、校验和、行数/Schema/类型检查、历史快照、过期提示；规则/参数/数据源各自有版本 |
| 评价治理 | 已有脱敏和限制同author一条，但随机换author即可重复；无申诉或审核状态 | 在对外开放前增加限频、审核/隐藏、申诉、来源可信标记；继续保持评价不冒充事实、不让好评证明安全 |
| 备用适配器传输 | 天眼查旧适配器 TYC_URL为HTTP，同时发送Authorization头，当前文档说未使用 | 启用前确认供应商支持的HTTPS入口并强制验证，或拒绝启用不安全配置；本次未发送测试请求 |

备用适配器位置：[commercial.py:31](<D:/company research/backend/app/sources/commercial.py:31>)。访问控制位置：[main.py:51](<D:/company research/backend/app/main.py:51>)、[main.py:231](<D:/company research/backend/app/main.py:231>)。

## 6. 功能提升：优先完善用户做决定的闭环

### F1. 查询前确认“到底是哪家公司、哪笔交易”

输入简称/品牌/分支机构时返回候选，用户确认全称、信用代码、所属关系。分别记录签约方、收款方、履约方、招聘方。场景金额支持“工资/押金/投资/预付款”角色。

价值：减少错主体查询、错金额门槛和把集团资质套到子公司的风险。依赖A06/A08/A09及统一实体模型。

### F2. 来源覆盖、新鲜度与定向刷新

每个检查项展示“本次查了哪些范围、何时更新、是否缓存、是否只取了部分、失败原因”。允许只重查工商/财务/新闻，预估会发生的调用和费用，并生成可比较的新版本。

价值：用户能分辨“没事”“没查”“没更新”；不必为了刷新一个来源重新跑所有步骤。依赖B01/B04/B06/B08。

### F3. 材料台账与页级引用

材料有独立ID、hash、版本、页码/区域、读取方式、读取状态、上传时间和原文。支持用户纠正OCR结果、标记失效/替代，而原材料和修改记录保留。引文点击可定位到文件原页，不只到一大段文字。

价值：更容易核对金额、户名和否定词；“只读出一半”不会隐藏在一次性的note里。当前read_material内部已有pages/status，可优先打通而非另起一套解析器。

### F4. 同一案卷内按合同/产品组织材料

当前构建把历史material和self_description合并成一个文本池，每类宣称集中成A1…A9。随着多产品、多份合同进入，金额、退款条款和收款信息容易跨材料混用。

增加transaction_id、claim_id、material_revision、适用日期；相冲突条款并列呈现。上传新协议时明确它替代哪份、还是另一笔交易，不默认让最后上传的获胜。

价值：从一次演示的“公司报告”升级为能长期维护的“本次交易案卷”。先做结构化范围管理，再考虑更复杂的模型抽取。

### F5. 人工核实与行动清单闭环

每条待核事项记录负责人、待问问题、对方回复、支持/反驳证据、处理结论和历史。人工澄清不覆盖客观事实；撤回误识别要有理由。不同展示页基于同一个有效状态生成。

价值：用户知道下一步做什么，以及做完后哪个疑点真正解决。依赖A01/A04/B07；判断页当前默认隐藏，开放前应完成端到端验收。

### F6. 财务分析提升到“可比且可核”

保留币种、单位、报告期、合并/母公司口径；季度累计值不与全年直接比较。增加经营现金流、净利润/现金流差异、短期偿债信息，但必须先有数据覆盖和行业适用规则。每个比率能看到分子、分母、来源；非上市公司无公开财报要明确说明。

价值：比增加更多没有口径解释的指标更有用。现有finance主要展示平台指标，适合作为起点；暂不将这些建议当作已经验证的投资判断规则。

### F7. 可复核的报告导出与分享

导出固定版本、证据目录、材料读取缺口、数据截止日、规则版本、人工处置记录和免责声明；分享按只读/限时/撤销权限控制。旧版导出不能被后来刷新sources改变。

价值：家人、同事、柜员看到同一版依据，能够复核而不是只收到一段结论。依赖访问控制与不可变证据快照。

### F8. 场景覆盖说明与质量评测

展示求职、预付、签约、接手等场景真正已经核到哪些事项；尚无能力的部分明确列为待核，避免换了标题让人以为完成了专项尽调。建立真实脱敏/合成反例集，按场景统计误报、漏报、主体错配、来源缺失和人工纠正率。

价值：扩展功能有可度量的质量目标。优先补本次发现的否定句、主体、部分结果、币种、历史时态，而不是只增加场景模板数量。

## 7. 推荐的工程结构与落地顺序

继续保持一个可维护的模块化后端。当前约7,500行代码，复杂度主要来自状态和证据语义，拆成多个独立服务并不能自动解决这些问题。

建议职责：

```text
API（鉴权、输入约束、错误契约）
  → Case / Task / Review 应用服务（事务、幂等、revision、预算）
    → 数据采集适配器（主体、覆盖、新鲜度、币种、完整度）
    → 证据快照与材料台账
    → 规则判定 + 版本差异 + 人工状态转换
    → 统一报告投影（短句、图表、一页纸、问答事实）
    → 模型解释边界（可引用的fact_id、预算、校验、兜底）
  → Repository 与任务状态持久化
```

| 阶段 | 做什么 | 进入下一阶段的条件 |
|---|---|---|
| 1. 守住结果 | A01/A02/A03/A04/A05/A09/A10/A11；补持久化回读、交错并发、语义反例测试；同步解决撤回投影 | 已成功操作不丢；案卷始终可回读；否定句不反转；来源失败不代表改善；模型不能篡改关键事实 |
| 2. 守住证据 | A06/A07/A08、B01/B02/B03/B05/B06；统一SourceResult/实体/Money/快照契约 | 不能混公司/币种/部分与全量；过期和失败可见；来源、时间和权限可复核 |
| 3. 守住运行 | 预算预留、输入/上传限制、任务有界执行和持久状态、访问控制、存储事务、分页、日志指标、CI和备份 | 两个客户端并发与重启测试通过；可控费用；权限隔离；有恢复演练结果 |
| 4. 扩展功能 | F1→F2→F3/F4→F5→F6/F7/F8，按前置条件逐步交付 | 每项都有面向用户的验收，而非只新增接口 |

存储选型按使用范围决定：

| 使用范围 | 建议 |
|---|---|
| 本机单进程演示 | 可先保留JSON，补状态校验、revision、互斥、唯一临时文件；备份历史。不把它作为多人长期方案 |
| 单机小规模内部使用 | SQLite事务、索引、独立版本/消息表、持久任务表是低运维成本候选；注意SQLite同时只有一个写入者，网络与模型调用不放在长事务里 |
| 多实例/多人正式服务 | Postgres等服务端数据库与独立worker；任务租约、跨实例预算/限流、权限隔离一起设计 |

SQLite的并发边界见[官方隔离说明](https://www.sqlite.org/isolation.html)。无论采用哪一种数据库，先读到旧revision、长时间做外部调用、再整份覆盖的逻辑都仍可能丢更新，必须显式处理。

HTTP客户端应在应用生命周期内复用并关闭，以使用连接池，参见[HTTPX客户端文档](https://www.python-httpx.org/advanced/clients/)。不要同时重写所有同步接口，先处理已证实阻塞的上传和核心慢调用路径。

模型状态验证可参考[Pydantic配置文档](https://docs.pydantic.dev/latest/api/config/)。启用validate_assignment能更早发现A01，但无法代替合法的状态映射、历史迁移和事务。

## 8. 下一轮回归门槛

| 类型 | 必须守住的不变量 |
|---|---|
| 案卷存储 | save后可由新实例加载；current与末版一致；版本不可回退；全部成功写入均保留 |
| 状态机 | 合法操作映射到合法状态；人工记录可审计；重新核实不能令文件坏掉 |
| 证据 | 来源/主体/时间/币种一致；原始材料不自动成为已证实事实；部分结果不证明全量无记录 |
| 规则 | 加否定词或改变主体/条件后不能保持原指控；机构类型不能互相冒充 |
| 模型 | 引用存在但事实错误也拒绝；首屏短句不反转状态；任何模型失败可回退 |
| 版本差异 | 数据失败≠改善；数量变化≠未变；改需求不预设事实未变 |
| 任务 | 重复请求幂等；并发有上限；多worker状态一致；中断有可解释的恢复/终止结果 |
| 成本 | 并发不能越限；任务与全局预算分别统计；缓存命中与计费可追踪 |
| 文档读取 | 大小上限一致；坏文件不拖垮事件循环；页级缺失持续可见 |
| 部署 | 依赖锁定、CI测试、Schema迁移、备份恢复、权限负例与日志脱敏都有验收证据 |

本次复现脚本是一次性审计证据。修复时应把各问题改写成独立回归测试，先使其在当前代码上失败，再验证修复；不要把“复现到了错误”的探针成功误当作产品测试通过。
