"""Persist material appendices from grounded analysis, including legacy versions.

Company snapshots remain available for audit. An appendix only includes claims
quoted in the newly submitted material, never unrelated older claims.
"""
import re

from app.models import Case, MaterialAnalysis


def _flat(value: str) -> str:
    return re.sub(r"\s+", "", value)


def ensure_material_analyses(case: Case) -> Case:
    saved = {a.report_version for a in case.material_analyses}
    raw = {r.id: r for r in case.raw}
    versions = sorted(case.versions, key=lambda v: v.no)
    for prev, current in zip(versions, versions[1:]):
        if current.trigger not in ("material", "reply") or current.no in saved:
            continue
        new_ids = set(current.raw_ids) - set(prev.raw_ids)
        materials = [raw[rid] for rid in current.raw_ids if rid in new_ids and rid in raw
                     and raw[rid].kind == "user_material" and isinstance(raw[rid].content, str)]
        if not materials:
            continue  # An incomplete legacy snapshot cannot supply invented evidence.
        ids = {r.id for r in materials}
        findings = []
        for claim in current.assertions:
            quotes = [q for q in claim.quotes if _flat(q) and any(_flat(q) in _flat(r.content) for r in materials)]
            refs = [r.id for r in materials if any(_flat(q) in _flat(r.content) for q in quotes)]
            if quotes and refs:
                findings.append(claim.model_copy(deep=True, update={"quotes": quotes, "refs": refs}))
        observations = [j.model_copy(deep=True) for j in current.judgments
                        if j.id.startswith("contract.") and any(b.ref in ids for b in j.basis)]
        attention = sum(a.color in ("red", "amber") for a in findings)
        unknown = sum(a.color == "grey" for a in findings)
        if attention:
            summary = f"发现 {attention} 项需要留意的材料说法"
        elif unknown:
            summary = f"有 {unknown} 项说法仍需补充依据"
        elif observations:
            summary = f"提取 {len(observations)} 项合同核对要点"
        elif findings:
            summary = "已识别的说法与现有记录相符"
        else:
            summary = "尚未提取到可核对的具体说法"
        linked = {a.id for a in findings} | {j.id for j in observations}
        questions = [q.model_copy(deep=True) for q in current.questions if linked.intersection(q.linked)]
        changes = [c.model_copy(deep=True) for c in current.judgment_changes
                   if c.kind != "same" and ids.intersection(c.because)]
        case.material_analyses.append(MaterialAnalysis(
            id=f"MA{current.no}", created_at=current.created_at, kind=current.trigger,
            title="、".join(r.title for r in materials), base_version=prev.no, report_version=current.no,
            raw_ids=[r.id for r in materials], need=current.need, summary=summary,
            findings=findings, observations=observations, changes=changes, questions=questions))
        saved.add(current.no)
    return case
