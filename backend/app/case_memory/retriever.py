"""Deterministic routing and relation expansion, scoped BEFORE searching."""
import re

from app.models import Case, Version
from app.conversation import GUIDES, WORRY
from . import builder
from .models import CaseMemory, RetrievalResult

TRANSACTION = {"withdrawal", "fees", "term", "parties", "payee"}


def condition_excerpts(leaf: str) -> list[str]:
    """Output companions from already fully-read text, at sentence boundaries.

    This is not an input compressor. Short fields remain intact. In a long
    document keep matching terms, all explicit exceptions/limitations, and their
    adjacent sentences; merge overlapping spans. Never trim a long sentence.
    Each returned span is still an exact substring of the original leaf.
    """
    if len(leaf) <= 2900:
        return [leaf]
    sentences = list(re.finditer(r"[^。！？\n]+[。！？\n]*", leaf))
    companions = re.compile(r"除非|除外|例外|但是|不过|否则|不得|不予|仅限|前提|限制|另行|详见|附件|以.{0,12}为准")
    selected = set()
    for i, sentence in enumerate(sentences):
        text = sentence.group()
        if set(builder.tags(text)) & {"withdrawal", "fees", "term"} or companions.search(text):
            selected.update(range(max(0, i-1), min(len(sentences), i+2)))
    spans = []
    for i in sorted(selected):
        start, end = sentences[i].span()
        if spans and start <= spans[-1][1]:
            spans[-1][1] = end
        else:
            spans.append([start,end])
    return list(dict.fromkeys(leaf[start:end] for start,end in spans))


def leaves(value) -> list[str]:
    if isinstance(value, dict):
        return [s for item in value.values() for s in leaves(item)]
    if isinstance(value, list):
        return [s for item in value for s in leaves(item)]
    return [] if value is None else [str(value)]


def read_evidence(case: Case, no: int, owner: str, locator):
    builder.authorize(case, owner)
    v = builder.version(case, no)
    raw = next(r for r in case.raw if r.id == locator.raw_id and r.id in v.raw_ids)
    value = builder.locate(raw.content, locator.path)
    # Keep the parent row's scalar fields (subject/date/unit/conditions) with each field.
    parents, parent = [], raw.content
    for part in locator.path:
        if isinstance(parent, dict):
            parents.append({k: item for k, item in parent.items() if not isinstance(item, (dict, list))})
        parent = parent[part]
    return raw, {"ref": raw.id, "path": locator.path, "content": value, "parent_fields": parents,
                 "source": raw.source_id, "kind": raw.kind, "coverage": raw.coverage.value,
                 "as_of": raw.as_of, "retrieved_at": raw.retrieved_at, "note": raw.note,
                 **({"url": raw.url, "discovery": raw.discovery.model_dump(mode="json")}
                    if raw.discovery else {})}


def compare_versions(case: Case, owner: str, from_no: int, to_no: int) -> dict:
    builder.authorize(case, owner)
    before, after = builder.version(case, from_no), builder.version(case, to_no)
    return {"from_version": from_no, "to_version": to_no,
            "comparison_scope": "saved_version_changes" if from_no == to_no - 1 else "version_snapshots",
            "before": [j.model_dump(mode="json") for j in before.judgments],
            "after": [j.model_dump(mode="json") for j in after.judgments],
            "changes": [c.model_dump(mode="json") for c in after.changes] if from_no == to_no - 1 else []}


def retrieve(case: Case, v: Version, owner: str, memory: CaseMemory, question: str,
             refs: list[str], *, evidence_budget: int = 70000) -> RetrievalResult:
    builder.authorize(case, owner)
    if (memory.owner_key != owner or memory.case_id != case.id or memory.version_no != v.no
        or memory.state != "ready" or memory.source_manifest_hash != builder.manifest(case, v)
        or memory.builder_version != builder.BUILDER_VERSION or memory.ruleset_version != builder.ruleset()):
        raise ValueError("Memory does not match the authorized version")
    by_id = {c.card_id: c for c in memory.cards}
    raw_ids = set(v.raw_ids)
    if any(ref not in by_id and ref not in raw_ids for ref in refs):
        raise ValueError("Reference not in authorized version")
    query = question
    if not refs and re.search(r"那|这个|它呢|继续|上面", question):
        previous = next((m for m in reversed(case.chat) if m.role == "user" and m.version == v.no), None)
        if previous:
            query = previous.text + " " + question
    requested = set(builder.tags(query))
    for ref in refs:
        if ref in by_id:
            requested.update(by_id[ref].topics)
    broad = bool(re.search(r"整体|全面|还有哪些|都有哪些|总体|全部|所有|总的", query))
    support = not refs and bool(WORRY.search(question) or re.search(r"我想存|准备存|我想投", question)) and not re.search(
        r"公司|报告|记录|处罚|牌照|保本|靠谱|能取|能退|取不出|急用", question)
    if requested & TRANSACTION:
        requested.update(TRANSACTION)  # Exit, fee, time, parties and payee are one verification bundle.
    if not requested and not support:
        broad = True  # Unknown intent is not a license to retrieve nothing and say "no risk".
    intent = "support" if support else "overview" if broad else "targeted"
    chosen = set() if support else {c.card_id for c in memory.cards if broad or set(c.topics) & requested}
    chosen.update(r for r in refs if r in by_id)
    # Expand direct source/explicit question relationships once, then all conflict companions.
    for ref in list(chosen):
        chosen.update(by_id[ref].related_cards)
    for ref in list(chosen):
        chosen.update(by_id[ref].conflicts_with)
    cards = [c for c in memory.cards if c.card_id in chosen]
    linked_raw = {r for c in cards for r in c.raw_refs}
    wanted_words = set(builder.words(query))
    selected = []
    private_docs = {r.id for r in case.raw if r.id in raw_ids and r.kind == "user_material"}
    for unit in memory.evidence_index:
        direct = unit.locator.raw_id in refs
        companion_document = bool(requested & TRANSACTION) and unit.locator.raw_id in private_docs
        matching = bool(set(unit.topics) & requested or set(unit.keywords) & wanted_words)
        if not support and (broad or direct or companion_document or matching):
            selected.append(unit)
    # A keyword hit in one field cannot hide a companion field/row in the
    # authoritative fact's own record. Pull all its complete units, not only
    # the first matching leaf; oversized records produce an explicit gap below.
    selected_ids = {u.unit_id for u in selected}
    selected.extend(u for u in memory.evidence_index if u.locator.raw_id in linked_raw and u.unit_id not in selected_ids)
    # Unknown/failure coverage and conflicts are always visible, including for broad questions.
    overview = {**memory.overview}
    if support:
        overview = {k: overview[k] for k in ("company", "purpose", "version", "navigation_only")}
    result = RetrievalResult(intent=intent, topics=sorted(requested), selected_cards=[c.card_id for c in cards])
    used, snippets = 0, []
    for unit in selected:
        raw, snippet = read_evidence(case, v.no, owner, unit.locator)
        size = len(builder.dump(snippet))
        if used + size > evidence_budget:
            result.omitted_units.append(unit.unit_id)
            continue  # Whole boundary omitted with explicit coverage failure, never char slicing.
        used += size
        snippets.append(snippet)
        result.raw_leaves.setdefault(raw.id, []).extend(leaves(snippet["content"]))
        result.raw_leaves[raw.id].extend(leaves(snippet["parent_fields"]))
    found_topics = {t for u in selected for t in u.topics}
    result.missing_topics = sorted(requested - found_topics)
    result.complete = not result.omitted_units
    result.provided_refs = [*dict.fromkeys([r for c in cards for r in c.fact_refs] + list(result.raw_leaves))]
    result.reasons = ["explicit_refs" if refs else "topic_and_keyword", "related_conditions_and_conflicts"]
    result.context = {
        "读取方式": "全量保存，按需读取；概览仅是导航，不是独立证据。",
        "案卷id": case.id, "报告版本": v.no, "公司": case.case.company_name,
        "案卷概览": overview,
        "已读取报告条目": [{"ref":c.card_id,"type":c.statement_type,"conditions":c.conditions,
                           "data":c.payload} for c in cards],
        "已读取原文": snippets,
        "覆盖说明": {"complete":result.complete,"missing_topics":result.missing_topics,
                     "omitted_units":len(result.omitted_units),
                     "notice":"未检索到不等于材料不存在或没有问题。用户材料、评价仍未经核实。"},
        "行动目录（仅问题与核对步骤，不是公司事实）": GUIDES,
        "未核实的历史对话（不是证据）": [{"role":m.role,"text":m.text} for m in case.chat if m.version == v.no][-4:],
        "允许引用的条目": result.provided_refs,
    }
    return result
