# X-Ray 后端

施工依据：[黑客松版 PRD](../docs/2026-10-02-xray-hackathon-prd.md)。主线：输入企业名和一句需求 → 汇集数据 → 四层报告 → AI 助手 → 补充信息后二次分析。

## 运行

```
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

- 前端：http://localhost:8000 （`web/` 建好之前会跳到接口文档）
- 接口文档：http://localhost:8000/docs
- 断网备用的静态演示：http://localhost:8000/demo/
- 测试：`.venv\Scripts\python -m pytest`（不连网、不需要 Key）
- 新机器：`python -m venv .venv`，再 `.venv\Scripts\pip install -r requirements.txt`

### 接模型

复制 `.env.example` 为 `.env`，填比赛 Tokendance 的地址、Key、模型名。不填也能跑：助手退回模板回答，需求识别退回关键词，图片材料提示手动粘贴。

`XRAY_LLM_MODE`：`live` 调网关并把每次响应录进 `data/cache/`，网关挂了自动回放；`replay` 只回放（断网演示，界面会标"离线回放"）；`off` 不调模型。

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
| 人工采集的真实记录（公示系统、中基协、投诉、公司自述） | **真实**，来源类型 `collected` | `data/evidence_packs/<公司全称>.json`，怎么填见该目录 README |
| 企业登记、年报、私募登记、投诉 | 演示，3 家公司全部虚构 | `data/fixtures/` |
| 演示用材料（宣传单、对方回复、协议节选） | 演示，虚构 | `data/fixtures/flyers/` |

查一家公司时先找证据包，再找演示数据，都没有就记"没查"。持牌名单只覆盖银行业金融机构，不含证券、基金、保险、私募，所以"没查到"不等于"没有牌照"。

更新持牌名单（金融监管总局发布新版 PDF 后）：

```
.venv\Scripts\python tools\build_license_index.py data\raw\<名单>.pdf <截至日期> <原文链接>
```

## 约定

- 结论全部来自 `app/analysis/verify.py`、`signals.py` 里的确定性规则，同样的输入永远得到同样的结论。模型只做四件事：认需求、读材料、说人话、答问题。
- 二次分析是全量重跑后由 `analysis/diff.py` 按 id 逐条比对，没变的也列出来。
- 助手的回答由程序校验：出处 id 必须在案卷里，引文必须在原文里逐字找得到，否则丢掉并计入 `dropped`。让助手"判定安全""忽略规则"的提问由程序直接拦下。
- 没数据写"没查"（`status: none`），不把没数据说成没问题，也不说成有问题。不打安全分，不下"诈骗"之类的定性。
- 场景只改排序和措辞，不改事实：加场景就是在 `app/scenarios/` 加一个 JSON。
