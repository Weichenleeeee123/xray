"""数据对象。

对应前端约定的 6 个对象：Case / Document / Observation / Assertion / Finding / Question。
前期分析只用到其中的 Case、Assertion，以及支撑它们的企业记录与数据来源。
"""
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Coverage(StrEnum):
    found = "found"              # 查过，有记录
    not_found = "not_found"      # 查过，没有
    not_covered = "not_covered"  # 没查：数据源未覆盖，不代表没有


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


class Verdict(StrEnum):
    mismatch = "mismatch"
    redline = "redline"
    misleading = "misleading"
    attention = "attention"
    unverifiable = "unverifiable"
    consistent = "consistent"


class Source(BaseModel):
    id: str
    name: str
    kind: Literal["official", "regulation", "demo", "user_material", "parameter"]
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


# ---------- 分析结果 ----------

class Check(BaseModel):
    label: str
    result: str
    status: Status
    source: str


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


class MissingItem(BaseModel):
    id: str
    text: str
    plain: str
    source: str


class SignalItem(BaseModel):
    key: str
    label: str
    value: str
    detail: str | None = None
    status: Status
    source: str


class Signal(BaseModel):
    key: Literal["risk", "finance", "credit", "reputation"]
    title: str
    lede: str
    flags: int
    items: list[SignalItem]
    extra: dict | None = None


class CaseIn(BaseModel):
    company_name: str = Field(min_length=2)
    for_whom: str = "妈妈"
    amount: float = Field(200000, gt=0)
    concern: str = ""
    flyer_text: str | None = None


class CaseOut(BaseModel):
    id: str
    version: str
    case: CaseIn
    company: CompanyProfile | None
    license: LicenseHit
    amac: AmacHit
    assertions: list[Assertion]
    missing: list[MissingItem]
    signals: list[Signal]
    tally: dict[str, int]
    notes: list[str]
    sources: dict[str, Source]
