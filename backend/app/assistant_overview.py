"""Bounded reading of an existing report, not a new whole-case investigation.

The caller has already authorized the private case and selected its version.
No model, external search, raw-text truncation or risk reclassification occurs
here. Every company statement is a server-formed report item with a current
source binding; general conversation must not become an evidence exemption.
"""
from collections import Counter
import re

from app.analysis.company_keywords import company_keywords
from app.analysis.company_summary import FOCUS_KEYS, perspective
from app.analysis.overview import build_overview
from app.demo_presentation import refresh_presentations
from app.models import Case, ChatMessage, Coverage, OverviewItem, RawRecord, Status, Version
from app.sources.collect import now


MAX_ITEM_CHARS = 800
PUBLIC_KINDS = {"official", "collected", "commercial", "web", "demo"}
SCOPE_NOTE = "依据本版报告，不代表逐条重新阅读全部原文；未覆盖或未核实的部分，不能据此判断有无问题。"
NEXT_QUESTIONS = {
    "general": "你更想了解它的业务与产品、工作机会，还是某项具体记录？",
    "job": "接下来想先看劳动争议的具体内容，还是招聘与参保记录？",
    "savings": "接下来想先看机构资质的依据，还是具体产品需要核对的地方？",
    "investment": "接下来想先看对应期间的财务数字，还是合规记录的具体内容？",
    "contract": "接下来想先看执行记录，还是诉讼所涉事项和处理结果？",
    "prepaid": "接下来想先看服务与退款相关线索，还是机构的经营记录？",
    "rental": "接下来想先看机构经营记录，还是房源及出租权限需要核对的地方？",
    "takeover": "接下来想先看债务与执行线索，还是登记和经营记录？",
}


def _records(case: Case, version: Version) -> dict[str, RawRecord]:
    counts = Counter(record.id for record in case.raw)
    return {record.id: record for record in case.raw
            if record.id in version.raw_ids and counts[record.id] == 1}


def _binding(item: OverviewItem, records: dict[str, RawRecord]) -> RawRecord | None:
    record = records.get(item.ref)
    if (record is None or record.kind not in PUBLIC_KINDS
            or record.source_id != item.source):
        return None
    return record


def _supported(item: OverviewItem, records: dict[str, RawRecord]) -> bool:
    record = _binding(item, records)
    if record is None or record.coverage not in {Coverage.found, Coverage.not_found}:
        return False
    # A completed empty search can ground a scoped 'not found' result. A source
    # marked found with no content cannot establish a positive company fact.
    return record.coverage == Coverage.not_found or bool(record.content)


def _date(record: RawRecord) -> str:
    return (f"来源数据日期：{record.as_of}" if record.as_of
            else "来源未标明数据截止日期")


def _selected_signal(version: Version, row: OverviewItem):
    return next((item for signal in version.signals for item in signal.items
                 if f"{signal.key}.{item.key}" == row.id
                 and item.value == row.text and item.status == row.status
                 and item.ref == row.ref and item.source == row.source), None)


def _render_item(version: Version, row: OverviewItem, records: dict[str, RawRecord]) -> tuple[str, list[str]]:
    record = _binding(row, records)
    cites = [row.id] + ([record.id] if record else [])
    markers = " ".join(f"[{ref}]" for ref in cites)
    label = row.label if len(row.label) <= 120 else "该核查项"
    if not _supported(row, records):
        state = "；原报告将此项列为异常，不能当作已排除" if row.status == Status.bad else ""
        return f"{label}：本版出处或查询结果尚未完整对应，需展开原记录核对{state}。{markers}", cites
    original = _selected_signal(version, row)
    value = f"{row.label}：{row.text}" + (f"。{original.detail}" if original and original.detail else "")
    if len(value) > MAX_ITEM_CHARS:
        # Do not retain a favourable fragment and drop a long exception. The
        # report entry remains fully available through the reference drawer.
        state = {"abnormal": "异常记录", "attention": "需进一步了解", "unknown": "待核实", "normal": "报告条目"}[row.category]
        return f"{label}：本版标为“{state}”。完整说明较长，条件与例外请展开本条查看；这里不截取片段作为判断。{markers}", cites
    source_note = "；演示数据，不代表真实企业" if record.kind == "demo" else ""
    if record.kind == "web" or row.id.startswith("reputation."):
        source_note += "；报道或投诉线索，不等于已查实的企业责任"
    return f"{value}（{_date(record)}{source_note}）。{markers}", cites


def _presentation(case: Case, version: Version, records: dict[str, RawRecord]):
    if version.report_presentation is None:
        return None
    # The existing validator owns fingerprint semantics. Only its isolated
    # version copy may be cleared; never mutate the user's historical snapshot.
    scoped = case.model_copy(update={"versions": [version.model_copy(deep=True)]})
    refresh_presentations(scoped)
    presentation = scoped.versions[0].report_presentation
    sources = version.sources or case.sources
    if not presentation or any(ref not in records or records[ref].kind not in PUBLIC_KINDS
                               or records[ref].coverage != Coverage.found or not records[ref].content
                               or (records[ref].source_id in sources and sources[records[ref].source_id].kind
                                   in {"user_material", "user_review"}) for ref in presentation.refs):
        return None
    return presentation


def build_overview_reply(case: Case, version: Version, question: str, route: str) -> ChatMessage:
    """Render an authorized saved-version overview with explicit reading scope."""
    if not any(saved is version or saved == version for saved in case.versions):
        raise ValueError("报告版本不属于当前案卷")
    records = _records(case, version)
    # A source's actual kind takes precedence over a possibly old/mislabelled
    # signal.source string. Private uploads and reviews are not company facts.
    private_ids = {raw.id for raw in case.raw if raw.id in version.raw_ids
                   and raw.kind in {"user_material", "user_review"}}
    private_sources = {sid for sid, source in (version.sources or case.sources).items()
                       if source.kind in {"user_material", "user_review"}}
    candidates = {}
    for signal in version.signals:
        for item in signal.items:
            candidates.setdefault(f"{signal.key}.{item.key}", []).append(item)
    conflicting = {ref: items for ref, items in candidates.items()
                   if len({item.model_dump_json() for item in items}) > 1}
    signal_view = [signal.model_copy(update={"items": [item for item in signal.items
                   if item.ref not in private_ids and item.source not in private_sources
                   and f"{signal.key}.{item.key}" not in conflicting]})
                   for signal in version.signals]
    company_view = version.model_copy(update={"signals": signal_view})
    overview = build_overview(company_view)  # Never trust a previously stored headline.
    rows = {row.id: row for row in overview.items}
    summary = overview.summary
    basis = summary.basis_ids if summary else []
    priorities = summary.priority_ids if summary else []
    purpose = perspective(version)
    strength_question = bool(re.search(r"厉害|牛|实力|强大|强不强|强[吗呀啊]", question))
    intro = ("“厉害”可以指技术、产品或经营表现，和适不适合你的选择并不是一回事。"
             "我先结合这份报告里已经形成的发现说说，不用处罚或投诉条数代替实力判断。"
             if route == "impression" and strength_question else
             "我会先看它与这次选择有关的情况。结合本版报告，有这几处值得你了解：")
    lines, citations = [intro], []
    if any(record.kind == "demo" for record in records.values()):
        lines.append("本版包含演示数据，以下相应条目不代表真实企业情况。")

    def cite(refs):
        citations.extend(ref for ref in refs if ref not in citations)

    # A short background can make the answer more useful than a list of fines.
    # Recompute descriptors from this version's structured company sources;
    # never trust arbitrary stored keyword labels or a company-name whitelist.
    background = next((keyword for keyword in company_keywords(version, list(records.values()))
                       if keyword.ref in records and records[keyword.ref].kind in PUBLIC_KINDS
                       and bool(records[keyword.ref].content)
                       and records[keyword.ref].source_id not in private_sources
                       and keyword.label != (version.company.status if version.company else None)
                       and len(keyword.basis) <= 300), None)
    if background:
        lines.append(f"基本背景：{background.basis}（{_date(records[background.ref])}）。[{background.ref}]")
        cite([background.ref])

    presentation = _presentation(case, version, records) if not conflicting else None
    valid_basis = not conflicting and bool(basis) and all(ref in rows and _supported(rows[ref], records) for ref in basis)
    # A huge signal value can also have been interpolated into the headline.
    # Do not copy just that value while dropping the row's conditions below.
    compact_basis = all((item := _selected_signal(version, rows[ref])) is not None
                        and len(f"{item.label}：{item.value}。{item.detail or ''}") <= MAX_ITEM_CHARS
                        for ref in basis if ref in rows)
    if presentation:
        lines.append("本版已绑定证据的预制摘要：\n" + presentation.title + "\n"
                     + presentation.note + "\n" + presentation.body + "\n"
                     + " ".join(f"[{ref}]" for ref in presentation.refs))
        cite(presentation.refs)
    elif summary and valid_basis and compact_basis:
        lines.append(f"从“{summary.perspective}”这个角度，本版发现是：{overview.headline}。\n"
                     f"{summary.explanation}\n" + " ".join(f"[{ref}]" for ref in basis))
        cite(basis)
    elif summary and summary.tone == "unknown":
        lines.append("本版部分关键企业资料尚不足以支持整体判断；下面把已有记录与尚待核实的部分分开说明。")
    else:
        lines.append("本版有需要进一步了解的事项；部分摘要依据尚需核对或完整说明较长，先看下方对应条目。")

    preferred = [*basis, *FOCUS_KEYS[purpose], "credit.status", *priorities, *rows]
    selected = list(dict.fromkeys(ref for ref in preferred if ref in rows and _supported(rows[ref], records)))[:3]
    # Three is a reading default, never a ceiling on serious record disclosure.
    serious = [ref for ref, row in rows.items() if row.status == Status.bad]
    selected += [ref for ref in serious if ref not in selected]
    if selected:
        facts = []
        for ref in selected:
            text, refs = _render_item(version, rows[ref], records)
            facts.append("• " + text)
            cite(refs)
        lines.append("报告依据：\n" + "\n".join(facts))

    if conflicting:
        # Existing citation IDs cannot unambiguously identify duplicate signal
        # rows. Do not quietly use the earlier row while the source drawer opens
        # the later one; show the gap and link their public raw records instead.
        disputed = []
        for ref, items in conflicting.items():
            public = [item for item in items if item.ref not in private_ids and item.source not in private_sources]
            if not public:
                continue
            label = public[0].label if len(public[0].label) <= 120 else "该核查项"
            refs = list(dict.fromkeys(item.ref for item in public
                                     if item.ref in records and records[item.ref].kind in PUBLIC_KINDS
                                     and records[item.ref].source_id == item.source))
            serious_note = "其中包含原报告异常状态，不能当作已排除。" if any(item.status == Status.bad for item in public) else ""
            disputed.append(f"{label}：本版同一条目编号对应多份不同说明，暂不合并为一个结论。{serious_note}"
                            + " ".join(f"[{raw_ref}]" for raw_ref in refs))
            cite(refs)
        if disputed:
            lines.append("需要核对的记录一致性：\n" + "\n".join(disputed))

    other = [ref for ref in priorities if ref in rows and ref not in selected]
    if other:
        labels = []
        for ref in other:
            row = rows[ref]
            label = row.label if len(row.label) <= 120 else "另一项关注记录"
            note = "（出处仍需核对）" if not _supported(row, records) else ""
            labels.append(f"{label}{note} [{ref}]")
        lines.append("其他关注项也保留在报告中：" + "；".join(labels) + "。")
        cite(other)

    gaps = [row for row in overview.items if row.category == "unknown" or row.gap]
    unbound = [row for row in overview.items if not _supported(row, records)]
    core_missing = [key for key in ("credit.status", "credit.penalties", "credit.abnormal",
                                   "credit.serious_illegal", "credit.dishonest") if key not in rows]
    if gaps or unbound or core_missing:
        gap_rows = list({row.id: row for row in [*gaps, *unbound]}.values())
        gap_labels = [f"{row.label if len(row.label) <= 120 else '该核查项'}："
                      + (row.text if row.gap and len(row.text) <= 200 else "出处或覆盖尚待核实")
                      + f" [{row.id}]" for row in gap_rows]
        lines.append("尚待核实：" + ("；".join(gap_labels) + "。" if gap_labels else "")
                     + (f"另有 {len(core_missing)} 项核心核查未形成报告条目。" if core_missing else "")
                     + "未覆盖、查询失败和未核实都不等于没有问题。")
        cite([row.id for row in gap_rows])

    lines.extend([SCOPE_NOTE, NEXT_QUESTIONS[purpose]])
    return ChatMessage(role="assistant", created_at=now(), version=version.no,
                       text="\n\n".join(lines), citations=citations, mode="template",
                       answer_kind="overview", answer_scope="report_snapshot", context_mode=None,
                       not_found=not bool(any(_supported(rows[ref], records) for ref in selected)
                                          or background or presentation))
