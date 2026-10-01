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

复制 `.env.example` 为 `.env`，填比赛 Tokendance 的地址、Key、模型名，Key 只保存在被 Git 忽略的本机 `.env`。当前地址为 `https://tokendance.space/gateway/v1`，文本与视觉均使用 `qwen3.8-max`，保守设置 `TOKENDANCE_JSON_MODE=0`。不填也能跑：助手退回模板回答，需求识别退回关键词，图片材料提示手动粘贴。

`XRAY_LLM_MODE`：`live` 调网关并把成功结果录进 `data/cache/`，网络故障时尝试明确标注的回放；`replay` 只回放（断网演示，界面会标"离线回放"）；`off` 不调模型。401/403 直接报告鉴权问题，不重试。

当前模型尚未接通：2026-10-02 05:34（中国时间）的文本、JSON、视觉探针均鉴权失败，诊断为 HTTP 401 / `API密钥不存在`。需要有效 Key 后继续验证，不能把上游旧模型的历史成功记录当作当前验收。详见 [Tokendance 能力记录](../docs/tokendance.md)；B 的版本引用、缓存与待接入服务见 [B 接入说明](../docs/backend-b-integration.md)。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 名单条数和日期、已有证据包、模型状态（不含 Key） |
| GET | `/api/scenarios` | 6 个场景模板 |
| POST | `/api/intake` | `{need}` → 场景、关注点、替谁看、金额（输入页预览用，用户可改） |
| POST | `/api/read` | 上传文件（txt / pdf / docx / 图片）→ 文字；读不出来返回 `failed` 和提示 |
| POST | `/api/cases` | 建案卷，生成第 1 版报告。`company_name`、`need`，可选 `scenario`、`for_whom`、`amount`、`material_text` |
| GET | `/api/cases`、`/api/cases/{id}` | 案卷列表；单个案卷（全部版本、原始数据、对话） |
| POST | `/api/cases/{id}/supplements` | 二次分析。`kind`：`material` 新材料 / `reply` 对方回复 / `need` 改需求；`text` 必填 |
| POST | `/api/cases/{id}/chat` | AI 助手。`text`，可选 `refs`（选中的条目 id） |
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
| 企业工商信息（商业） | 企查查或天眼查开放平台，配置了才用，来源标"商业数据" | 缓存在 `data/cache/commercial/` |
| 人工采集的真实记录（公示系统、中基协、投诉、公司自述） | **真实**，来源类型 `collected` | `data/evidence_packs/<公司全称>.json`，怎么填见该目录 README |
| 企业登记、年报、私募登记、投诉 | 演示，3 家公司全部虚构 | `data/fixtures/` |
| 演示用材料（宣传单、对方回复、协议节选） | 演示，虚构 | `data/fixtures/flyers/` |

每家公司都查五份官方名单（银行、保险、期货、支付、私募），每份各记一条原始数据。企业登记按顺序找：证据包 → 商业接口 → 演示数据，都没有就记"没查"。证券公司、公募基金名录还没接，名字像证券或基金公司的，资格一条判"无法核验"，不硬下结论。

配了模型网关后，每家公司还会联网查证（`app/sources/web.py`，虚构的演示公司不查）：
- 只搜监管、法院、政府网站，找点名它的处罚、监管措施、风险提示、法院文书。这类结果必须在摘要里有公司全称才保留，来源标"官方记录"。
- 全网搜"简称 + 投诉、维权、兑付"，归进口碑信号。只匹配上简称的，原始数据里标"可能是同名的别家"。
- 天眼查、企查查等商业数据网站的结果一律丢掉。分类靠关键词，不让模型判断。每次搜索都有缓存，断网时回放。网关实测见 [docs/tokendance.md](../docs/tokendance.md)。

商业接口只取基本工商信息，处罚、出质、被执行等字段它不给，报告里这些项显示"没查"，不显示"无"（`CompanyProfile.checked` 控制）。查回来的公司名和输入对不上时不采用。

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
