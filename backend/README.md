# 企er（X-Ray）后端

施工依据：[黑客松版 PRD](../docs/2026-10-02-xray-hackathon-prd.md)。主线：输入企业名和一句需求 → 汇集数据 → 分层报告 → 小企（AI 助手）→ 补充信息后二次分析。

## 运行

```
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

- 首页：http://localhost:8000 （研究室；首次启动或修改后，在 `research-room/` 执行 `npm install`、`npm run build:home`）
- 案卷与报告：http://localhost:8000/xray/#/cases （`web/`，原生 JS，改完刷新即可）
- 接口文档：http://localhost:8000/docs
- 断网备用的静态演示：http://localhost:8000/demo/
- 测试：`.venv\Scripts\python -m pytest`，共 329 个，不连网、不需要 Key、不扣企查查积分；前端版本与流式接入测试在仓库根目录跑 `node --test web/tests/*.test.cjs`，共 27 个
- 新机器：`python -m venv .venv`，再 `.venv\Scripts\python -m pip install -r requirements-b.txt`（包含共享依赖和图片验证所需的 Pillow）。不要复制别人的 `.venv`，解释器路径不能跨机器用

### 配置（`backend/.env`）

复制 `.env.example` 为 `.env` 再填。`.env` 被 git 忽略，Key 只放这里，不写进文档和提交。改完重启后端。什么都不填也能跑：小企退回模板回答，需求识别退回关键词，图片材料提示手动粘贴，真实公司的工商登记显示"没查"。

| 配置 | 默认 | 作用 |
|---|---|---|
| `TOKENDANCE_BASE_URL`、`TOKENDANCE_API_KEY` | — | 比赛模型网关，写到 `/v1` 这一级。地址 `https://tokendance.space/gateway/v1` |
| `TOKENDANCE_MODEL`、`TOKENDANCE_VISION_MODEL` | — / 同文本模型 | 文本和看图的模型，现在都用 `qwen3.8-max` |
| `TOKENDANCE_JSON_MODE` | `0` | `1` 让网关按 JSON 输出，已在线验证，`.env.example` 里是 `1`；服务端照样做 Schema 校验 |
| `TOKENDANCE_ENABLE_THINKING` | `0` | 长思考。开了以后完整案卷问答会超过 45 秒超时，所以默认关 |
| `TOKENDANCE_TIMEOUT` | `45` | 单次请求超时，秒 |
| `XRAY_LLM_MODE` | `live` | `live` 调网关，成功结果录进 `data/cache/`，网络故障时回放并标明；`replay` 只回放（断网演示，界面标"离线回放"）；`off` 不调模型，也不联网搜索。401/403 直接报鉴权问题，不重试 |
| `XRAY_COMMERCIAL` | 空 | 商业工商数据：`qcc_agent`（企查查智能体数据平台，推荐）、`qcc`、`tianyancha`；空就不查 |
| `QCC_AGENT_KEY` | — | 企查查智能体平台的 Key，不带 `Bearer`。可以填多个，用逗号隔开，见下文"企查查" |
| `XRAY_QCC_MAX_POINTS` | `300` | 单次运行最多实际花多少积分，缓存命中不算 |
| `QCC_APP_KEY`、`QCC_SECRET_KEY`、`TIANYANCHA_TOKEN`、`XRAY_COMMERCIAL_MAX_CALLS` | — / `30` | 老的企查查、天眼查开放平台，要企业实名，现在没用 |
| `XRAY_AMAC_DETAIL` | `1` | 名单里查到的私募管理人，再取一次中基协详情页；测试里设 `0` |
| `XRAY_REF_DEPOSIT_RATE` | `0.011` | 承诺收益拿来比的一年期定存参考利率（演示参数） |
| `XRAY_CASES_DIR`、`XRAY_REVIEWS_DIR`、`XRAY_CACHE_DIR` | `data/cases` 等 | 案卷、用户评价、缓存放哪；测试指到临时目录 |

网关的实测结果和长思考超时的来龙去脉见 [Tokendance 能力记录](../docs/tokendance.md)；版本化引用、缓存与回放、还没接进主流程的模型增强见 [后端 B 接入说明](../docs/backend-b-integration.md)。网站已部署到 `https://qier.asia`，由 Caddy 提供 HTTPS，按用户要求无需登录即可使用；服务器使用独立的 `/etc/qier/backend.env` 与 `/var/lib/qier` 数据目录，维护及验收说明见 [部署文档](../docs/deployment.md)。

### 浏览器演示验证

额外安装 `requirements-browser.txt`，在装有 Microsoft Edge 的 Windows 上运行：

```powershell
.venv\Scripts\python -m pip install -r requirements-browser.txt
.venv\Scripts\python tools/acceptance_browser.py
# 以下命令会调用已配置的真实网关，产生 API 用量：
.venv\Scripts\python tools/acceptance_browser.py --live
# 同时验证企查查（会消耗商业查询额度）：
.venv\Scripts\python tools/acceptance_browser.py --live --commercial
```

其他平台需要自行准备 Playwright Chromium。脚本只启动本机临时端口，使用新建的隔离案卷和缓存，不覆盖现有用户数据。默认关闭模型和企查查；`--live` 验证真实 A/B 问答、两次补充、旧版引用、A4 PDF、窄屏与静态备用页，然后恢复本次测试自己的服务端提问前快照，在阻断外部 HTTP 的条件下验证同案卷回放和未命中提示。`--commercial` 显式启用企查查；`--seed-cache <上次验收目录>/cache` 将此前缓存复制到新的隔离目录，避免重复查询。输出在仓库被忽略的 `.tmp/browser-acceptance-*/`，`result.json` 的 `completed` 才是本次结果；失败不可当通过。本轮结果见 [B 合并交接](../docs/backend-b-integration.md)，[旧验收记录](../docs/2026-10-02-browser-acceptance.md) 保留为历史快照。学校实际网络和三分钟讲稿仍需人工排练，见 [演示操作单](../docs/demo-runbook.md)。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 名单条数和日期、已有证据包、模型状态、企查查状态（Key 个数、正在用第几个、本次花了多少积分；不含 Key） |
| GET | `/api/sources` | 数据来源目录（`Source`）：每个来源的名称、类型、日期、链接；报告里的 `source` 指向这里 |
| GET | `/api/scenarios` | 6 个场景模板 |
| GET | `/api/glossary` | 名词解释词表（`app/glossary.json`），前端标注和助手共用 |
| POST | `/api/intake` | `{need}` → 场景、关注点、替谁看、金额（输入页预览用，用户可改） |
| POST | `/api/read` | 上传文件（txt / pdf / docx / 图片）→ 文字；读不出来返回 `failed` 和提示 |
| POST | `/api/cases` | 建案卷，生成第 1 版报告。`company_name`、`need`，可选 `scenario`、`for_whom`、`amount`、`material_text` |
| GET | `/api/cases`、`/api/cases/{id}` | 案卷列表；单个案卷（全部版本、原始数据、对话） |
| POST | `/api/cases/{id}/supplements` | 二次分析。`kind`：`material` 新材料 / `reply` 对方回复 / `need` 改需求；`text` 必填 |
| POST | `/api/cases/stream`、`/api/cases/{id}/supplements/stream` | 同上两个，但边查边发进度（NDJSON，一行一个事件），最后一行是整个案卷。给等待动画用，格式见 `docs/progress-events.md` |
| POST | `/api/runs`、`/api/cases/{id}/runs` | 同建案卷、补充信息，但马上返回任务编号（202），后台跑；进度记在 `data/runs/`（git 忽略） |
| GET | `/api/runs/{run_id}?after=n` | 取第 n 条以后的进度和状态（`running` / `complete` + `case_id` / `error` / `interrupted`）。页面刷新后用同一个编号接着看，不重复提交 |
| POST | `/api/cases/{id}/resolve` | 对一条判断下结论（`judgment_id`、`action`：clarified / withdrawn / recheck、`note`），出一版新报告。界面上判断页先藏着（地址带 `?judg=1` 才显示），见[判断更新契约](../docs/2026-10-02-judgment-update-contract.md) |
| POST | `/api/cases/{id}/reviews` | 把这家公司最新的用户评价放进案卷，出一版新报告（"更新用户评价"）；评价没变返回 409 |
| GET | `/api/reviews?company=&author=` | 某家公司的用户评价：条数、1–5 星分布（不算平均分）、评价列表（新的在前；`mine` 标出这个浏览器写的） |
| POST | `/api/reviews` | 写评价：`company`、`stars` 1–5、`relation`（customer / employee / applicant / other）、`text` 10–500 字、可选 `nickname`、`author`（浏览器匿名编号）。同一编号对同一家公司只能写一条，重复 409 |
| POST | `/api/cases/{id}/chat` | AI 助手。`text`，可选 `refs`（选中的条目 id）、`version`（正在浏览的版本，正整数） |
| GET | `/api/cases/{id}/onepager?audience=family\|teller` | 一页结论：家人版 / 网点版 |
| GET | `/api/demo?case=C`、`/api/demo/cases` | 演示案例的输入和要补充的信息（`data/demo_cases.json`） |
| GET | `/api/licenses/check?name=` | 查机构是否在银行业金融机构名单里 |
| GET | `/api/companies/profile?name=` | 某家公司汇集到的全部记录 |

返回格式以 `app/models.py` 为准。[`docs/sample-case.json`](../docs/sample-case.json) 是早期样例（演示案例 C 补了一次对方回复、问了一次助手之后的案卷），后来加的 `glance`、`terms`、`charts`、`judgments` 等字段不在里面。

## 前端（`web/`）

界面名叫"企er"，AI 助手叫"小企"。顶部三个分区，右边一栏始终是小企。细节见 [前端交接](../docs/frontend.md)。

| 页面 | 地址 | 内容 |
|---|---|---|
| 查企 | `#/check`（空地址也到这里） | 公司全称 + 一句需求；需求停顿 0.8 秒自动识别场景（可改）；可选材料（粘贴或上传）；演示案例一键填入 |
| 案卷 | `#/cases` | 查过的公司和它们的每一版 |
| 我的 | `#/me` | 模型和数据源状态、每家都查的名单、名词表、这几条底线 |
| 报告页 | `#/case/<id>`、`#/case/<id>/v/<n>` | 首屏"一眼看懂"：第一问的结论、它说的对记录里的、四个信号小卡、下一步该问什么；"文字版"里是一页结论（家人版 / 网点版，可打印成一页 A4）。下面是图和标签页：变化（第 2 版起）、四个信号、宣称 vs 记录、该问对方的、原始数据、评价 |
| 小企 | 右栏（窄于 1280px 收成右下角的"小企"按钮） | 报告里每条右边有"问"（悬停出现）；回答里的出处和逐字引文点得开；提到新情况时给"加入案卷"按钮，走二次分析，聊天本身不改报告 |

- 来源 = 来源类型 + 数据日期 + 原始数据编号，一行灰字，点开就是原始记录；原始记录里列出报告用到它的地方，引文高亮。
- 虚构公司全程挂"演示数据 · 公司为虚构"，打印出来的一页结论上也有。只有真查到了演示数据才挂，真实公司"没查"的记录显示"没有数据"。
- 二次分析的对话框里，演示案例准备好的补充材料可以一键填入。
- 报告页最后一个标签是"评价"：用户个人观点，未经核实。星级分布、写评价、评价列表；有没进这一版的评价时，可以"放进报告"出一版新的。

## 用户评价（`app/reviews.py`）

评价按公司存，不按案卷存；它是别人说的、没核实，只让人多留意，不让人放心：
- 有评价时，汇集数据记一条原始数据"用户评价（N 条）"（来源 `user_reviews`，类型 `user_review`，不含作者编号）。
- 口碑信号加一条 `reputation.user_reviews`：少于 3 条只作参考；3 条以上、1–2 星占一半或更多，标"要留意"；其余只作参考。**好评不标绿，差评不到"有问题"**。
- 一页结论和判断（judgments）都不收评价。助手可以引用评价，但越界检查不把评价原文当作记录：评价里写了"非法集资"，助手也不能借它说出口。
- 存之前遮掉手机号、身份证号、住址、出生信息；定性话照发，页面统一写"用户个人观点，未经核实"。
- 没有账号：浏览器生成匿名编号，后端只存哈希，同一浏览器对同一家公司只能写一条。防手滑，不防刷。
- 用户写的评价在 `data/reviews/`（git 忽略）；演示评价只给虚构的满盈禾，在 `data/fixtures/reviews.json`。不给真实公司编评价。

## 条目 id（前端跳转、助手引用都用它）

| id | 指什么 |
|---|---|
| `A1`…`A9` | 说法核验，按类型固定：资格、收益承诺、合作机构、背景、注册资本、规模、收款信息、退款承诺、先交钱 |
| `M1` | 该写却没写的内容 |
| `risk.bank_list` 这种 | 信号条目：`信号.条目` |
| `Q1`… | 该问对方的问题 |
| `R1`… | 原始数据（RawRecord）；每条检查的 `ref` 指向它 |
| `nfra_bank_list` 这种 | 数据来源（Source）；法规、参数类检查只有 `source` 没有 `ref` |

## 数据

| 数据 | 真实 / 演示 | 位置 |
|---|---|---|
| 持牌机构名单 | **真实**：金融监管总局《银行业金融机构法人名单》，截至 2025-06-30，共 4070 家 | `data/licensed_institutions.csv` |
| 保险机构名单 | **真实**：金融监管总局《保险机构法人名单》，截至 2025-06-30，共 238 家 | `data/registries/nfra_insurance.csv` |
| 期货公司名录 | **真实**：证监会，2026 年 8 月，共 150 家 | `data/registries/csrc_futures.csv` |
| 支付机构名单 | **真实**：人民银行《已获许可机构（支付机构）》，含许可证号、业务类型、有效期 | `data/registries/pbc_payment.csv` |
| 私募基金管理人 | **真实**：中基协公示全量，共 18,396 家，含登记编号、在管基金数、特别提示/诚信信息标记 | `data/registries/amac_managers.csv` |
| 企业工商信息（商业） | 企查查智能体数据平台（推荐，个人可注册）或企查查、天眼查开放平台，配置了才用，来源标"商业数据" | 缓存在 `data/cache/qcc_agent/`、`data/cache/commercial/` |
| 财务数据、新闻舆情（商业） | 企查查智能体数据平台的 `get_financial_data`、`get_news_sentiment`，只在用智能体平台时查；虚构公司不查 | 同上，`data/cache/qcc_agent/` |
| 实控人、许可资质、变更、开庭立案、劳动仲裁、招聘（商业） | 企查查智能体数据平台，工商查到了这家公司才查（`app/sources/qcc_more.py`） | 同上 |
| 上市公司公告、年报原文 | **真实**：巨潮资讯网（证监会指定披露网站），免费、不用 Key；有股票代码才查。`XRAY_CNINFO=0` 关掉 | 缓存在 `data/cache/cninfo/`，一天内直接用缓存 |
| 权威媒体报道 | 联网搜索，只搜人民网、新华网、央视、财新、第一财经、证券时报、中国证券报、上海证券报等二十多家 | 同联网查证 |
| 人工采集的真实记录（公示系统、中基协、投诉、公司自述） | **真实**，来源类型 `collected` | `data/evidence_packs/<公司全称>.json`，怎么填见该目录 README |
| 企业登记、年报、私募登记、投诉 | 演示，3 家公司全部虚构 | `data/fixtures/` |
| 演示用材料（宣传单、对方回复、协议节选） | 演示，虚构 | `data/fixtures/flyers/` |

每家公司都查五份官方名单（银行、保险、期货、支付、私募），每份各记一条原始数据。企业登记按顺序找：证据包 → 商业接口 → 演示数据，都没有就记"没查"。证券公司、公募基金名录还没接，名字像证券或基金公司的，资格一条判"无法核验"，不硬下结论。

配了模型网关后，每家公司还会联网查证（`app/sources/web.py`，虚构的演示公司不查）：
- 只搜监管、法院、政府网站，找点名它的处罚、监管措施、风险提示、法院文书。这类结果必须在摘要里有公司全称才保留，来源标"官方记录"。
- 全网搜"简称 + 投诉、维权、兑付"，归进口碑信号（进度里是 `opinion` 那一步）。只匹配上简称的，原始数据里标"可能是同名的别家"。
- 天眼查、企查查等商业数据网站的结果一律丢掉。分类靠关键词，不让模型判断。每次搜索都有缓存，断网时回放。网关实测见 [docs/tokendance.md](../docs/tokendance.md)。

企查查、天眼查开放平台只取基本工商信息，处罚、出质、被执行等字段它不给，报告里这些项显示"没查"，不显示"无"（`CompanyProfile.checked` 控制）。查回来的公司名和输入对不上时不采用。

企查查智能体数据平台（`app/sources/qcc_agent.py`）一家公司依次调：工商信息 → 风险扫描（35 项各有几条）→ 有记录的项再取明细 → 股东、分支机构、上市信息。平台是 MCP 协议，实际就是 `POST https://agent.qcc.com/mcp/<server>/stream` 的 JSON-RPC 请求。规矩：
- 0 条的项不调明细，算"查了，没有"；明细只给前几条时按风险扫描的总数算（`CompanyProfile.counts`）。
- 平台摘要里"排查安全，允许进入下一步"这类定性话，存档前删掉。
- 法定代表人、负责人、联系方式不存；自然人股东写成"自然人股东A"，申请人等是个人的写"自然人"；处罚决定原文里只留讲这家公司的分条，被处罚的个人写成"相关个人"。
- 积分：一家公司约 40 积分（股东 20、风险扫描 5、分支机构 5、工商信息 3……），平台对同一家公司每月最多扣 100；`XRAY_QCC_MAX_POINTS` 限制单次运行的总花费。结果按"公司 + 工具"缓存在 `data/cache/qcc_agent/`，不重复扣。新开 worktree 或换机器时把这个缓存目录一起拷过去，否则会重新扣积分。
- 多个 Key：`QCC_AGENT_KEY=key1,key2,key3`。一直用当前这个，它失效、积分用完或被限流才换下一个；"查不到这家公司"这类和 Key 无关的错误不换。都不能用时，报告里记"查询失败"，并写明每个 Key 的原因。`/api/health` 只显示 Key 的个数和正在用第几个。
- 出质、抵押按角色算：出质只算标的企业是它的，抵押只算抵押人是它的；它当债权人的条数写在说明里，不算它的风险。风险扫描里打官司的条数不分原告被告，只标"要留意"；终本案件、税务非正常户这类才标"有问题"。
- 证据包里没有 `registry` 段（只摘了文书）时，登记信息照样从企查查取。
- 宣称上市的，对照上市信息里的交易所、股票代码。
- 财务数据（`app/sources/finance.py`，每家 5 积分）：只有上市、发债等公开财报的公司才有。照抄营业总收入、净利润、总资产，以及平台算好的营收同比、资产负债率、净资产收益率，不自己重算、不判断高低（银行负债率 90% 以上是常态）；只有净利润为负标"要留意"。没有就写"没有公开的财务数据"，不等于经营差。报告财务卡片下面列近三年年报。
- 补充信息（`app/sources/qcc_more.py`，8 个工具，每家约 40 积分）：实际控制人、行政许可、资质证书、变更记录、开庭公告、立案信息、劳动仲裁、招聘信息。个人名字一律不存：实控人是个人只写"自然人"，开庭立案只留案号、案由、法院、日期和它的角色，变更记录只留日期和项目（名称、住所、注册资本这三类才留前后内容）。只看它当被告的案子；能标"要留意"的只有：近一年改名或换法定代表人、近两年被告的投资合伙理财类纠纷、近两年的劳动纠纷、在 3 个以上城市招人但参保不到 10 人。实际控制人还用来核验"国资背景"：控制人是个人就判"与记录不符"。
- 巨潮资讯网（`app/sources/cninfo.py`）：最新年报原文链接，加最近一年标题带处罚、诉讼、问询字样的公告（按关键词分，标题不等于结论）；有处罚或监管措施的标"要留意"。
- 权威媒体（`web.py` 的 `find_media`）：标题里有它的名字、又说到处罚或警示的，标"要留意"；同一实控人的兄弟公司常被一起报道，只在正文里提到它的不算。网页标题、摘要里的"法定代表人：某某""（公司、某某）"这类个人名字存档前遮掉；政府任免通知、审计公告里点名的公职人员没有遮。
- 新闻舆情（`app/sources/news.py`，每家 5 积分）：平台给总条数和最近 30 条（标题、时间、来源、负面/中立/正面）。倾向是企查查的模型标的，报告里写"企查查标为负面"；近一年有负面的标"要留意"，不到"有问题"。只存负面新闻的标题，标题括号里列的个人名字换成"相关个人"；中立、正面的只存日期和来源。

更新名单：

```
.venv\Scripts\python tools\build_license_index.py data\raw\<银行业名单>.pdf <截至日期> <原文链接>
.venv\Scripts\python tools\build_license_index.py data\raw\<保险名单>.pdf <截至日期> <原文链接> registries/nfra_insurance 保险机构法人名单
.venv\Scripts\python tools\fetch_amac.py
.venv\Scripts\python tools\fetch_official_lists.py futures
.venv\Scripts\python tools\fetch_official_lists.py payment
```

## 约定

- 结论全部来自 `app/analysis/verify.py`、`signals.py` 里的确定性规则，同样的输入永远得到同样的结论。模型只做四件事：认需求、读材料、说人话、答问题。
- 二次分析是全量重跑后由 `analysis/diff.py` 按 id 逐条比对，没变的也列出来。
- 助手的回答由程序校验：出处 id 必须在案卷里，引文必须在原文里逐字找得到，否则丢掉并计入 `dropped`。让助手"判定安全""忽略规则"的提问由程序直接拦下。
- 没数据写"没查"（`status: none`），不把没数据说成没问题，也不说成有问题。不打安全分，不下"诈骗"之类的定性。
- 场景只改排序和措辞，不改事实：加场景就是在 `app/scenarios/` 加一个 JSON。
- 报告里的图（`app/analysis/charts.py`，存在 `Version.charts`）全部从记录和规则算出，不经过模型：注册资本说的 / 登记的 / 实缴的，承诺收益 vs 定存参考利率，宣称门店 vs 登记分支机构，股东构成，近 12 个月投诉，时间线。没查的值是 `null`，前端画成"没查"，不画成 0；不画风险分和雷达图；自然人股东不显示姓名；时间线不放"其他提及"类的政府网站结果，法院文书只写类别。
- 报告生成时一并写好"一眼看懂"的短句和名词（`app/plain.py`，存在 `Version.glance`、`Version.terms`）：模型把规则写的长句缩成 18 字以内的短句，并补上词表里没有的名词（标"AI 解释"）。程序逐条校验：短句里的数字必须在原句里出现，不许越界，原句里"不需要""不等于"这类改变意思的词不能丢；名词必须在报告里一字不差出现，不能提这家公司。校验不过就丢掉，前端用原句。二次分析时原句没变的短句和名词直接沿用。接模型时建案卷多花约 4–6 秒（实测：满盈禾从约 1 秒到 7.7 秒，杭州银行从约 5 秒到 9 秒）；二次分析只缩新条目，约 3 秒。
- 名词解释优先使用人工固定词表 `app/glossary.json`；报告生成时可补充词表里没有的术语，标为 origin=model 和"AI 解释"，随 `Version.terms` 保存。助手读取所选版本的术语，出处写作 `[term.<id>]`。两类解释都不算公司调查记录，不能拿来给公司定性或用示例数字证明公司事实。
