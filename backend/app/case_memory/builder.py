"""Deterministic notes: original report objects and exact JSON-field locators."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.models import Case, Version
from .models import CaseMemory, EvidenceCard, EvidenceUnit, Locator

BUILDER_VERSION = "deterministic-2-public-discovery"
TOPICS = {
    "identity": ("名称", "身份", "登记", "主体", "股东", "成立", "状态", "统一社会信用", "registry", "status"),
    "license": ("资质", "资格", "牌照", "持牌", "许可证", "经营范围", "scope", "bank_list", "amac"),
    "parties": ("合同", "签约", "甲方", "乙方", "主体", "合作", "parties"),
    "payee": ("收款", "账户", "转账", "户名", "付款", "打款", "payee"),
    "withdrawal": ("退款", "取用", "取回", "取出", "退出", "赎回", "急用", "不退", "可退", "退费", "refund"),
    "fees": ("费用", "收费", "扣费", "手续费", "违约", "押金", "培训费", "upfront_fee"),
    "term": ("期限", "到期", "提前", "服务开始", "终止", "条件", "例外"),
    "returns": ("收益", "回报", "年化", "保本", "保息", "利息", "promise"),
    "credit": ("处罚", "纠纷", "诉讼", "失信", "被执行", "欠税", "监管", "penalt", "litigation"),
    "job": ("工作", "薪酬", "工资", "岗位", "入职", "试用", "offer", "欠薪", "招聘"),
    "business": ("业务", "做什么", "干什么", "主营", "公司介绍", "公司简介"),
    "brand": ("品牌", "简称", "英文名", "旗下"),
    "product": ("产品", "应用", "软件", "硬件", "app"),
    "funding": ("融资", "投资方", "融资轮", "创投"),
    "activity": ("活动", "发布", "参访", "展会", "园区", "合作"),
    "media": ("报道", "采访", "新闻", "记者", "快讯"),
    "finance": ("财务", "净利润", "营业收入", "资产", "负债", "资本", "实缴", "认缴", "抵押", "质押", "finance"),
    "reputation": ("投诉", "评价", "口碑", "舆情", "新闻", "reputation"),
    "gaps": ("未查", "失败", "未覆盖", "尚不", "没查", "缺失", "未知", "gap"),
}


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def tags(text: str) -> list[str]:
    lower = text.lower()
    return [topic for topic, words in TOPICS.items() if any(w in lower for w in words)]


def words(text: str) -> list[str]:
    # Bigrams enable unlisted Chinese company/field terms without an external tokenizer.
    chunks = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_.]+", text.lower())
    return sorted({w for chunk in chunks for w in (
        [chunk] if re.fullmatch(r"[a-z0-9_.]+", chunk) else
        [chunk[i:i+2] for i in range(max(1, len(chunk)-1))]
    )})


def authorize(case: Case, owner: str) -> None:
    if not owner or case.owner_id != owner:
        raise PermissionError("Private case ownership required")


def version(case: Case, no: int) -> Version:
    return next(v for v in case.versions if v.no == no)


def manifest(case: Case, v: Version) -> str:
    value = {"company": case.case.company_name, "version": v.model_dump(mode="json"),
             "sources": {k: s.model_dump(mode="json") for k, s in (v.sources or case.sources).items()},
             "raw": [r.model_dump(mode="json") for r in case.raw if r.id in v.raw_ids]}
    return hashlib.sha256(dump(value).encode()).hexdigest()


def ruleset() -> str:
    base = Path(__file__).resolve().parents[1]
    files = sorted((base / "analysis").glob("*.py")) + sorted((base / "scenarios").glob("*.json"))
    files += [base / "glossary.json"]
    digest = hashlib.sha256()
    for path in files:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    digest.update(dump([config.REF_DEPOSIT_RATE, config.HIGH_RETURN_RATIO,
                       config.LOW_PAID_RATIO, config.YOUNG_COMPANY_MONTHS]).encode())
    return digest.hexdigest()


def locate(content, path: list[str | int]):
    for part in path:
        content = content[part]
    return content


def units(content, path=()):
    """Use fields/complete rows, never cut a sentence. User documents use root."""
    if isinstance(content, dict):
        for key, value in content.items():
            if isinstance(value, (dict, list)) and len(dump(value)) > 8000:
                yield from units(value, (*path, key))
            else:
                yield list((*path, key)), value
    elif isinstance(content, list):
        for i, value in enumerate(content):
            yield list((*path, i)), value
    else:
        yield list(path), content


def build(case: Case, no: int, owner: str) -> CaseMemory:
    authorize(case, owner)
    v = version(case, no)
    memory = CaseMemory(case_id=case.id, version_no=no, owner_key=owner,
                        source_manifest_hash=manifest(case, v), ruleset_version=ruleset(),
                        builder_version=BUILDER_VERSION)
    raw_ids = set(v.raw_ids)
    rows = []
    rows.extend((a.id, "rule_result", a.kind_label + " " + a.text + " " + a.plain,
                 [*a.refs, *(c.ref for c in a.checks if c.ref)], a.model_dump(mode="json")) for a in v.assertions)
    rows.extend((m.id, "gap", m.text + " " + m.plain, m.refs, m.model_dump(mode="json")) for m in v.missing)
    rows.extend((f"{s.key}.{i.key}", "report_item", i.label + " " + i.value + " " + (i.detail or ""),
                 [i.ref] if i.ref else [], i.model_dump(mode="json")) for s in v.signals for i in s.items)
    rows.extend((q.id, "question", q.ask + " " + q.why, [], q.model_dump(mode="json")) for q in v.questions)
    for ref, kind, text, refs, payload in rows:
        memory.cards.append(EvidenceCard(card_id=ref, topics=tags(ref + " " + text) or ["identity"],
            statement_type=kind, summary=text, fact_refs=[ref], raw_refs=sorted(set(refs) & raw_ids),
            coverage=str(payload.get("gap") or payload.get("status") or kind), payload=payload))
    for raw in case.raw:
        if raw.id not in raw_ids or raw.discovery is None:
            continue
        # Navigation cards are NOT new fact_ids or risk judgments. Read the raw unit.
        memory.cards.append(EvidenceCard(card_id=f"public:{raw.id}",
            topics=raw.discovery.topics or tags(raw.title) or ["business"],
            statement_type="source_statement", summary=raw.title, raw_refs=[raw.id],
            coverage=raw.coverage.value, conditions=[raw.note or "来源说法待核实"],
            payload={"title": raw.title, "navigation_only": True,
                     "provenance": raw.discovery.model_dump(mode="json", include={
                         "relation", "nature", "read_state", "canonical_url"})}))
    by_ref = {c.card_id: c for c in memory.cards}
    for judgment in v.judgments:
        card = by_ref.get(judgment.target)
        if card:
            card.conditions = [*judgment.premise, *judgment.unknown, *judgment.cannot, *judgment.dispute]
            card.payload["judgment"] = judgment.model_dump(mode="json")
            card.raw_refs = sorted(set(card.raw_refs) | {b.ref for b in judgment.basis if b.ref in raw_ids})
            # Conflicts are preserved from the authoritative rule, not guessed by the model.
            if judgment.dispute:
                card.conflicts_with = [c.card_id for c in memory.cards if c.card_id != card.card_id
                                       and set(c.raw_refs) & set(card.raw_refs)]
    for card in memory.cards:
        card.related_cards = sorted({c.card_id for c in memory.cards if c.card_id != card.card_id
            and (set(c.raw_refs) & set(card.raw_refs) or c.card_id in card.payload.get("linked", []))})
        card.locators = [Locator(raw_id=r) for r in card.raw_refs]
    for raw in case.raw:
        if raw.id not in raw_ids:
            continue
        # A public page stays together with its relationship, acquisition state and
        # conflicting statements. Avoid repeating a large parent body per metadata field.
        parts = [([], raw.content)] if raw.kind == "user_material" or raw.discovery else units(raw.content)
        for i, (path, value) in enumerate(parts):
            searchable = raw.title + " " + dump(path) + " " + dump(value)
            memory.evidence_index.append(EvidenceUnit(unit_id=f"{raw.id}:{i}", locator=Locator(raw_id=raw.id, path=path),
                topics=sorted(set(tags(searchable)) | set(raw.discovery.topics if raw.discovery else [])),
                keywords=words(searchable), chars=len(dump(value))))
    memory.overview = {
        "company": case.case.company_name, "purpose": v.need, "version": no, "report_date": v.created_at,
        "navigation_only": True,
        "findings": [c.card_id for c in memory.cards if c.statement_type != "question"],
        "unknown": [c.card_id for c in memory.cards if c.statement_type == "gap" or c.payload.get("gap")],
        "conflicts": [j.model_dump(mode="json") for j in v.judgments if j.dispute],
        "changes": [c.model_dump(mode="json") for c in v.changes],
        "judgment_changes": [c.model_dump(mode="json") for c in v.judgment_changes],
        "coverage": [{"ref": r.id, "kind": r.kind, "coverage": r.coverage.value, "as_of": r.as_of,
                      "retrieved_at": r.retrieved_at, "note": r.note,
                      **({"discovery": r.discovery.model_dump(mode="json", include={
                          "relation", "nature", "read_state", "topics"})} if r.discovery else {})}
                     for r in case.raw if r.id in raw_ids],
    }
    memory.state = "ready"
    memory.built_at = datetime.now(timezone.utc).isoformat()
    return memory
