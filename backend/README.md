# X-Ray 后端

施工依据：[黑客松版 PRD](../docs/2026-10-02-xray-hackathon-prd.md)。主线：输入企业名和一句需求 → 汇集数据 → 四层报告 → AI 助手 → 补充信息后二次分析。

## 运行

```
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

- 前端：http://localhost:8000 （`web/`，原生 JS，不打包，改完刷新即可）
- 接口文档：http://localhost:8000/docs
- 断网备用的静态演示：http://localhost:8000/demo/
- 测试：`.venv\Scripts\python -m pytest`（不连网、不需要 Key）
- 新机器：`python -m venv .venv`，再 `.venv\Scripts\python -m pip install -r requirements-b.txt`（包含共享依赖和图片验证所需的 Pillow）

### 接模型

复制 `.env.example` 为 `.env`，填比赛 Tokendance 的地址、Key、模型名，Key 只保存在被 Git 忽略的本机 `.env`。当前地址为 `https://tokendance.space/gateway/v1`，文本与视觉均使用 `qwen3.8-max`，已在线验证 `TOKENDANCE_JSON_MODE=1`。`TOKENDANCE_ENABLE_THINKING=0` 默认关闭长思考，避免完整案卷问答因长思考超时；`1` 开启，显式留空则不传该参数，修改后重启服务。不填凭据也能跑：助手退回模板回答，需求识别退回关键词，图片材料提示手动粘贴。

`XRAY_LLM_MODE`：`live` 调网关并把成功结果录进 `data/cache/`，网络故障时尝试明确标注的回放；`replay` 只回放（断网演示，界面会标"离线回放"）；`off` 不调模型。401/403 直接报告鉴权问题，不重试。

2026-10-02 06:18（中国时间）已用更新的本机凭据跑通合成材料的真实网关验收：需求识别、中文图片读取、完整案卷问答、v2 后查询旧版和同输入回放。06:28 合并报告短句功能后再次通过，两次问答实测约 7.74 / 5.19 秒，均为模型回答且通过引用校验；不是延迟承诺或真实公司判断验收。这两轮历史测试使用进程内 HTTP 路由，不是浏览器验收。详见 [Tokendance 能力记录](../docs/tokendance.md)；B 的版本引用、缓存与待接入服务见 [B 接入说明](../docs/backend-b-integration.md)。没有进行公网部署。

### 浏览器演示验证

额外安装 `requirements-browser.txt`，在装有 Microsoft Edge 的 Windows 上运行：

```powershell
.venv\Scripts\python -m pip install -r requirements-browser.txt
.venv\Scripts\python tools/acceptance_browser.py
# 以下命令会调用已配置的真实网关，产生 API 用量：
.venv\Scripts\python tools/acceptance_browser.py --live
```

其他平台需要自行准备 Playwright Chromium。脚本只启动本机临时端口，使用新建的隔离案卷和缓存，不覆盖现有用户数据。默认关闭模型；`--live` 验证真实 A/B 问答、两次补充、旧版引用、A4 PDF、窄屏与静态备用页，然后恢复本次测试自己的提问前快照，在阻断外部 HTTP 的条件下验证同案卷回放和未命中提示。输出在仓库被忽略的 `.tmp/browser-acceptance-*/`，`result.json` 的 `completed` 才是本次结果；失败不可当通过。最新 [本机完整验收记录](../docs/2026-10-02-browser-acceptance.md) 已通过。学校实际网络和三分钟讲稿仍需人工排练，见 [演示操作单](../docs/demo-runbook.md)。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 名单条数和日期、已有证据包、模型状态（不含 Key） |
| GET | `/api/scenarios` | 6 个场景模板 |
| GET | `/api/glossary` | 名词解释词表（`app/glossary.json`），前端标注和助手共用 |
| POST | `/api/intake` | `{need}` → 场景、关注点、替谁看、金额（输入页预览用，用户可改） |
| POST | `/api/read` | 上传文件（txt / pdf / docx / 图片）→ 文字；读不出来返回 `failed` 和提示 |
| POST | `/api/cases` | 建案卷，生成第 1 版报告。`company_name`、`need`，可选 `scenario`、`for_whom`、`amount`、`material_text` |
| GET | `/api/cases`、`/api/cases/{id}` | 案卷列表；单个案卷（全部版本、原始数据、对话） |
| POST | `/api/cases/{id}/supplements` | 二次分析。`kind`：`material` 新材料 / `reply` 对方回复 / `need` 改需求；`text` 必填 |
| POST | `/api/cases/{id}/reviews` | 把这家公司最新的用户评价放进案卷，出一版新报告（"更新用户评价"）；评价没变返回 409 |
| GET | `/api/reviews?company=&author=` | 某家公司的用户评价：条数、1–5 星分布（不算平均分）、评价列表（新的在前；`mine` 标出这个浏览器写的） |
| POST | `/api/reviews` | 写评价：`company`、`stars` 1–5、`relation`（customer / employee / applicant / other）、`text` 10–500 字、可选 `nickname`、`author`（浏览器匿名编号）。同一编号对同一家公司只能写一条，重复 409 |
| POST | `/api/cases/{id}/chat` | AI 助手。`text`，可选 `refs`（选中的条目 id）、`version`（正在浏览的版本，正整数） |
| GET | `/api/cases/{id}/onepager?audience=family\|teller` | 一页结论：家人版 / 网点版 |
| GET | `/api/demo?case=C`、`/api/demo/cases` | 演示案例的输入和要补充的信息（`data/demo_cases.json`） |
| GET | `/api/licenses/check?name=` | 查机构是否在银行业金融机构名单里 |
| GET | `/api/companies/profile?name=` | 某家公司汇集到的全部记录 |

完整的返回格式见 [`docs/sample-case.json`](../docs/sample-case.json)：演示案例 C 补了一次对方回复、问了一次助手之后的案卷。

## 前端（`web/`）

| 页面 | 地址 | 内容 |
|---|---|---|
| 输入页 | `#/` | 公司全称 + 一句需求；需求停顿 0.8 秒自动识别场景（可改）；可选材料（粘贴或上传）；演示案例一键填入；最近的案卷 |
| 报告页 | `#/case/<id>`、`#/case/<id>/v/<n>` | 首屏是一页结论（家人版 / 网点版，可打印成一页 A4）；下面是标签页：变化（第 2 版起）、四个信号（只列要看的，其余折叠）、宣称 vs 记录、该问对方的、原始数据（每个来源单独标查到了 / 查了没有 / 没查 / 查询失败） |
| 助手 | 报告页右栏（窄屏是"问助手"按钮） | 报告里每条右边有"问"（悬停出现）；回答里的出处和逐字引文点得开；提到新情况时给"加入案卷"按钮，走二次分析，聊天本身不改报告 |

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
| 人工采集的真实记录（公示系统、中基协、投诉、公司自述） | **真实**，来源类型 `collected` | `data/evidence_packs/<公司全称>.json`，怎么填见该目录 README |
| 企业登记、年报、私募登记、投诉 | 演示，3 家公司全部虚构 | `data/fixtures/` |
| 演示用材料（宣传单、对方回复、协议节选） | 演示，虚构 | `data/fixtures/flyers/` |

每家公司都查五份官方名单（银行、保险、期货、支付、私募），每份各记一条原始数据。企业登记按顺序找：证据包 → 商业接口 → 演示数据，都没有就记"没查"。证券公司、公募基金名录还没接，名字像证券或基金公司的，资格一条判"无法核验"，不硬下结论。

配了模型网关后，每家公司还会联网查证（`app/sources/web.py`，虚构的演示公司不查）：
- 只搜监管、法院、政府网站，找点名它的处罚、监管措施、风险提示、法院文书。这类结果必须在摘要里有公司全称才保留，来源标"官方记录"。
- 全网搜"简称 + 投诉、维权、兑付"，归进口碑信号。只匹配上简称的，原始数据里标"可能是同名的别家"。
- 天眼查、企查查等商业数据网站的结果一律丢掉。分类靠关键词，不让模型判断。每次搜索都有缓存，断网时回放。网关实测见 [docs/tokendance.md](../docs/tokendance.md)。

企查查、天眼查开放平台只取基本工商信息，处罚、出质、被执行等字段它不给，报告里这些项显示"没查"，不显示"无"（`CompanyProfile.checked` 控制）。查回来的公司名和输入对不上时不采用。

企查查智能体数据平台（`app/sources/qcc_agent.py`）一家公司依次调：工商信息 → 风险扫描（35 项各有几条）→ 有记录的项再取明细 → 股东、分支机构、上市信息。平台是 MCP 协议，实际就是 `POST https://agent.qcc.com/mcp/<server>/stream` 的 JSON-RPC 请求。规矩：
- 0 条的项不调明细，算"查了，没有"；明细只给前几条时按风险扫描的总数算（`CompanyProfile.counts`）。
- 平台摘要里"排查安全，允许进入下一步"这类定性话，存档前删掉。
- 法定代表人、负责人、联系方式不存；自然人股东写成"自然人股东A"，申请人等是个人的写"自然人"。
- 积分：一家公司约 40 积分（股东 20、风险扫描 5、分支机构 5、工商信息 3……），平台对同一家公司每月最多扣 100；`XRAY_QCC_MAX_POINTS` 限制单次运行的总花费。结果按"公司 + 工具"缓存，不重复扣。
- 证据包里没有 `registry` 段（只摘了文书）时，登记信息照样从企查查取。
- 宣称上市的，对照上市信息里的交易所、股票代码。

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
