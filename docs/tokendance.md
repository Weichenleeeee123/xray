# Tokendance 网关能力实测（B1）

- 实测时间：2026-10-02 凌晨，用比赛发的 Key，从本机直连
- 地址：`https://tokendance.space/gateway/v1`（OpenAI 兼容），Key 放在 `backend/.env`，不进仓库
- 官方文档：<https://tokendance.space/llms.txt>，`/v1/models` 每个模型都写了 `supported_protocols`
- 模型目录共 107 个

## 结论

| 能力 | 结果 | 我们用的 | 实测 |
|---|---|---|---|
| 中文文本 | ✅ | `qwen3-max` | 约 2.3 秒，不带思考过程，回答干净 |
| JSON 输出 | ✅ 支持 `response_format: json_object` | `qwen3-max` | 约 2.2 秒，直接返回合法 JSON；`TOKENDANCE_JSON_MODE=1` |
| 看图（读宣传单照片） | ✅ | `qwen3-vl-plus` | 约 3.3 秒，10 行宣传单逐字读对（图片故意转了 2 度） |
| OCR（带坐标） | ✅ | `qwen3.5-ocr` 备用 | 约 4 秒，每行带坐标；`glm-ocr` 走的是 `zai:layout-parsing` 协议，不走 chat |
| 联网搜索 | ✅ 走独立协议，不走 chat | 博查 `POST /gateway/bocha/v1/web-search` | 约 1.7 秒；支持 `include` 只搜指定域名，`summary=true` 返回摘要 |
| 联网搜索（备用） | ✅ | UniFuncs `POST /gateway/unifuncs/web-search` | 约 4–11 秒；不支持限定域名 |
| 网页阅读 | ✅ 能用，但对前端动态渲染的页面只拿到外壳 | UniFuncs `POST /gateway/unifuncs/web-reader` | 约 4 秒；金融监管总局的详情页只读到版权声明 |
| 工具调用 | 没测 | — | 主流程不依赖：搜索由后端自己调，不让模型决定 |

其他发现：

- `deepseek-v4-flash`、`glm-5.3-flash`、`qwen3.8-flash` 会返回 `reasoning_content`，更慢（glm 用了 25 秒），不适合演示时的实时问答。
- 博查的 `include` 要写具体域名：写 `gov.cn` 只会搜中国政府网一个站。我们写的是监管、法院、浙江和杭州政府网站的列表（见 `backend/app/sources/web.py`）。
- 金融监管总局的处罚详情页背后有公开的数据文件：`/cn/static/data/DocInfo/SelectByDocId/data_docId=<id>.json`，没有验证码，比网页阅读更可靠。
- 深度研究模型（`unifuncs-u3`、`unifuncs-s3`）兼容 chat 协议，但一次要跑很多轮，不适合演示时的实时调用，没接。

## 在代码里怎么用

| 用途 | 位置 | 失败时 |
|---|---|---|
| 识别需求（场景、关注点、金额） | `app/intake.py` | 退回关键词规则 |
| AI 助手 | `app/assistant.py` | 退回模板回答；回答里出现"安全""可靠"之类的定性也退回模板 |
| 读图片材料 | `app/readers.py` | 提示用户手动粘贴 |
| 联网查证（政府网站文件、公开报道） | `app/sources/web.py` | 回放录下的搜索结果；没有录音就记"查询失败" |

所有调用都录在 `backend/data/cache/`（git 忽略）。断网演示前，把演示路径完整走一遍，然后设 `XRAY_LLM_MODE=replay`。
