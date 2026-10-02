"""主线：建案卷 → 汇集数据 → 生成一版报告；补充信息 → 全量重跑 → 和上一版逐条比对。

结论全部来自 verify.py / signals.py 的确定性规则；这里只负责把数据、材料、场景接起来，
并把每条检查指回它依据的原始数据（RawRecord）。
"""
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import uuid4

from app.analysis.charts import build_charts
from app.analysis.diff import diff
from app.analysis.extract import ClaimExtractor, RuleExtractor
from app.analysis.followup import build_questions
from app.analysis.judgments import attach_disputes, build as build_judgments, update as update_judgments
from app.analysis.report import onepager
from app.analysis.signals import add_pack_items, build_signals, official_pack_items
from app.analysis.verify import verify
from app.models import (TRIGGER_LABELS, Assertion, Case, CaseIn, Intake, JudgmentChange, MissingItem, RawRecord,
                        ResolveIn, Signal, Source, SupplementIn, Version)
from app.scenarios import claim_rank, get_scenario
from app import config
from app.reviews import SOURCE_ID as REVIEW_SOURCE, ReviewStore, review_record
from app.sources.amac_detail import AmacDetailClient
from app.sources.catalog import build_sources, registry_sources
from app.sources.collect import Collected, collect, now
from app.sources.commercial import CommercialClient
from app.sources.fixtures import FixtureAmac, FixtureComplaints, FixtureRegistry
from app.sources.licenses import LicenseIndex
from app.sources.packs import EvidencePacks
from app.sources.qcc_agent import QccAgentClient
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
    commercial: CommercialClient | QccAgentClient | None = None        # 企查查/天眼查，配置了才用
    web: WebClient | None = None                                       # 联网查证，网关配置了才用
    amac_detail: AmacDetailClient | None = None                        # 中基协公示详情页
    reviews: ReviewStore | None = None                                 # 用户评价（按公司存）


def load_services() -> Services:
    licenses, registry = LicenseIndex.load(), FixtureRegistry.load()
    amac, complaints = FixtureAmac.load(), FixtureComplaints.load()
    registries = load_registries()
    sources = build_sources(licenses.meta, registry.as_of, amac.as_of, complaints.as_of) | registry_sources(registries)
    provider = os.getenv("XRAY_COMMERCIAL", "").strip().lower()
    commercial = QccAgentClient() if provider == "qcc_agent" else CommercialClient(provider)
    web = WebClient()
    return Services(licenses, registry, amac, complaints, EvidencePacks.load(), RuleExtractor(), sources, registries,
                    commercial if commercial.configured else None, web if web.configured else None,
                    AmacDetailClient(config.CACHE_DIR / "amac") if config.AMAC_DETAIL else None,
                    ReviewStore(config.REVIEWS_DIR, config.FIXTURES_DIR / "reviews.json"))


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
    amount = inp.amount or intake.amount
    signals = build_signals(ext, company, lic, amac, collected.complaints, collected.as_of, scenario, assertions,
                            collected.others, collected.web, web_refs, amount, collected.reviews)
    pack_items = official_pack_items(inp.company_name, [raw_by_id[rid] for rid in collected_ids])
    add_pack_items(signals, pack_items, raw, company, collected.web, web_refs)
    by_source = {raw_by_id[rid].source_id: rid for rid in collected_ids}
    link_refs(assertions, missing, signals, by_source, texts)
    charts = build_charts(ext, company, assertions, by_source, collected.web, web_refs, collected.complaints,
                          collected.as_of, amac)

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
    questions = build_questions(assertions, missing, signals, scenario, intake.focus)
    judges = build_judgments(inp.company_name, scenario, no, assertions, missing, signals, questions, texts, company)
    attach_disputes(judges, inp.company_name, assertions, texts, company)
    page = onepager(company_name=inp.company_name, for_whom=for_whom, amount=amount, scenario=scenario,
                    assertions=assertions, missing=missing, signals=signals, questions=questions,
                    sources=collected.sources)
    ver = Version(no=no, created_at=now(), trigger=trigger, trigger_label=TRIGGER_LABELS[trigger], need=inp.need,
                  for_whom=for_whom, amount=amount, scenario=scenario.id, scenario_label=scenario.label,
                  focus=intake.focus, raw_ids=collected_ids + [t.id for t in texts], company=company, license=lic,
                  amac=amac, assertions=assertions, missing=missing, signals=signals, tally=tally, notes=notes,
                  questions=questions, onepager=page, charts=charts, judgments=judges)
    if no == 1:
        ver.judgments, ver.judgment_changes, ver.judgment_summary = update_judgments([], judges, {}, 1)
    return ver


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
    cur.judgments, cur.judgment_changes, cur.judgment_summary = update_judgments(
        prev.judgments, cur.judgments, new_texts, cur.no)
    case.versions.append(cur)
    case.case, case.scenario, case.focus, case.current = inp, cur.scenario, cur.focus, cur.no
    case.sources = collected.sources
    return case


class NoNewReviews(Exception):
    """这家公司的评价和这一版报告里的一样，不用再出一版。"""


def _review_raw(case: Case, v: Version) -> RawRecord | None:
    return next((r for r in case.raw if r.id in v.raw_ids and r.source_id == REVIEW_SOURCE), None)


def refresh_reviews(case: Case, svc: Services) -> Case:
    """把这家公司最新的用户评价放进案卷，出新一版。别的数据照常重查一遍，和补充材料一样逐条比对。"""
    prev = case.versions[-1]
    before = _review_raw(case, prev)
    draft = review_record(svc.reviews.all(case.case.company_name)) if svc.reviews else None
    if draft is None or (before is not None and before.content == draft.content):
        raise NoNewReviews(case.id)
    intake = Intake(scenario=prev.scenario, scenario_label=prev.scenario_label, focus=prev.focus,
                    for_whom=prev.for_whom, amount=prev.amount, method="user")
    collected, ids = _collect_into(case.raw, case.case.company_name, svc)
    cur = build_version(prev.no + 1, "reviews", case.case, intake, collected, ids, case.raw, svc)
    after = _review_raw(case, cur)
    cur.changes, base = diff(prev, cur, {after.id: ""} if after else {})
    n_before = len(before.content) if before else 0
    cur.change_summary = (f"这一版放进了新写的用户评价：上一版 {n_before} 条，现在 {len(after.content)} 条。"
                          "评价是用户自己写的，没核实，只影响口碑里\"用户评价\"这一条。" + base)
    cur.judgments, cur.judgment_changes, cur.judgment_summary = update_judgments(prev.judgments, cur.judgments, {}, cur.no)
    case.versions.append(cur)
    case.current = cur.no
    case.sources = collected.sources
    return case


VERB = {"clarified": "已澄清", "withdrawn": "已撤回", "recheck": "需要重新核实"}


def resolve(case: Case, body: ResolveIn) -> Case:
    """人对某条判断下结论：疑点说清楚了、是误识别、还是要继续查。

    系统自己不会把一条警告悄悄撤掉；要撤回，必须有人署名讲清楚为什么。出的是一版新案卷，
    旧版留着，历史写在判断的 history 上。
    """
    prev = case.versions[-1]
    cur = prev.model_copy(deep=True)
    cur.no, cur.created_at, cur.trigger = prev.no + 1, now(), "resolve"
    cur.trigger_label, cur.need = TRIGGER_LABELS["resolve"], prev.need
    hit = None
    for j in cur.judgments:
        if j.id != body.judgment_id:
            continue
        before_label = j.state_label or "待核"
        j.history.append(f"第 {prev.no} 版起：{before_label}；第 {cur.no} 版：{VERB[body.action]}"
                         f"（{body.by}：{body.note or '没写说明'}）")
        j.state, j.state_label, j.changed_at = body.action, VERB[body.action], cur.no
        j.plain = f"{VERB[body.action]}（{body.by}：{body.note or '没写说明'}）。上一次状态：{before_label}。"
        if j.unknown and body.action in ("clarified", "withdrawn"):
            # 人去核实过了，就不能卡片上一边写"已澄清"一边还挂着"还没证明的事"。
            # 这些事不是被证据证明了，是被这个人担下来了 —— 所以写进 history，不留在待核清单里。
            j.history.append(f"第 {cur.no} 版起不再挂着这些待核的事：{'；'.join(j.unknown)}（由 {body.by} 核实）")
            j.unknown = []
        hit = j
    if hit is None:
        raise KeyError(body.judgment_id)

    # 报告那一头也要跟着改。否则判断上写着"已澄清"，报告里还在催人去核实，
    # 用户看到的就是"它只会加警告，不会撤警告"。
    for a in cur.assertions:
        if a.id != hit.target:
            continue
        a.plain = (f"第 {cur.no} 版：这条{VERB[body.action]}"
                   f"（{body.by}：{body.note or '没写说明'}）。原来的核验结论是：{a.plain}")

    cur.judgment_changes = []
    for j in cur.judgments:
        if j.id == body.judgment_id:
            cur.judgment_changes.append(JudgmentChange(
                target=j.id, label=hit.text[:40], kind="cleared", text=hit.text, before=hit.text, after=hit.text,
                plain=f"{VERB[body.action]}：{body.by}说「{body.note or '没写说明'}」。这条不再和上一版一样看待。"))
        else:
            cur.judgment_changes.append(JudgmentChange(
                target=j.id, label=j.text[:40], kind="same", text=j.text, before=j.text, after=j.text,
                plain=f"{j.text[:50]}：没变。"))
    n = len([1 for j in cur.judgments if j.state == "withdrawn"])
    cur.judgment_summary = (f"这一版只做了一件事：有一条判断改成「{VERB[body.action]}」，"
                            f"报告里那条提醒也跟着改了。其余 {max(len(cur.judgments) - 1, 0)} 条保持不变。"
                            + (f"现在案卷里有 {n} 条被撤回，不再算在要留意的事里。" if n else ""))
    cur.changes, cur.change_summary = [], f"没有新材料进来，只是把一条判断的结论改了：{VERB[body.action]}。"
    case.versions.append(cur)
    case.current = cur.no
    return case
