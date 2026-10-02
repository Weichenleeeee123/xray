# Tokendance 网关能力与验证记录

当前文本和视觉模型均为 `qwen3.8-max`，更新本机凭据后已通过真实网关验证。完整案卷问答的默认长思考会超过 45 秒读取超时；按确认方案设置 `TOKENDANCE_ENABLE_THINKING=0`，保留完整上下文、JSON Schema 校验、引用检查与确定性规则。没有更换模型或延长超时来绕过问题。

## 当前配置的验证结果

- 测试时间：2026-10-02 05:59–06:28（中国时间），修复后完整流程于 06:18 通过，集成上游报告短句更新后于 06:28 再次通过。
- 网关：`https://tokendance.space/gateway/v1`，程序追加 `/chat/completions`。
- 文本模型和视觉模型：`qwen3.8-max`，没有自动换用其他模型。
- 文本、JSON、视觉及完整问答仅发送合成材料；真实公司搜索单独通过实际检索服务路径验证，不代表对公司可靠性的结论。

| 能力 | 当前状态 | 已验证与未验证 |
| --- | --- | --- |
| 中文文本 | 在线成功 | 合成文本探针约 1.59 秒；修复后 `/api/intake` 返回 method=model、金额 200000，约 1.42 秒 |
| JSON 输出 | 在线成功 | 实测 `response_format: {"type":"json_object"}` 可用，独立探针约 2.86 秒；仍执行 Pydantic 校验，不把 JSON 模式当事实保障 |
| 图片识别 | 在线成功，限定合成样本 | `/api/read` 调用当前模型，约 1.97 秒；中文付款测试图片中的“企鹅演示有限公司”“张三”“200000”均识别正确，不是复杂真实合同的准确率评测 |
| 完整案卷问答 | 在线成功 | 虚构案例 C 的 v1 问答约 5.72 秒，mode=model、引用 A2/R9、not_found=false、无改写；v2 后查 v1 约 8.33 秒，仍指向第 1 版 |
| 回放与版本 | 通过 | 同一案卷及相同输入回放 mode=replay、带录制时间且答案一致；补充材料产生 v2 和 33 条变化；聊天不修改报告或原始数据 |
| 搜索 | 实际服务在线成功 | `WebClient.findings("杭州银行股份有限公司")` 返回 14 条官方结果、6 条新闻结果，无 errors、replay=false，约 0.56 秒；这些只是检索结果，不是可靠性认定 |
| 网页阅读 | 独立协议在线成功，未接 B 阅读接口 | UniFuncs 读取 Tokendance 文档索引，HTTP 200、2129 字符，约 5.91 秒；`LLM.read_url` 仍未接入，不能声称已具备端到端网页阅读 |

合并上游 `6f16f2d` 后的第二轮同场景验收：建案卷含短句生成 8.59 秒，v1 问答 7.74 秒，补充材料及短句生成 4.23 秒，v2 后查旧版 5.19 秒；短句与两次问答均为在线 model，问答引用 A2/R9。版本只读和同输入回放再次通过。最终完整测试为 177 passed，包含独立审查补充的短句录制案卷/版本隔离测试。

公开依据：[模型目录](https://tokendance.space/gateway/v1/models)、[qwen3.8-max 模型信息](https://tokendance.space/portal/api/models/qwen3.8-max)、[Chat Completions 协议](https://tokendance.space/docs/protocol-openai-chat-completions.md)、[官方文档索引](https://tokendance.space/llms.txt)。JSON 模式以本次真实请求验证为依据，当前设置 `TOKENDANCE_JSON_MODE=1`。

05:34 的旧凭据曾返回 HTTP 401 / `API密钥不存在`，现已由更新凭据后的在线结果取代。单元测试中的 FakeLLM、MockTransport 和回放结果本身都不是在线能力证据。完整验收采用进程内 FastAPI TestClient + 真实 Tokendance 请求，未执行浏览器端或公网部署验收；上述延迟是单次观测，不是 SLA。

## 长思考超时修复

同一完整问答上下文默认开启思考时，45 秒请求超时；流式诊断发现答案正文前持续返回 `reasoning_content`，一次诊断到 66.33 秒才开始正文、72.92 秒完成。仅关闭 JSON 模式不能解决。实验传入 `enable_thinking=false` 后约 6.66 秒完成；落地修复后的路由实测见上表。

[千问官方深度思考文档](https://www.alibabacloud.com/help/en/model-studio/deep-thinking) 说明该混合思考模型支持此开关；本次真实请求确认 Tokendance 透传有效。代码使用原始 HTTP JSON，因此参数放在请求顶层，不嵌套 SDK 的 `extra_body`。

`TOKENDANCE_ENABLE_THINKING` 在创建 LLM 实例时读取，修改后重启服务：

- 未设置或 `0`：发送布尔值 `false`，默认用于演示低延迟问答及图片读取。
- `1`：发送布尔值 `true`，显式开启长思考，可能再次超过当前 45 秒超时。
- 显式留空：不发送该参数，遵循提供方默认值，也可用于不支持该参数的兼容网关。
- 其他值：请求前报配置错误，不发送网络请求，也不回显配置值。

有效思考模式纳入录制键；不同模式不能互相回放。本次更新前的录制键不再命中，应重新录制需要离线演示的路径。关闭长思考不关闭引用、逐字引文、数字、规则状态或结构化输出校验，也不代表模型输出必然正确。

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
TOKENDANCE_JSON_MODE=1
TOKENDANCE_ENABLE_THINKING=0
TOKENDANCE_TIMEOUT=45
XRAY_LLM_MODE=live
```

`TOKENDANCE_API_KEY` 的空值仅是文档占位。本机凭据已通过上述验证，其他机器需独立配置有效凭据。仅使用比赛确认的网关，勿把 Key 发给同名网站。

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
