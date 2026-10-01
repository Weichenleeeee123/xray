# 企鹅后端 B 接入说明

B 的模型调用、材料读取、案卷问答和需求识别已在现有 FastAPI 接口下通过本地测试。本次还集成了上游主线的共享模型、规则、数据与前端更新；B 的增强继续通过既有接口接入。下面说明如何运行、前端怎样引用旧版报告，以及哪些增强仍需要 A 显式接入。

## 运行与配置

B 开发基线为 Git 提交 `34a3406`，本地实现提交为 `59fdf2d`，交付快照已集成上游主线 `29d80ae`。发布分支为 `codex/penguin-backend-b`；通过 GitHub 连接发布时提交元数据可能不同，本地历史保留备份。使用 Python 3.11 以上，本机测试环境为 Python 3.12.14。

在仓库的 `backend` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-b.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

其他机器先创建自己的虚拟环境。不要复制本机 `.venv`，其解释器路径不可跨机器复用。`requirements-b.txt` 包含共享 `requirements.txt` 和图片验证所需的 Pillow，新机器应使用上述 B 依赖入口。将 `.env.example` 的配置写入本机 `backend/.env`，不要提交 Key。当前文本与视觉模型均为 `qwen3.8-max`，`TOKENDANCE_JSON_MODE=0`。探针命令和真实测试状态见 [Tokendance 能力验证](tokendance.md)。

当前工作进入推送与 PR 交接阶段；本文不表示远端分支或 PR 已创建，也未进行公网部署。本机已配置所提供的比赛 Key，但 2026-10-02 05:34（中国时间）的文本、JSON、视觉合成探针均鉴权失败，安全诊断为 HTTP 401 / `unauthorized` / `API密钥不存在`，因此真实模型仍未接通。公开资料确认了模型 id 和原生视觉能力，但没有明确承诺 `response_format: json_object`，需有效凭据后继续验收。

## 已接入的接口

| HTTP 接口 | B 的服务入口 | 行为 |
| --- | --- | --- |
| POST `/api/intake` | `run_intake(need, llm, scenario=None, company=None)` | 模型识别场景与关注点；失败退回 A 的关键词规则；金额和替谁看以需求原文中的确定性识别为准 |
| POST `/api/read` | `read_upload(filename, data, llm)` | 图片先验证实际文件内容，再发视觉模型；文本、PDF、DOCX 本地读取；失败提示手动录入 |
| POST `/api/cases/{id}/chat` | `answer(case, q, llm, *, version_no=None, max_context_chars=120000)` | 只读指定版本及其原始数据；回答经引用校验；由现有 A 路由保存聊天，不生成新版报告 |
| GET `/api/health` | `llm.status()` | 显示配置是否完整、模式、模型、网关主机和录制数量，不返回 Key |

新建案卷和修改需求的既有路径也会调用 `run_intake`，不必另造接口。没有配置模型时，规则分析、材料本地解析、模板问答仍可运行；这不代表真实模型已接通。

现有共享 Intake 只区分 keywords/model/user，没有单独的 replay 字段；因此需求识别的回放仍映射为 method=model。A 若要在需求预览里明确标注回放时间，需要扩展该契约。问答和详细 OCR 结果已保留回放模式与时间。

## 助手引用约定

当前版继续支持原接口格式：

```json
{"text":"为什么这条重要？","refs":["A1"]}
```

为了避免看 v1、却问到 v2，前端在查看旧报告时应传带版本的引用：

```json
{"text":"为什么这条重要？","refs":["v:1:assertion:A1"]}
```

可用格式：

- `v:1:assertion:A1`：第 1 版说法。
- `v:1:signal:risk:bank_list`：第 1 版风险卡里的持牌名单条目。
- `v:1:missing:M1`、`v:1:question:Q1`：第 1 版缺项或待问问题。
- `raw:R9` 或 `R9`：当前所选版本使用的原始记录。

一个问题只能引用一个版本；混用版本、版本不存在、条目不存在，均返回 `mode="guard"` 和重新选择提示，不静默忽略。服务内部调用也可直接传 `version_no=1`。返回的 `ChatMessage.version` 指定版本，`citations` 保持原来的 `A1/R9/risk.bank_list` 格式；前端跳转时必须结合 version，不能只按裸 A1 定位。

每个模型事实段独立检查。假 id、对不上的逐字引文、无出处的事实段，以及能检测到的数值或判定冲突会被剔除，不只是删脚注。判定与信号/检查状态对照独立的权威规则字段，不能靠引用另一份材料里的“与记录相符”覆盖当前判定。全部被剔除时返回 `not_found=true` 和补充材料建议。来源目录的 `registry` 等 id 不是原始记录，不能当作事实出处。

这些检查只能保证引用可追溯及部分一致性，不能证明任意解释的语义都正确。用户材料的原话也不等于事实，界面须保留来源类别、日期和演示标记。助手的文字和引文应按纯文本或安全 Markdown 渲染，不使用未经清理的 `innerHTML`。

## 材料读取细节

`read_upload` 仍返回共享 `models.ReadResult` 的 `text/method/note`。部分 PDF 页未读出时，已成功页保留，note 明确列出未读页并要求补充；扫描件、加密失败、坏文件和空内容不会标成成功。

需要逐页状态时可使用 B 的内部服务：

```python
from app.readers import read_material

result = read_material(
    file_bytes,
    filename="contract.pdf",
    content_type="application/pdf",
    gateway=llm,
)
# result.status: ready / partial / needs_manual / failed
# result.pages: page_number, text, status
```

保护值可通过参数覆盖：10 MiB、PDF 50 页、图片 2000 万像素。超过限制整份拒绝，不静默截断。图片扩展名、实际格式及传入 MIME 不一致时拒绝；多帧图片要求拆分。DOCX 限制 XML 大小与解压比例，禁用声明式实体。

现有 A 上传路由另有限制 15 MiB，所以当前 10–15 MiB 文件会得到 B 的“超过读取上限”结果。该路由是 async，但同步调用 PDF/模型读取；A 下一步宜用线程池调用 `read_upload`，限制 `UploadFile.read` 的读取字节数，并把实际 `content_type` 传给详细读取服务。B 未越界修改此路由。

模型 OCR 仅是识别，不保证准确；必须显示“请对照原图核对金额、账号和姓名”。回放 OCR 会带录制时间，不能显示成刚刚在线识别。

## 缓存与回放

沿用 `XRAY_LLM_MODE=live/replay/off`：live 请求网关并录制成功结果，网络故障时尝试明确标注的回放；replay 只读录制，不联网；off 关闭模型。401/403 直接报告鉴权问题，不重试。每次结构化生成的 JSON 格式最多修复一次，两次均不合格则退回调用方模板。

助手同时保留上游的越界改写机制：初次回答后最多改写两次，每次回答与改写都执行 B 的引用和事实一致性检查。越界改写与 JSON 修复是两层独立限制，最坏情况下三次结构化生成各发两次请求，共六次 HTTP 调用；并非整个问答最多请求两次。

录制键包含模型、网关地址、输入、Schema、温度和任务 namespace。问答和改写额外包含案卷 id 与版本，不能用别的案卷录制凑答案。修复后的有效结果保存到原请求键。格式 v2 不复用初版旧录制，需要在当前版本重新录制演示。

默认录制目录仍是被忽略的 `backend/data/cache/`。录制可能包含材料内容，属于敏感本地数据，不要提交或公开提供静态访问；不需要录制时构造 `LLM(cache_dir=None)`。该缓存不是加密保险箱，也不是防篡改证据。离线演示使用已保存的同一案卷，不要新建案卷后期待旧录制跨案卷命中。

## 需要 A 显式接入的增强

以下服务有测试，但没有自动改动 A 的分析流水线。

```python
from app.assistant import classify_reply, rewrite_report
from app.llm import LLMExtractor

# 只返回解释文案映射；不返回被替换的报告或判定。
wording = rewrite_report(case, gateway=llm)
# wording.explanations: A2 / change:A7 / onepager.found.0 → 文案
# 未通过检查的项保留 A 原模板；检查 warnings，保留 mode/recorded_at。

# 只判断“是否回答问题”，不验证回复真假。
reply_info = classify_reply("许可证编号是什么？", "编号123456", gateway=llm)
# pending_identifiers 仅为待查编号，requires_verification 始终为 True。

# 由 A 决定是否打开补充抽取；先保留 RuleExtractor 的全部结果。
svc.extractor = LLMExtractor(llm)
```

报告改写采用可选文案覆盖层。规则判定、金额、引用和版本对象不被改写；变化原因的引文还必须来自该变化 `because` 指定的新材料。模型补抽必须逐字引用原文；影响规则的数字、关键词和机构名仍要经过确定性抽取验证，不接受模型直接提供判定。

`llm.search` 和 `llm.read_url` 目前仍是明确的不可用状态接口，不会联网，也不会把模型记忆当搜索结果。博查 `/gateway/bocha/v1/web-search` 与 UniFuncs 搜索/阅读的独立协议已确认；上游 `app/sources/web.py` 已实现实际搜索，这是另一条服务路径，不需要为 B 重复实现。B 模型探针的搜索/阅读返回 `blocked_protocol`，表示该探针尚未接适配器，不代表官方协议未知。不要把占位接口的 `unavailable` 当作“查询成功、没有负面”。

## 验证和下一步

执行过原有测试以及新增 B 测试，覆盖缓存损坏、修复回放、假引用、旧版选择、聊天不写案卷、PDF 部分页、坏图片、需求金额和现有 HTTP 路由。所有样本均为合成测试资料，不是对真实公司的评价。

合并上游后的本地结果：`python -m pytest -q` 为 **145 passed**（此前 B 独立版本为 132 passed），有一个上游 Starlette/httpx 弃用警告。此前 B 的 `git diff --check` 和 Python 编译检查通过；提交前仍应检查最终集成差异。独立审查提出的三个重要问题已用失败测试复现并修复，另补了分段假引文测试。真实 HTTP 回环测试也跑通了虚构案例 C 的 v1 → 问答 → 补充材料 → v2；没有把这次模型关闭的测试算作 AI 连通验收。

仍需完成：取得有效 Key 后复验当前 `qwen3.8-max` 的文本、JSON、视觉能力，并沿实际服务路径复验搜索/阅读；真实宣传单 OCR 人工核对；A 选择并接入 `rewrite_report`、`classify_reply`、`LLMExtractor` 等 P1 服务；F 按 version 定位引用；浏览器端完整演示及学校网络断网演练。上游旧模型的成功记录见能力文档，不能替代当前配置验收。没有进行公网部署；公开部署前由 A 加访问控制与用量保护。
