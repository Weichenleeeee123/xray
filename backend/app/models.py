"""数据结构：前后端和三个人之间唯一的契约。改字段先在群里说。

一个案卷（Case）= 用户输入 + 原始数据（RawRecord）+ 若干版报告（Version）+ 助手对话（ChatMessage）。
报告里每条检查都有 source（指回 Source）和 ref（指回 RawRecord），前端据此点进原始数据。
"""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Coverage(StrEnum):
    found = "found"              # 查过，有记录
    not_found = "not_found"      # 查过，没有
    not_covered = "not_covered"  # 没查：数据源未覆盖，不代表没有
    failed = "failed"            # 查询失败


class Status(StrEnum):
    bad = "bad"    # 有问题
    warn = "warn"  # 要留意
    ok = "ok"      # 查过，没问题
    miss = "miss"  # 该有的没有
    none = "none"  # 没查


class ClaimKind(StrEnum):
    qualification = "qualification"    # 资格：正规理财、持牌……
    return_promise = "return_promise"  # 收益承诺：保本、年化 X%……
    partner = "partner"                # 合作机构：银行存管……
    background = "background"          # 背景：国资、央企、上市……
    capital = "capital"                # 注册资本
    scale = "scale"                    # 规模：门店、会员……
    payee = "payee"                    # 收款信息：户名、个人账户……
    refund = "refund"                  # 退款或退出承诺：随时可退、随时取出……
    upfront_fee = "upfront_fee"        # 先交钱：入职培训费、押金……


class Verdict(StrEnum):
    mismatch = "mismatch"
    redline = "redline"
    misleading = "misleading"
    attention = "attention"
    unverifiable = "unverifiable"
    consistent = "consistent"


# official 官方记录（程序直接取）；collected 人工采集的官方记录；commercial 商业数据（企查查等，第三方加工）
# user_review 用户评价：别人说的，未核实
SourceKind = Literal["official", "collected", "commercial", "regulation", "demo", "user_material", "web", "parameter",
                     "user_review"]

# 判断依据的级别：material 是用户给的材料（只代表文字读对了），其余是可核来源
BasisGrade = Literal["official", "collected", "commercial", "web", "material", "regulation", "parameter", "demo"]


class Source(BaseModel):
    id: str
    name: str
    kind: SourceKind
    as_of: str | None = None
    url: str | None = None
    note: str | None = None


# ---------- 企业记录 ----------

class Shareholder(BaseModel):
    name: str
    type: str
    pct: float


class Penalty(BaseModel):
    date: str
    org: str
    reason: str
    result: str


class Pledge(BaseModel):
    date: str
    pledgor: str
    share: str
    pledgee: str


class CompanyProfile(BaseModel):
    name: str
    code: str | None = None
    status: str
    founded: str
    reg_capital: float
    capital_currency: str = "人民币"
    paid_currency: str = "人民币"
    paid_capital: float | None = None   # 年报未公示时为 None
    capital_due: str | None = None
    scope: str
    shareholders: list[Shareholder] = Field(default_factory=list)
    insured: int | None = None          # 年报参保人数，企业可选择不公示
    branches: int | None = None
    penalties: list[Penalty] = Field(default_factory=list)
    pledges: list[Pledge] = Field(default_factory=list)
    mortgages: list[dict] = Field(default_factory=list)
    executions: list[dict] = Field(default_factory=list)
    tax_arrears: list[dict] = Field(default_factory=list)
    abnormal: bool = False
    serious_illegal: bool = False
    dishonest: bool = False
    restricted: bool = False            # 限制高消费
    listing: dict | None = None         # 上市信息（交易所、股票代码……）；查了没有是 None，要配合 known("listing") 看
    controller: list[dict] | None = None  # 实际控制人（企查查）：[{名称, 是自然人, 总持股比例, 表决权比例}]；个人只写"自然人"
    counts: dict[str, int] = Field(default_factory=dict)  # 数据源给的总条数；明细只取了前几条或没取到时，以它为准
    partial: list[str] = Field(default_factory=list)
    facts: dict[str, str] = Field(default_factory=dict)  # 失信、限高这类"有/无"项的一句话明细（日期、法院、金额）
    risk_scan: dict[str, int] | None = None  # 商业数据的风险扫描：各类风险各有几条（含没单列的终本案件、裁判文书……）
    # 实际查过的字段。None 表示全部查过（演示数据）；商业接口、证据包只给了部分字段时，
    # 没列出的字段显示"没查"，不能因为默认是空列表就说成"无"
    checked: list[str] | None = None

    def known(self, field: str) -> bool:
        return self.checked is None or field in self.checked

    def n(self, field: str) -> int:
        """某类记录有几条：数据源报了总数就用总数，否则数明细。"""
        rows = getattr(self, field)
        return max(self.counts.get(field, 0), len(rows) if isinstance(rows, list) else 0)


class LicenseRecord(BaseModel):
    name: str
    name_en: str
    code: str
    type: str
    regulator: str


class LicenseHit(BaseModel):
    query: str
    found: bool
    record: LicenseRecord | None = None
    suggestions: list[LicenseRecord] = Field(default_factory=list)
    source: str = "nfra_bank_list"
    count: int | None = None              # 名单总条数


class AmacHit(BaseModel):
    coverage: Coverage
    registered: bool | None = None
    source: str = "amac"
    record: dict | None = None            # 真实名单命中时：登记编号、在管基金数、是否有特别提示/诚信信息……
    as_of: str | None = None
    count: int | None = None              # 名单总条数


class RegistryHit(BaseModel):
    """在一份官方名单里查一个名字的结果（保险机构、期货公司、支付机构……）。"""
    registry: str                         # 名单 id，也是 Source id
    title: str
    query: str
    found: bool
    record: dict | None = None
    suggestions: list[str] = Field(default_factory=list)
    as_of: str | None = None
    count: int = 0


# ---------- 原始数据 ----------

class WebEvidence(BaseModel):
    """Discovery provenance, never a truth score or an input to risk counters."""
    canonical_url: str
    read_url: str | None = None
    content_hash: str = ""
    relation: Literal["direct", "linked", "possible"] = "possible"
    nature: Literal["self_description", "media", "review", "official_record", "discussion"] = "discussion"
    read_state: Literal["full", "partial", "snippet_only", "link_only", "failed"] = "snippet_only"
    published_at: str | None = None
    indexed_at: str | None = None
    updated_at: str | None = None
    paths: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    duplicate_group: str | None = None


class RawRecord(BaseModel):
    """每次取数据、每份用户材料都记一条。报告第四层就是这些记录。"""
    id: str                              # R1、R2……同一案卷内唯一
    source_id: str                       # 指回 Source
    title: str
    kind: Literal["official", "collected", "commercial", "user_material", "web", "demo", "user_review"]
    coverage: Coverage = Coverage.found
    retrieved_at: str
    as_of: str | None = None             # 数据本身的截止日期
    url: str | None = None
    content: dict | list | str | None = None  # 原文或字段
    screenshot: str | None = None
    note: str | None = None              # 例如"对方说的，未核实""手动录入"
    discovery: WebEvidence | None = None  # 旧案卷无此字段仍可读取；不进入风险规则输入


# ---------- 分析结果 ----------

# status 是 none（不知道）时，为什么不知道。"没查成"和"没查"要分开说，用户才知道该重试、该补材料，还是本来就不适用
Gap = Literal["failed",          # 查了，但查询出错（接口失败、积分用完、名字对不上……），重试可能就有
              "not_found",       # 查了，数据源里没有这家公司或这项记录
              "not_covered",     # 这次的数据源不含这一项
              "needs_input",     # 要用户补材料才能核对（比如理财产品登记编码要看宣传材料）
              "not_applicable",  # 对这家公司不适用（虚构的演示公司不联网搜索、币种不同不能比）
              "undisclosed",     # 企业自己没公开（年报未公示、非上市公司没有财报）
              "partial",         # 只拿到部分明细
              "reference",       # 查到了，但只作参考，不算结论（评价太少）
              "listed"]          # 已在上面的条目里单独列出，这里不重复算


class Check(BaseModel):
    label: str
    result: str
    status: Status
    source: str
    ref: str | None = None               # RawRecord id；法规、参数类来源没有
    gap: Gap | None = None               # status 是 none 时：为什么不知道


class Assertion(BaseModel):
    id: str
    kind: ClaimKind
    kind_label: str
    text: str
    quotes: list[str]
    verdict: Verdict
    verdict_label: str
    color: Literal["red", "amber", "grey", "green"]
    plain: str
    checks: list[Check]
    refs: list[str] = Field(default_factory=list)  # 说法出自哪些材料


class MissingItem(BaseModel):
    id: str
    text: str
    plain: str
    source: str
    refs: list[str] = Field(default_factory=list)


class SignalItem(BaseModel):
    key: str
    label: str
    value: str
    detail: str | None = None
    status: Status
    source: str
    ref: str | None = None
    gap: Gap | None = None               # status 是 none 时：为什么不知道


class Signal(BaseModel):
    key: Literal["risk", "finance", "credit", "reputation"]
    title: str
    lede: str
    flags: int
    items: list[SignalItem]
    extra: dict | None = None


class Term(BaseModel):
    """名词解释。人工写好的固定词表（app/glossary.json），报告标注和助手回答共用，不让模型现编。"""
    id: str                              # 助手引用时写作 term.<id>
    term: str
    aliases: list[str] = Field(default_factory=list)  # 报告里也按这些写法认出它
    plain: str                           # 它是什么
    why: str | None = None               # 对你意味着什么
    basis: str | None = None             # 依据：Source id
    law: str | None = None               # 依据：不在数据来源目录里的法规
    origin: Literal["glossary", "model"] = "glossary"  # model：报告生成时模型补的，词表里没有，标"AI 解释"


class ChartPoint(BaseModel):
    label: str
    value: float | None = None           # None = 没查：前端画成虚线框写"没查"，不画成 0
    display: str
    side: Literal["said", "record", "reference"] = "record"  # 它说的 / 记录里的 / 参考值
    ref: str | None = None               # RawRecord id
    source: str | None = None            # Source id


class TimelineEvent(BaseModel):
    date: str                            # YYYY-MM-DD 或 YYYY-MM
    label: str
    tone: Literal["bad", "warn", "neutral", "future"] = "neutral"
    ref: str | None = None
    item: str | None = None              # 点了跳到的报告条目


class Chart(BaseModel):
    """报告里的图。数据全部来自记录和规则，不经过模型（app/analysis/charts.py）。"""
    id: str                              # capital / return / scale / holders / complaints / timeline
    kind: Literal["compare", "share", "series", "timeline"]
    title: str
    note: str | None = None              # 一句话读图
    item: str | None = None              # 点图跳到的报告条目
    points: list[ChartPoint] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)


class Glance(BaseModel):
    """一眼看懂：报告生成时一并写好的短句。判定、颜色、排序全部来自规则，模型只把规则写的长句缩短。"""
    first: list[str] = Field(default_factory=list)        # 回答"第一问"的条目 id（这一版里有的）
    short: dict[str, str] = Field(default_factory=dict)   # 条目 id → 短句；没有的，前端用规则原句
    mode: Literal["model", "replay", "template"] = "template"
    dropped: int = 0                                      # 没通过程序校验、被丢掉的短句和名词


class Question(BaseModel):
    id: str
    ask: str                             # 该问对方的话
    why: str
    check_where: str                     # 拿到答案后去哪里查
    linked: list[str] = Field(default_factory=list)  # 关联的说法、信号条目 id


class Change(BaseModel):
    target: str                          # 说法 id（A1）、缺项 id（M1）或信号条目（risk.bank_list）
    label: str
    kind: Literal["new_concern", "worse", "clarified", "unchanged", "added", "removed", "updated", "unavailable"]
    before: str | None = None
    after: str | None = None
    because: list[str] = Field(default_factory=list)  # 新信息的 RawRecord id
    quote: str | None = None             # 新信息里的原文
    plain: str


class OnePagerLine(BaseModel):
    text: str
    refs: list[str] = Field(default_factory=list)


class OnePager(BaseModel):
    audience: Literal["family", "teller"]
    title: str
    subject: str
    headline: str
    found: list[OnePagerLine]            # 查到了什么
    mismatch: list[OnePagerLine]         # 哪里对不上
    unknown: list[OnePagerLine]          # 还不知道什么
    next_steps: list[OnePagerLine]       # 在下一步之前先确认这几件事
    footer: str


# ---------- 输入与案卷 ----------

class CaseIn(BaseModel):
    refresh_sources: bool = False
    model_config = ConfigDict(str_strip_whitespace=True)
    company_name: str = Field(min_length=2, max_length=80)
    need: str = Field("", max_length=4000)
    scenario: Literal["savings", "takeover", "job", "prepaid", "contract", "general"] | None = None
    for_whom: str | None = Field(None, max_length=80)
    amount: float | None = Field(None, gt=0, allow_inf_nan=False)
    material_text: str | None = Field(None, max_length=200000)
    material_title: str | None = Field(None, max_length=200)


class IntakeIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    need: str = Field("", max_length=4000)
    company_name: str | None = Field(None, min_length=2, max_length=80)


class Intake(BaseModel):
    scenario: str
    scenario_label: str
    focus: list[str]                      # 用户最担心的事，用人话写
    for_whom: str | None = None
    amount: float | None = None
    method: Literal["keywords", "model", "user"]
    matched: list[str] = Field(default_factory=list)  # 命中的关键词


class MustAsk(BaseModel):
    about: str                            # 说法类型（payee、refund……）或主题（equity、debts……），用来去重
    ask: str
    check_where: str


class Scenario(BaseModel):
    id: str
    label: str
    keywords: list[str]
    hand_over: str
    first_question: str
    first_items: list[str] = Field(default_factory=list)  # 回答"第一问"的条目 id（说法或信号条目），报告首屏用
    license_checks: list[str]
    claim_kinds: list[ClaimKind]
    signal_order: list[Literal["risk", "finance", "credit", "reputation"]]
    signal_ledes: dict[str, str] = Field(default_factory=dict)
    must_ask: list[MustAsk]
    onepager_title: str


TRIGGER_LABELS = {"initial": "首次分析", "material": "补充材料", "reply": "对方回复", "need": "修改需求",
                  "resolve": "核实结论", "reviews": "更新用户评价"}


# ---------- 可追踪的判断 ----------
#
# 报告只是"某一次发布时，这些判断长什么样"。真正被保存、被更新、被追踪的是判断本身。
# 三层必须分开，不能混着说：
#   said      材料里写了什么（只代表文字读对了，不代表材料真实、账户归属已认证）
#   confirmed 现实中确认了什么（登记、名单、年报这类可核来源）
#   inferred  系统据此推断出什么（规则推的，一定带 premise 和 unknown，并写明不能推出什么）


class Basis(BaseModel):
    """一条判断的依据：引用哪份材料的哪个位置，以及这份依据是哪一级。"""
    ref: str | None = None               # RawRecord id，点开看到原文
    label: str = ""                      # 人话：合同草案、登记记录、付款截图
    quote: str | None = None             # 逐字原文
    locator: str | None = None           # 位置：第 6 条、收款户名那一行、2025 年报
    grade: BasisGrade = "official"
    as_of: str | None = None             # 这份依据的日期


class Judgment(BaseModel):
    id: str                              # 稳定 id（said.A7 / record.risk.bank_list / ask.Q1），跨版本跟着走
    layer: Literal["said", "confirmed", "inferred"]
    layer_label: str
    text: str                            # 判断内容：到底在说什么
    scope: str                           # 适用范围：哪家公司、哪次交易、哪份合同版本
    basis: list[Basis] = Field(default_factory=list)      # 依据
    premise: list[str] = Field(default_factory=list)      # 前提：成立时才适用
    unknown: list[str] = Field(default_factory=list)      # 未知项：还没得到证明的
    cannot: list[str] = Field(default_factory=list)       # 不能直接推出什么
    state: Literal["holds", "needs_check", "unconfirmed", "revised", "clarified", "withdrawn"] = "holds"
    state_label: str = ""
    since: int = 1                       # 第几版形成
    changed_at: int | None = None        # 第几版被修订、澄清或撤回
    plain: str = ""                      # 人话
    dispute: list[str] = Field(default_factory=list)      # 冲突：两边证据并列保留，不让后交的材料赢
    history: list[str] = Field(default_factory=list)      # 版本与状态：什么时候形成、后来怎么被修订
    target: str | None = None            # 对应报告条目 id，点了跳过去


class JudgmentChange(BaseModel):
    """判断级的变化。五格：保持不变 / 新增发现 / 需要重新核实 / 尚不能确认 / 下一步问题（另加"不再出现"）。
    多出来的 cleared 是"这一条被人核实过、警告撤了"，单独一档，免得和"没变"混在一起。"""
    target: str                          # 判断 id
    label: str
    kind: Literal["same", "found", "recheck", "unconfirmed", "next_question", "dropped", "cleared"]
    text: str
    before: str | None = None
    after: str | None = None
    because: list[str] = Field(default_factory=list)      # 触发这次变化的新材料 RawRecord id
    basis: list[Basis] = Field(default_factory=list)
    plain: str = ""


class PrebuiltProvenance(BaseModel):
    """本版直接取自服务端预制包；缺少此字段不代表本版实时查询过。"""
    demo_id: str | None = None
    built_at: str | None = None          # 预制包生成时间，不是各来源的数据截止时间


class CompanyKeyword(BaseModel):
    label: str
    ref: str                            # 本版原始资料；前端可直接查看出处
    basis: str


class Version(BaseModel):
    no: int
    created_at: str
    prebuilt: PrebuiltProvenance | None = None
    trigger: Literal["initial", "material", "reply", "need", "resolve", "reviews"]
    trigger_label: str
    need: str
    for_whom: str | None = None
    amount: float | None = None
    scenario: str
    scenario_label: str
    focus: list[str]
    raw_ids: list[str]                    # 本版用到的原始数据
    sources: dict[str, Source] = Field(default_factory=dict)
    company: CompanyProfile | None
    company_keywords: list[CompanyKeyword] = Field(default_factory=list)
    license: LicenseHit
    amac: AmacHit
    assertions: list[Assertion]
    missing: list[MissingItem]
    signals: list[Signal]
    tally: dict[str, int]
    notes: list[str]
    questions: list[Question] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    change_summary: str | None = None
    judgments: list[Judgment] = Field(default_factory=list)              # 这一版里，一条条可追踪的判断
    judgment_changes: list[JudgmentChange] = Field(default_factory=list)  # 判断级的变化，五格
    judgment_summary: str | None = None
    onepager: OnePager | None = None
    glance: Glance | None = None          # 报告首屏的短句（app/plain.py）
    charts: list[Chart] = Field(default_factory=list)  # 报告里的图，全部来自记录和规则
    terms: list[Term] = Field(default_factory=list)  # 这一版报告里出现的名词及解释，随报告一起生成


class Quote(BaseModel):
    ref: str
    text: str


class ChatMessage(BaseModel):
    context_mode: Literal["full", "selective"] | None = None
    error_code: Literal["context_budget", "evidence_coverage"] | None = None
    request_id: str | None = None
    role: Literal["user", "assistant"]
    text: str
    refs: list[str] = Field(default_factory=list)       # 用户选中的报告条目
    citations: list[str] = Field(default_factory=list)  # 回答引用的条目或原始数据 id
    quotes: list[Quote] = Field(default_factory=list)   # 逐字校验过的原文
    suggest: list[str] = Field(default_factory=list)    # 建议补查或补充的材料
    not_found: bool = False                             # 数据里没有，回答"没查到"
    dropped: int = 0                                    # 被程序丢掉的出处或引文（编造的 id、对不上的原文）
    rewrites: int = 0                                   # 回答越界（定性、推测后果）后让模型重写的次数
    blocked: list[str] = Field(default_factory=list)    # 被程序拦下的越界说法
    version: int
    mode: Literal["model", "replay", "template", "guard"] | None = None
    recorded_at: str | None = None                      # 离线回放时，响应的录制时间
    created_at: str


class MaterialAnalysis(BaseModel):
    """A saved material appendix, separate from the company report's presentation."""
    id: str
    created_at: str
    kind: Literal["material", "reply"]
    title: str
    base_version: int
    report_version: int
    raw_ids: list[str]
    need: str
    summary: str
    findings: list[Assertion] = Field(default_factory=list)
    observations: list[Judgment] = Field(default_factory=list)
    changes: list[JudgmentChange] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)


class Case(BaseModel):
    owner_id: str | None = None          # 服务端分配；旧案卷无归属，不开放公共访问
    revision: int = 0
    id: str
    created_at: str
    case: CaseIn                          # 最新的输入
    scenario: str
    focus: list[str]
    current: int                          # 当前版本号
    versions: list[Version]
    material_analyses: list[MaterialAnalysis] = Field(default_factory=list)
    raw: list[RawRecord]
    chat: list[ChatMessage] = Field(default_factory=list)
    sources: dict[str, Source]


class CaseSummary(BaseModel):
    id: str
    created_at: str
    company_name: str
    need: str
    scenario_label: str
    versions: int


class PublicChatMessage(ChatMessage):
    """Public response DTO; full audit fields remain in server-side ChatMessage."""
    dropped: int = Field(0, exclude=True)
    rewrites: int = Field(0, exclude=True)
    blocked: list[str] = Field(default_factory=list, exclude=True)

    @computed_field
    @property
    def has_omitted_claims(self) -> bool:
        """Public notice only; rejected content and audit counts remain private."""
        return self.mode in ("model", "replay") and not self.not_found and self.dropped > 0


class PublicCase(Case):
    owner_id: str | None = Field(None, exclude=True)
    chat: list[PublicChatMessage] = Field(default_factory=list)


class SupplementIn(BaseModel):
    refresh_sources: bool = False
    model_config = ConfigDict(str_strip_whitespace=True)
    kind: Literal["material", "reply", "need"]
    text: str = Field(min_length=1, max_length=200000)
    title: str | None = Field(None, max_length=200)
    scenario: Literal["savings", "takeover", "job", "prepaid", "contract", "general"] | None = None


class ResolveIn(BaseModel):
    """人对某条判断下结论：疑点核实清楚了、是误识别、还是要继续查。

    系统自己不会把一条警告悄悄撤掉。要撤回，必须有人署名说清楚为什么。
    """
    judgment_id: str
    action: Literal["clarified", "withdrawn", "recheck"] = "clarified"
    note: str = Field("", max_length=4000)
    by: str = Field("用户", min_length=1, max_length=80)


class ChatIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)
    refs: list[str] = Field(default_factory=list, max_length=40)
    version: int | None = Field(default=None, ge=1, strict=True)  # 正在浏览的版本；不选条目也能问旧版


class ReadResult(BaseModel):
    text: str
    method: Literal["text", "pdf", "vision", "failed"]
    note: str | None = None
    status: Literal["ready", "partial", "needs_manual", "failed"] = "ready"
    pages: list[dict] = Field(default_factory=list)


# ---------- 用户评价（按公司存，不按案卷存；别人说的，未核实） ----------

REVIEW_RELATIONS = {"customer": "客户", "employee": "员工", "applicant": "求职者", "other": "其他"}


class ReviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    company: str = Field(min_length=2, max_length=80)
    stars: int = Field(ge=1, le=5)
    relation: Literal["customer", "employee", "applicant", "other"]
    text: str = Field(min_length=10, max_length=500)
    nickname: str | None = Field(None, max_length=20)
    author: str = Field(min_length=8, max_length=64)  # 浏览器里随机生成的匿名编号；后端只存哈希


class Review(BaseModel):
    id: str
    stars: int
    relation: str
    relation_label: str
    text: str
    nickname: str | None = None          # 空着显示"匿名用户"
    created_at: str
    demo: bool = False                   # 演示数据（只给虚构公司）
    mine: bool = False                   # 是不是这个浏览器写的


class ReviewList(BaseModel):
    company: str
    count: int
    dist: dict[str, int]                 # "5" → 条数 … "1" → 条数；不算平均分
    reviews: list[Review]                # 新的在前
