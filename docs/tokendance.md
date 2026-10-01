# Tokendance 网关能力与验证记录

当前文本和视觉模型均配置为 `qwen3.8-max`。公开模型目录确认了该精确模型 id 和原生视觉能力，但本机使用所提供 Key 的文本、JSON、视觉探针都遭到鉴权拒绝，因此目前不能声称模型已接通、JSON 输出可用或 OCR 成功。下文保留上游使用其他模型的历史实测，不能将其当作当前模型、Key 或配置的验收结果。

## 当前配置的验证结果

- 测试时间：2026-10-02 05:34（中国时间；2026-10-01T21:34Z）。
- 网关：`https://tokendance.space/gateway/v1`，程序追加 `/chat/completions`。
- 文本模型和视觉模型：`qwen3.8-max`，没有自动换用其他模型。
- 三项探针均只发送内置合成输入，均因鉴权失败结束。随后一次安全诊断确认 HTTP 401，错误为 `unauthorized` / `API密钥不存在`。

| 能力 | 当前状态 | 已验证与未验证 |
| --- | --- | --- |
| 中文文本 | 鉴权失败，未接通 | HTTP 适配、鉴权错误和断网处理通过离线测试；当前模型的真实中文响应未验证 |
| JSON 输出 | 鉴权失败，未验证 | Pydantic 校验、每次结构化生成的一次修复、成功录制和离线回放通过测试；当前网关 JSON 输出未验证 |
| 图片识别 | 鉴权失败，未验证 | 模型公开信息支持原生视觉；图片内容验证、视觉消息格式、失败提示已测试；当前 OCR 准确性未验证 |
| 搜索 | 独立协议已确认 | 上游 `app/sources/web.py` 已实现实际搜索；B 的模型探针及 `LLM.search` 未接该适配器，本次未重新做在线搜索验收 |
| 网页阅读 | 独立协议已确认 | UniFuncs 阅读协议已确认；B 的模型探针及 `LLM.read_url` 尚未接入，本次未重新做在线阅读验收 |

公开依据：[模型目录](https://tokendance.space/gateway/v1/models)、[qwen3.8-max 模型信息](https://tokendance.space/portal/api/models/qwen3.8-max)、[OpenAI Chat Completions 协议](https://tokendance.space/docs/protocol-openai-chat-completions.md)、[官方文档索引](https://tokendance.space/llms.txt)。公开文档没有明确承诺 `response_format: {"type":"json_object"}`，所以当前保守设置 `TOKENDANCE_JSON_MODE=0`；仍使用提示词约束和服务端 JSON 校验，取得有效 Key 后再实测该参数。

首次仅检查配置的旧探针曾返回 `configured=false/status=not_tested`；这一历史状态已被本次“已配置但鉴权失败”的结果取代。单元测试中的 FakeLLM、MockTransport 和回放结果都不是在线能力证据。

## 上游历史实测（B1，未在当前配置复验）

以下为上游在 2026-10-02 凌晨记录的本机直连结果，使用当时比赛提供的 Key；原记录称模型目录共 107 个，并可通过 `supported_protocols` 查看协议。这些记录用于保留集成依据，不代表当前推荐或已启用这些模型。

| 能力 | 上游记录的结果 | 当时使用的模型或接口 | 当时实测与限制 |
| --- | --- | --- | --- |
| 中文文本 | 成功 | `qwen3-max` | 约 2.3 秒，不带思考过程 |
| JSON 输出 | 成功 | `qwen3-max` | 约 2.2 秒，`response_format: json_object` 返回合法 JSON；当时 `TOKENDANCE_JSON_MODE=1`，不能据此推断 `qwen3.8-max` 支持情况 |
| 看图（宣传单照片） | 成功 | `qwen3-vl-plus` | 约 3.3 秒，记录称旋转 2 度的 10 行宣传单逐字读对；不是当前模型的 OCR 验收 |
| OCR（带坐标） | 成功 | `qwen3.5-ocr` 备用 | 约 4 秒，每行带坐标；`glm-ocr` 使用 `zai:layout-parsing` 协议，不走 chat |
| 联网搜索 | 成功，独立协议 | 博查 `POST /gateway/bocha/v1/web-search` | 约 1.7 秒；支持 `include` 指定域名，`summary=true` 返回摘要 |
| 联网搜索（备用） | 成功 | UniFuncs `POST /gateway/unifuncs/web-search` | 约 4–11 秒；不支持限定域名 |
| 网页阅读 | 成功但内容受限 | UniFuncs `POST /gateway/unifuncs/web-reader` | 约 4 秒；动态渲染页面可能只有外壳，金融监管总局详情页当时只读到版权声明 |
| 工具调用 | 未测 | — | 主流程不依赖模型决定是否搜索，搜索由后端调用 |

上游还记录了以下发现，当前未重新验证：

- `deepseek-v4-flash`、`glm-5.3-flash`、`qwen3.8-flash` 会返回 `reasoning_content`，耗时较长，其中 glm 约 25 秒，不适合当时演示的实时问答。
- 博查的 `include` 应写具体域名：当时写 `gov.cn` 只搜到中国政府网一个站。代码采用监管、法院、浙江和杭州政府网站列表，见 `backend/app/sources/web.py`。
- 金融监管总局处罚详情页背后有公开数据文件：`/cn/static/data/DocInfo/SelectByDocId/data_docId=<id>.json`。当时没有验证码，读取比网页阅读更可靠。
- 深度研究模型 `unifuncs-u3`、`unifuncs-s3` 兼容 chat，但一次运行很多轮，当时未接入演示实时调用。

## 在代码里怎么用

| 用途 | 位置 | 失败时 |
| --- | --- | --- |
| 识别需求（场景、关注点、金额） | `app/intake.py` | 退回关键词规则 |
| AI 助手 | `app/assistant.py` | 越界回答最多要求改写两次，每次仍检查引用与事实一致性；网关不可用或仍越界时退回模板 |
| 读图片材料 | `app/readers.py` | 提示用户手动粘贴，并要求核对原图中的金额、账号和姓名 |
| 联网查证（政府网站文件、公开报道） | `app/sources/web.py` | 回放已录制的搜索结果；没有录制则记“查询失败” |

实际搜索与 `LLM.search` / `LLM.read_url` 的不可用占位接口是不同路径，不需要为了 B 再复制一份实时搜索适配器，也不能把占位接口的 `unavailable` 当成“查询成功、没有负面”。

成功结果的本地录制保存在被 Git 忽略的 `backend/data/cache/`，可能包含材料内容，不应提交。离线演示前需使用有效凭据完整走过演示路径，再设置 `XRAY_LLM_MODE=replay`；仅有配置或鉴权失败不会产生可用的成功录制。

## 本机配置

在被 Git 忽略的 `backend/.env` 中填写 Key，不将凭据写进文档或提交：

```dotenv
TOKENDANCE_BASE_URL=https://tokendance.space/gateway/v1
TOKENDANCE_API_KEY=
TOKENDANCE_MODEL=qwen3.8-max
TOKENDANCE_VISION_MODEL=qwen3.8-max
TOKENDANCE_JSON_MODE=0
TOKENDANCE_TIMEOUT=45
XRAY_LLM_MODE=live
```

`TOKENDANCE_API_KEY` 的空值仅是文档占位。本机已配置所提供的 Key，但当前被网关拒绝；需要有效凭据后才能继续真实能力验收。仅使用比赛确认的网关，勿把 Key 发给同名网站。

## 探针命令与后续验收

在 `backend` 目录执行。默认不加 `--live` 不联网：

```powershell
.\.venv\Scripts\python.exe -m tools.probe_tokendance --capability text
```

配置有效 Key 后，文本、JSON、视觉在线探针会请求比赛网关，可能消耗额度；只发送内置合成输入：

```powershell
.\.venv\Scripts\python.exe -m tools.probe_tokendance --capability text --live
.\.venv\Scripts\python.exe -m tools.probe_tokendance --capability json --live
.\.venv\Scripts\python.exe -m tools.probe_tokendance --capability vision --live
```

结果只输出状态、时间和安全错误代码，不打印 Key 或完整模型内容。`tested` 表示本次在线返回符合探针预期；`replay_only` 不算真实连通；`content_mismatch` 表示请求返回但内容不符合测试；`blocked_config` 是缺少配置。

`--capability search --live` 和 `--capability reader --live` 当前不会调用实际检索服务，返回兼容状态码 `blocked_protocol`。这里表示该模型探针尚未接入搜索/阅读适配器，不能解释为官方协议未知。实际搜索应沿 `app/sources/web.py` 的已实现路径验收。

视觉探针使用生成的 `PENGUIN 123` 图片，只验证基本多模态通路。真实宣传单中文、账号与金额仍需用无私人信息的材料测试并人工对照。后续记录每项测试的时间、模型、状态、安全错误代码、JSON 模式和视觉人工核对结果，不记录 Key、完整账户、私人合同或聊天截图。
