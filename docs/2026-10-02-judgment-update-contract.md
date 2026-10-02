# 判断更新：给后端（A）的契约增量说明

日期 2026-10-02 ｜ 分支 `feat/trackable-judgments` ｜ 主要由前端一侧提出，改动落在 `backend/app/models.py`

实现状态：`Basis`、`Judgment`、`JudgmentChange`、`ResolveIn` 和 `cleared` 已进入主线，`POST /api/cases/{id}/resolve` 已有后端实现与测试。判断页目前默认隐藏，前端地址带 `?judg=1` 才显示；此功能的界面行为仍需核对，不能把后端契约完成等同于界面已正式开放。

## 1. 为什么加这些字段

原来的「二次分析」是：新材料进来 → 重跑一遍 → 出一版新报告，两个版本的**报告条目**做 diff。
问题在于被保存的只有「报告长什么样」，没有「哪一条判断、靠什么依据、什么时候被推翻的」。
所以补材料只能让警告变多变少，不能把一条不成立的警告撤掉。

现在把**判断**当成一等实体存下来：一条判断 = 判断内容 + 适用范围 + 依据 + 前提 + 未知项 + 不能推出什么 + 状态 + 版本历史。
报告只是「某一版发布时，这些判断长什么样」。

三层在数据结构里分开，不靠提示词：

| 层 | 含义 | 谁能填 |
| --- | --- | --- |
| `said` 材料里写的 | 只代表文字读对了，不代表材料真实、账户归属已认证 | 材料提取 |
| `confirmed` 记录里查到的 | 登记、名单、年报这类可核来源 | 规则 + 官方数据 |
| `inferred` 系统据此推断的 | 规则推的，必须带 `premise` / `unknown` / `cannot` | 规则 |

## 2. 新增模型（`app/models.py`，**全部增量，没有改老字段的语义**）

```python
class Basis(BaseModel):            # 一条依据
    ref: str | None               # RawRecord id，点开能看原文
    label: str                    # 人话：合同草案 / 登记记录 / 付款截图
    quote: str | None             # 逐字原文
    locator: str | None           # 位置：第 6 条 / 收款户名那一行
    grade: BasisGrade = "official"  # official / user_material / web / demo
    as_of: str | None

class Judgment(BaseModel):
    id: str                       # 稳定 id，跨版本跟着走（见第 4 条）
    layer: Literal["said", "confirmed", "inferred"]
    layer_label: str
    text: str                     # 判断内容
    scope: str                    # 适用范围：哪家公司、哪次交易、哪份合同版本
    basis: list[Basis]
    premise: list[str]            # 前提：成立时才适用
    unknown: list[str]            # 未知项：还没得到证明的
    cannot: list[str]             # 不能直接推出什么
    state: Literal["holds", "needs_check", "unconfirmed", "revised", "clarified", "withdrawn"]
    state_label: str
    since: int                    # 第几版形成
    changed_at: int | None        # 第几版被修订 / 澄清 / 撤回
    plain: str
    dispute: list[str]            # 冲突：两边证据并列保留
    history: list[str]            # 「第 2 版起：需要核实；第 3 版：已澄清（某某：说明）」
    target: str | None            # 对应报告条目 id

class JudgmentChange(BaseModel):  # 判断级的变化
    target: str                   # 判断 id
    label: str
    kind: Literal["same", "found", "recheck", "unconfirmed", "next_question", "dropped", "cleared"]
    text: str
    before: str | None
    after: str | None
    because: list[str]            # 触发这次变化的新材料 RawRecord id
    basis: list[Basis]
    plain: str

class ResolveIn(BaseModel):       # 人对一条判断下结论
    judgment_id: str
    action: Literal["clarified", "withdrawn", "recheck"] = "clarified"
    note: str = ""
    by: str = "用户"
```

`Version` 上加了三个可选字段：`judgments` / `judgment_changes` / `judgment_summary`。
`Version.trigger` 的 Literal 加了 `"resolve"`，`TRIGGER_LABELS` 加了 `"resolve": "核实结论"`。
`Change` / `change_summary` 全部保留不动，老前端不受影响。

## 3. 新增端点

`POST /api/cases/{case_id}/resolve`，body 是 `ResolveIn`，返回整个 `Case`（和 supplements 一样）。
不存在这条判断 → 404。做的事：复制上一版 → `trigger="resolve"` → 改这条判断的 state / state_label / history /
plain → **报告那一头对应的断言也改写**（前缀「第 N 版：这条已澄清（某某：说明）。原来的核验结论是：…」）
→ 出一版新案卷，旧版留着。

理由：只改判断不改报告，用户看到的就是「它只会加警告，不会撤警告」。
如果是 `clarified` / `withdrawn`，这条判断原来挂着的 `unknown` 会清空并记进 `history`（「不再挂着这些待核的事：…（由某某核实）」）；
`recheck` 不清空，还得挂着。

## 4. 判断 id 跟内容走，不跟位置编号

- `said.<断言 id>`、`record.<信号 key>`、`check.<断言 id>`、`key.<场景关键事项>`、`ask.<sha1(问题原文)>`
- 问题的编号 Q1/Q2 会随问题增减整体挪位，所以 `ask` 的 id 用问题原文算 sha1。
  否则加一条问题，旧判断会全被认成「变了」，一次冒出三条假变化。
- 比较两版是否同一条判断时，指纹**不含 `basis.ref`**：报告条目挪位置不算判断变了。

## 5. 变化清单的档位

五格：`保持不变 / 新增发现 / 需要重新核实 / 尚不能确认 / 下一步问题`，另加 `不再出现`。
新增 `cleared`（「已经澄清」）：有人核实过、警告撤了。单独一档，免得和「没变」混在一起。

## 6. 新材料不会自动覆盖旧材料

`attach_disputes()`：材料说的和记录里查到的对不上时，两边都留着 ——「材料可能是真的，也可能是印错了或者被改过；
记录也可能还没更新。不以后交的材料为准。」不让最后上传的文件「获胜」。

## 7. 自测（真实跑过）

- `pytest -q` → **121 passed**（基线 104，新增 17 条在 `tests/test_judgments.py`）
- 端到端真跑（API 建案卷，不是 fixture）：
  - v1（需求：这家公司让我先交 5800 元才能入职）→ 12 条判断
  - v2（补一张收款户名「张某」的付款截图）→ 新增发现 1 / 需要重新核实 1 / 尚不能确认 3 / 下一步问题 1 / 其余 12 条保持不变
  - v3（对 `check.A7` 下 `clarified`）→ 已经澄清 1，报告 A7 那条提醒跟着改写，判断 history 留两行
- 没有出现「风险等级从低变高」，也没有推出「账户真实属于张某 / 违法收款 / 这是诈骗」这些说法。

## 8. 原待确认事项（现状）

1. 字段已加入 `models.py` 并由主线使用，不再等待契约确认。
2. `/resolve` 使用 `ResolveIn`，由 FastAPI 生成 OpenAPI 描述；当前和 supplements 一样没有用户鉴权。若以后公网部署，访问控制应作为部署任务处理。
