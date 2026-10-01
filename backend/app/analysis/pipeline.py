"""主线：建案卷 → 汇集数据 → 生成一版报告；补充信息 → 全量重跑 → 和上一版逐条比对。

结论全部来自 verify.py / signals.py 的确定性规则；这里只负责把数据、材料、场景接起来，
并把每条检查指回它依据的原始数据（RawRecord）。
"""
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import uuid4

from app.analysis.diff import diff
from app.analysis.extract import ClaimExtractor, RuleExtractor
from app.analysis.followup import build_questions
from app.analysis.report import onepager
from app.analysis.signals import build_signals
from app.analysis.verify import verify
from app.models import (TRIGGER_LABELS, Assertion, Case, CaseIn, Intake, MissingItem, RawRecord, Signal, Source,
                        SupplementIn, Version)
from app.scenarios import claim_rank, get_scenario
from app.sources.catalog import build_sources, registry_sources
from app.sources.collect import Collected, collect, now
from app.sources.commercial import CommercialClient
from app.sources.fixtures import FixtureAmac, FixtureComplaints, FixtureRegistry
from app.sources.licenses import LicenseIndex
from app.sources.packs import EvidencePacks
from app.sources.registries import RegistryIndex, load_registries
from app.sources.web import WebClient

TEXT_SOURCES = ("self_description", "material")  # 这两类原始数据里的文字是"宣称"
DODGE = re.compile(r"放心|绝对|保证|没问题|大家都|别担心|不用担心|相信我们|正规的|很多人")
CHECKABLE = re.compile(r"\d{4,}|编码|编号|合同|协议|户名|许可证")


@dataclass
class Services:
    licenses: LicenseIndex
    registry: FixtureRegistry
    amac: FixtureAmac
    complaints: FixtureComplaints
    packs: EvidencePacks
    extractor: ClaimExtractor
    sources: dict[str, Source]
    registries: dict[str, RegistryIndex] = field(default_factory=dict)  # 保险、期货、支付、私募等官方名单
    commercial: CommercialClient | None = None                         # 企查查/天眼查，配置了才用
    web: WebClient | None = None                                       # 联网查证，网关配置了才用


def load_services() -> Services:
    licenses, registry = LicenseIndex.load(), FixtureRegistry.load()
    amac, complaints = FixtureAmac.load(), FixtureComplaints.load()
    registries = load_registries()
    sources = build_sources(licenses.meta, registry.as_of, amac.as_of, complaints.as_of) | registry_sources(registries)
    commercial, web = CommercialClient(), WebClient()
    return Services(licenses, registry, amac, complaints, EvidencePacks.load(), RuleExtractor(), sources, registries,
                    commercial if commercial.configured else None, web if web.configured else None)


# ---------- 原始数据 ----------

def attach(raw: list[RawRecord], draft: RawRecord) -> str:
    """同一来源、同样内容的记录只存一份；内容变了才新增一条。"""
    for r in raw:
        if (r.source_id, r.title, r.coverage, r.content) == (draft.source_id, draft.title, draft.coverage, draft.content):
            return r.id
    rid = f"R{len(raw) + 1}"
    raw.append(draft.model_copy(update={"id": rid}))
    return rid


def material_record(text: str, title: str | None, trigger: str) -> RawRecord:
    default = {"initial": "用户提供的材料", "material": "补充材料", "reply": "对方回复"}[trigger]
    note = "对方说的，未核实" if trigger == "reply" else "用户提供；系统只读文字，不判断材料真伪"
    return RawRecord(id="", source_id="material", title=title or default, kind="user_material",
                     retrieved_at=now(), content=text, note=note)


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def link_refs(assertions: list[Assertion], missing: list[MissingItem], signals: list[Signal],
              by_source: dict[str, str], texts: list[RawRecord]) -> None:
    """给每条检查填上 ref：点开它就能看到依据的原始数据。"""
    latest_text = texts[-1].id if texts else None
    for a in assertions:
        a.refs = [t.id for t in texts if any(_flat(q) in _flat(t.content) for q in a.quotes)]
        for c in a.checks:
            c.ref = c.ref or by_source.get(c.source) or ((a.refs or [latest_text])[0] if c.source == "material" else None)
    for m in missing:
        m.refs = [t.id for t in texts]
    for s in signals:
        for i in s.items:
            i.ref = i.ref or by_source.get(i.source) or (latest_text if i.source == "material" else None)


# ---------- 生成一版报告 ----------

def build_version(no: int, trigger: str, inp: CaseIn, intake: Intake, collected: Collected,
                  collected_ids: list[str], raw: list[RawRecord], svc: Services) -> Version:
    scenario = get_scenario(intake.scenario)
    texts = [r for r in raw if r.source_id in TEXT_SOURCES and isinstance(r.content, str)]
    text = "\n".join(t.content for t in texts)
    ext = svc.extractor.extract(text)
    company, lic, amac = collected.company, collected.license, collected.amac

    assertions, missing = verify(ext, company, lic, amac, svc.licenses, inp.company_name, collected.others)
    rank = claim_rank(scenario)
    assertions.sort(key=lambda a: rank(a.kind))
    raw_by_id = {r.id: r for r in raw}
    web_refs = {raw_by_id[rid].url: rid for rid in collected_ids if raw_by_id[rid].source_id.startswith("web_")}
    signals = build_signals(ext, company, lic, amac, collected.complaints, collected.as_of, scenario, assertions,
                            collected.others, collected.web, web_refs)
    by_source = {raw_by_id[rid].source_id: rid for rid in collected_ids}
    link_refs(assertions, missing, signals, by_source, texts)

    colors = Counter(a.color for a in assertions)
    tally = {c: colors.get(c, 0) for c in ("red", "amber", "grey", "green")} | {"missing": len(missing)}

    notes = []
    if collected.note:
        notes.append(collected.note)
    if collected.sources["registry"].kind == "commercial":
        notes.append("登记信息来自商业数据接口（第三方加工），有出入时以国家企业信用信息公示系统为准。")
    if company and collected.sources["registry"].kind == "demo":
        notes.append("演示数据 · 公司为虚构：登记、年报、投诉都是编出来的，只用来演示。")
    if company is None:
        notes.append("还没有这家公司的登记数据：股东、资本、处罚等核验显示为\"没查\"。持牌名单是真实数据，照常核验。")
    if collected.web:
        notes.append("联网查证只能找到公开报道和政府网站上的文件，搜不到不等于没有" +
                     ("；本次用的是离线回放的搜索结果。" if collected.web.replay else "。"))
    if not texts:
        notes.append("还没有这家公司的说法：上传宣传材料、合同或聊天记录，就能逐条对照。")
    elif not ext.claims:
        notes.append("材料里没有识别到需要核验的说法。")

    for_whom = inp.for_whom or intake.for_whom
    amount = inp.amount or intake.amount
    questions = build_questions(assertions, missing, signals, scenario, intake.focus)
    page = onepager(company_name=inp.company_name, for_whom=for_whom, amount=amount, scenario=scenario,
                    assertions=assertions, missing=missing, signals=signals, questions=questions,
                    sources=collected.sources)
    return Version(no=no, created_at=now(), trigger=trigger, trigger_label=TRIGGER_LABELS[trigger], need=inp.need,
                   for_whom=for_whom, amount=amount, scenario=scenario.id, scenario_label=scenario.label,
                   focus=intake.focus, raw_ids=collected_ids + [t.id for t in texts], company=company, license=lic,
                   amac=amac, assertions=assertions, missing=missing, signals=signals, tally=tally, notes=notes,
                   questions=questions, onepager=page)


def _collect_into(raw: list[RawRecord], name: str, svc: Services) -> tuple[Collected, list[str]]:
    collected = collect(name, svc)
    return collected, [attach(raw, r) for r in collected.records]


def new_case(body: CaseIn, intake: Intake, svc: Services) -> Case:
    raw: list[RawRecord] = []
    collected, ids = _collect_into(raw, body.company_name, svc)
    if body.material_text and body.material_text.strip():
        attach(raw, material_record(body.material_text, body.material_title, "initial"))
    inp = body.model_copy(update={"scenario": intake.scenario, "for_whom": body.for_whom or intake.for_whom,
                                  "amount": body.amount or intake.amount})
    v1 = build_version(1, "initial", inp, intake, collected, ids, raw, svc)
    return Case(id=uuid4().hex[:12], created_at=now(), case=inp, scenario=v1.scenario, focus=v1.focus, current=1,
                versions=[v1], raw=raw, sources=collected.sources)


def supplement(case: Case, body: SupplementIn, intake: Intake | None, svc: Services) -> Case:
    """补充信息后重新判断。intake 只在改需求时需要（重新识别场景和关注点）。"""
    prev = case.versions[-1]
    inp, new_texts = case.case, {}
    if body.kind == "need":
        # 换了场景，旧需求里的金额和"替谁看"说的是另一件事，不沿用；场景没变才沿用
        same = intake.scenario == prev.scenario
        inp = inp.model_copy(update={"need": body.text, "scenario": intake.scenario,
                                     "for_whom": intake.for_whom or (inp.for_whom if same else None),
                                     "amount": intake.amount or (inp.amount if same else None)})
    else:
        intake = Intake(scenario=prev.scenario, scenario_label=prev.scenario_label, focus=prev.focus,
                        for_whom=prev.for_whom, amount=prev.amount, method="user")
        rid = attach(case.raw, material_record(body.text, body.title, body.kind))
        new_texts = {rid: body.text}

    collected, ids = _collect_into(case.raw, inp.company_name, svc)
    cur = build_version(prev.no + 1, body.kind, inp, intake, collected, ids, case.raw, svc)
    if body.kind == "reply" and DODGE.search(body.text) and not CHECKABLE.search(body.text):
        cur.notes.append("对方的回复没有给出任何可以核对的信息（编号、合同、户名），只是让你放心。这不算回答。")
    cur.changes, cur.change_summary = diff(prev, cur, new_texts)
    case.versions.append(cur)
    case.case, case.scenario, case.focus, case.current = inp, cur.scenario, cur.focus, cur.no
    case.sources = collected.sources
    return case
