"""数据结构：前后端和三个人之间唯一的契约。改字段先在群里说。

一个案卷（Case）= 用户输入 + 原始数据（RawRecord）+ 若干版报告（Version）+ 助手对话（ChatMessage）。
报告里每条检查都有 source（指回 Source）和 ref（指回 RawRecord），前端据此点进原始数据。
"""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


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


SourceKind = Literal["official", "collected", "regulation", "demo", "user_material", "web", "parameter"]


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


class AmacHit(BaseModel):
    coverage: Coverage
    registered: bool | None = None
    source: str = "amac"


# ---------- 原始数据 ----------

class RawRecord(BaseModel):
    """每次取数据、每份用户材料都记一条。报告第四层就是这些记录。"""
    id: str                              # R1、R2……同一案卷内唯一
    source_id: str                       # 指回 Source
    title: str
    kind: Literal["official", "collected", "user_material", "web", "demo"]
    coverage: Coverage = Coverage.found
    retrieved_at: str
    as_of: str | None = None             # 数据本身的截止日期
    url: str | None = None
    content: dict | list | str | None = None  # 原文或字段
    screenshot: str | None = None
    note: str | None = None              # 例如"对方说的，未核实""手动录入"


# ---------- 分析结果 ----------

class Check(BaseModel):
    label: str
    result: str
    status: Status
    source: str
    ref: str | None = None               # RawRecord id；法规、参数类来源没有


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


class Signal(BaseModel):
    key: Literal["risk", "finance", "credit", "reputation"]
    title: str
    lede: str
    flags: int
    items: list[SignalItem]
    extra: dict | None = None


class Question(BaseModel):
    id: str
    ask: str                             # 该问对方的话
    why: str
    check_where: str                     # 拿到答案后去哪里查
    linked: list[str] = Field(default_factory=list)  # 关联的说法、信号条目 id


class Change(BaseModel):
    target: str                          # 说法 id（A1）、缺项 id（M1）或信号条目（risk.bank_list）
    label: str
    kind: Literal["new_concern", "worse", "clarified", "unchanged", "added", "removed"]
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
    company_name: str = Field(min_length=2)
    need: str = ""                        # 一句需求，例如"我妈想存 20 万理财，最怕急用时取不出来"
    scenario: str | None = None           # 不填就从需求里识别
    for_whom: str | None = None
    amount: float | None = Field(None, gt=0)
    material_text: str | None = None      # 可选：宣传单、合同、聊天记录的文字
    material_title: str | None = None


class IntakeIn(BaseModel):
    need: str = ""
    company_name: str | None = None


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
    license_checks: list[str]
    claim_kinds: list[ClaimKind]
    signal_order: list[Literal["risk", "finance", "credit", "reputation"]]
    signal_ledes: dict[str, str] = Field(default_factory=dict)
    must_ask: list[MustAsk]
    onepager_title: str


TRIGGER_LABELS = {"initial": "首次分析", "material": "补充材料", "reply": "对方回复", "need": "修改需求"}


class Version(BaseModel):
    no: int
    created_at: str
    trigger: Literal["initial", "material", "reply", "need"]
    trigger_label: str
    need: str
    for_whom: str | None = None
    amount: float | None = None
    scenario: str
    scenario_label: str
    focus: list[str]
    raw_ids: list[str]                    # 本版用到的原始数据
    company: CompanyProfile | None
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
    onepager: OnePager | None = None


class Quote(BaseModel):
    ref: str
    text: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    refs: list[str] = Field(default_factory=list)       # 用户选中的报告条目
    citations: list[str] = Field(default_factory=list)  # 回答引用的条目或原始数据 id
    quotes: list[Quote] = Field(default_factory=list)   # 逐字校验过的原文
    suggest: list[str] = Field(default_factory=list)    # 建议补查或补充的材料
    not_found: bool = False                             # 数据里没有，回答"没查到"
    dropped: int = 0                                    # 被程序丢掉的出处或引文（编造的 id、对不上的原文）
    version: int
    mode: Literal["model", "replay", "template", "guard"] | None = None
    recorded_at: str | None = None                      # 离线回放时，响应的录制时间
    created_at: str


class Case(BaseModel):
    id: str
    created_at: str
    case: CaseIn                          # 最新的输入
    scenario: str
    focus: list[str]
    current: int                          # 当前版本号
    versions: list[Version]
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


class SupplementIn(BaseModel):
    kind: Literal["material", "reply", "need"]
    text: str = Field(min_length=1)       # 材料文字、对方回复，或新的需求
    title: str | None = None
    scenario: str | None = None           # 改需求时，用户手动指定场景


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    refs: list[str] = Field(default_factory=list)


class ReadResult(BaseModel):
    text: str
    method: Literal["text", "pdf", "vision", "failed"]
    note: str | None = None
