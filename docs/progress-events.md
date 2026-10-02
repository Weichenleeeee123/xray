# 等待动画的进度事件

给"小企研究室"等待动画用：后端每走完一步，就发一条带真实结果的事件，动画跟着事件走。

## 1 原则（动画也要守）

- **只演真的。** 小企走到哪个位置、盖什么章，都由事件决定，不按定时器演。没有总进度百分比，一共要多久事先不知道。
- **每一步都有结果。** 开头的 `begin` 列出这次要走的步骤，每一步都会先来 `start` 再来 `done`，各一次，按列出的顺序，中间不插别的步骤。没走的步骤也有 `done`，写明为什么没走，比如"没联网搜：虚构的演示公司"。
- **"没查"要演出来。** `not_covered` 不是失败，是我们承认这一块没查。建议演成：小企走过去，抽屉是空的，耸耸肩，盖灰色虚线章"没查"。
- **章上的字只说查没查到、查到几条，不下结论。** 好坏由报告里的规则说。动画里不要出现分数、仪表盘、红绿灯评级、"安全""有风险"这类字，也不要把公司画成反派。
- **数字只用事件里给的。** 不要写"27 篇公开资料"这类编出来的数。

## 2 接口

| 方法 | 路径 | 请求体 | 用途 |
|---|---|---|---|
| POST | `/api/cases/stream` | 同 `/api/cases`（`company_name`、`need`……） | 建案卷 |
| POST | `/api/cases/{id}/supplements/stream` | 同 `/supplements`（`kind`、`text`……） | 补充信息、改需求 |

- 返回 `application/x-ndjson`：一行一个 JSON。最后一行是 `case`（整个案卷，和 `GET /api/cases/{id}` 一样）或 `error`。
- 请求体不合格（422）、案卷不存在（404），照常回 HTTP 错误，不开流。
- 开流以后出错，最后一行是 `{"type":"error","status":500,"message":"…"}`，message 可以直接给用户看。
- 客户端中途断开，后端照样做完、存好案卷。
- 原来不带 `/stream` 的两个接口不变。

### 2.1 刷新后接着看：任务接口

流式接口断了就接不回来。要能刷新页面、复制链接接着看，用任务接口：后端把同样的事件一条条记到 `data/runs/<任务编号>.ndjson`（git 忽略），前端按编号轮询。

| 方法 | 路径 | 返回 | 用途 |
|---|---|---|---|
| POST | `/api/runs` | `202 {"run_id":"…24 位十六进制…","status":"running"}` | 建案卷（请求体同 `/api/cases`） |
| POST | `/api/cases/{id}/runs` | 同上 | 补充信息（请求体同 `/supplements`） |
| GET | `/api/runs/{run_id}?after=n` | `{"status","case_id","events":[第 n 条以后],"next"}` | 取进度；`next` 作为下次的 `after` |

- `status`：`running` 还在跑；`complete` 跑完了，`case_id` 是案卷编号，再 `GET /api/cases/{case_id}` 取报告；`error` 出错；`interrupted` 后端中途重启过，这次没跑完，要重新查。
- `events` 里是和流式接口一样的 `begin`、`step`，最后一条是 `{"type":"complete","case_id":…}` 或 `{"type":"error","message":…}`。日志里不存案卷本身。
- 编号放在页面地址里（研究室用 `?run=…`）。刷新时拿同一个编号从 `after=0` 重新取，不会再提交一次查询。
- 没有暂停、取消：页面关掉，后端照样跑完、存好案卷。

## 3 事件

每条都带 `t`：从收到请求起的秒数。

```jsonc
{"type":"begin","kind":"create","company":"杭州巨鲸财富管理有限公司","t":0.0,
 "steps":[{"id":"intake","label":"读懂需求","lookup":false},{"id":"lists","label":"持牌名单","lookup":true}, ...]}
{"type":"step","id":"intake","label":"读懂需求","phase":"start","t":0.0}
{"type":"step","id":"intake","label":"读懂需求","phase":"done","coverage":null,"counts":null,
 "text":"识别为：存钱 / 理财 / 投资，20 万，替妈妈看","t":1.96}
{"type":"step","id":"lists","label":"持牌名单","phase":"done","coverage":"not_found",
 "counts":{"found":0,"not_found":4,"not_covered":0,"failed":0},"text":"查了 4 份名单，都没有它","t":1.96}
...
{"type":"case","case":{...整个案卷...},"t":36.33}
```

- `kind`：`create` 建案卷 / `supplement` 补充信息。
- `lookup`：`true` 是查资料的步骤，`done` 带 `coverage` 和 `counts`；`false` 是处理步骤（读需求、对照规则、写短句），这两项是 `null`。
- `coverage`：这一步的总结果。报告里用的是同样四种：

| coverage | 意思 | 建议的章 |
|---|---|---|
| `found` | 查到了 | 实心章"查到" |
| `not_found` | 查了，没有 | 空心章"查了没有" |
| `not_covered` | 没查（没有数据源，或这次不查） | 灰色虚线章"没查" |
| `failed` | 查了但没查成（网络、接口出错） | 断线章"没查成" |

- `counts`：这一步每种结果各几条原始记录。
- `text`：一句话的结果，可以直接写在章旁边。

## 4 步骤、实测耗时和建议位置

顺序固定。补充材料时没有 `intake`；改需求时有。

| id | 名字 | 查什么 | 实测耗时（2026-10-02，联网） | 建议房间位置和动作 |
|---|---|---|---|---|
| `intake` | 读懂需求 | 模型识别场景、金额、替谁看 | 1.4–2 秒 | 门口来访的鹅递来需求和宣传单 |
| `lists` | 持牌名单 | 银行业、保险、期货、支付 4 份官方名单 | 不到 0.01 秒 | 左上档案柜，一口气拉开四个抽屉 |
| `amac` | 中基协私募登记 | 中基协名单 + 公示详情页 | 0–2.2 秒（登记了才取详情页） | 右侧数据终端，敲键盘 |
| `registry` | 工商登记 | 证据包或企查查商业数据；企查查查到了再取实控人、许可资质、变更、开庭立案、劳动仲裁、招聘 | 首次查企查查 15–30 秒；有缓存约 0 秒 | 数据终端（或档案柜），翻文件夹 |
| `finance` | 财务数据 | 企查查财务数据（上市、发债等公开财报的公司才有）；上市公司再到巨潮资讯网取年报原文和最近一年公告 | 首次约 2–16 秒（巨潮翻页）；一天内有缓存约 0 秒 | 数据终端，看报表 |
| `pack` | 人工摘录的文书 | 项目组从官网摘的处罚、监管文书、年报 | 约 0 秒 | 左侧书架，翻书 |
| `web` | 政府网站 | 联网搜索监管、法院、政府网站 | 1.5–2 秒 | 右上报刊架和软木板，放大镜、红笔圈 |
| `opinion` | 新闻舆情和网上投诉 | 企查查新闻舆情（带平台标的倾向）+ 联网搜"简称 + 投诉 维权 兑付" + 只搜权威媒体网站 | 3–8 秒 | 门口访客：查到了才开门进来讲，章上写"未核实" |
| `reviews` | 本站用户评价 | 别人在本站写的评价（未核实） | 约 0 秒 | 同上，和 `opinion` 一起算访客 |
| `rules` | 对照规则 | 说法逐条对记录 | 约 0.01 秒 | 回工位，把纸堆理齐 |
| `plain` | 写成短句 | 模型把长句缩短、补名词解释 | 7–9 秒 | 工位上打字 |

2026-10-02 晚上 `web` 拆成了 `web`（政府网站）和 `opinion`（新闻舆情 + 网上投诉），新增 `finance`。旧版前端没认识的步骤会落到默认位置，不会报错，因为 `begin` 里列出了全部步骤。

实测总时长（拆分之前测的；拆分后 A 约 13 秒、B 约 11 秒，企查查有缓存）：

| 情况 | 巨鲸 | 杭州银行 | 满盈禾（虚构，不联网） |
|---|---|---|---|
| 第 1 版，企查查首次查 | 36 秒（企查查 20、写短句 9） | 20 秒（企查查 9、写短句 7.5） | — |
| 第 1 版，企查查有缓存 | 13 秒（写短句 8.5） | 7 秒 | 9 秒 |
| 补材料出第 2 版 | 13 秒 | — | — |

演示前先把要演的公司各查一遍，让企查查结果进缓存；现场再查就不扣积分，也快很多。

## 5 编排建议

- **快的步骤合成一趟。** 不到 0.3 秒的几步连着来，小企一趟走完，章依次盖下去，每个章至少停 0.25 秒，让人看得见。
- **慢的步骤让动作循环。** 收到 `start` 就走过去开始动作，一直循环到 `done` 到达。不设固定时长。
- **案卷到了就收尾。** 剩下还没演完的动作压缩到 0.8 秒内，然后跳转报告。不要为了演完让人干等。
- **不放假控件。** 不要百分比、倒计时、暂停、倍速、重播。可以显示"已用 N 秒 · 正在查：{label}"。
- **"减少动画"的设置。** 系统开了 `prefers-reduced-motion` 时，只盖章、不走路。
- **结尾和报告接上。** 报告顶部那行"汇集了 N 条记录：x 查到 · y 查了没有 · z 没查"，就是这些章的合计，可以让章飞过去。

## 6 前端读取示例（原生 JS）

```js
async function createWithProgress(body, onEvent) {
  const r = await fetch('/api/cases/stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);   // 422 / 404：没开流
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      const ev = JSON.parse(line);
      if (ev.type === 'case') return ev.case;
      if (ev.type === 'error') throw new Error(ev.message);
      onEvent(ev);                       // begin / step start / step done
    }
  }
  throw new Error('连接断了，没收到结果');  // 后端可能已经存好案卷：可以去"案卷"列表里找
}
```

## 7 测试

`backend/tests/test_progress.py` 覆盖：
- 每一步都按顺序先 start 后 done；
- 流里给的案卷就是存下的那份；
- 真实公司各步的结果；
- 结果文字里没有定性词；
- 补充信息的两种情况；
- 出错时流以 error 结束，不泄露内部异常；
- 普通接口不发事件。
