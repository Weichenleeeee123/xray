"""One evidence scope for the company headline, counts and five-axis outline.

This projection does not re-rate records, call a model, inspect a company's name,
or infer that an unqueried source is clear. Material claims and user reviews keep
their original places in the report and cannot rate the company overview.
"""
from app.models import Case, OverviewCounts, OverviewItem, ReportOverview, Status, Version
from app.scenarios import get_scenario
from app.analysis.company_summary import build_company_summary


ITEM_AXIS = {
    "credit.status": "basics", "credit.abnormal": "basics",
    "finance.paid_capital": "basics", "finance.insured": "basics", "finance.jobs": "basics",
    "finance.amac_scale": "basics", "risk.controller": "basics", "risk.changes": "basics",
}
SIGNAL_AXIS = {"risk": "qualify", "finance": "funds", "credit": "stability", "reputation": "news"}
QUIET_GAPS = {"listed", "reference", "not_applicable"}
MATERIAL_ITEMS = {
    "risk.payee", "risk.refund", "risk.upfront_fee", "risk.promise", "risk.return_promise",
    "risk.benchmark", "risk.disclosure", "risk.pressure", "risk.product_code", "risk.pf_threshold",
}
# These records are emitted only when a specific finding exists, not as a
# routine check. Absence of the optional finding is not a failed source query.
OPTIONAL_KEY_ITEMS = {"risk.amac_tips"}
# Routine company checks apply across scenarios, independent of materials.
TRUST_CORE_KEYS = {
    "credit.status": "登记状态", "credit.penalties": "行政处罚", "credit.abnormal": "经营异常名录",
    "credit.serious_illegal": "严重违法失信名单", "credit.dishonest": "失信被执行人",
}
CATEGORY = {Status.ok: "normal", Status.warn: "attention", Status.bad: "abnormal",
            Status.miss: "unknown", Status.none: "unknown"}
# A duplicate can never erase a warning, definite anomaly or uncovered source.
DEDUP_PRIORITY = {Status.ok: 0, Status.none: 1, Status.miss: 2, Status.warn: 3, Status.bad: 4}


def build_overview(version: Version) -> ReportOverview:
    by_id: dict[str, OverviewItem] = {}
    excluded_ids: set[str] = set()
    for signal in version.signals:
        for item in signal.items:
            key = f"{signal.key}.{item.key}"
            # Historical snapshots marked an unneeded private-fund registration
            # as "ok" without a gap. Keep that explanation in the signal, but do
            # not turn it into another successful company check. Actual AMAC
            # registrations and flagged records still participate normally.
            licensed_without_amac = (key == "risk.amac" and version.license.found
                                     and not version.amac.registered and item.status == Status.ok)
            if (item.gap in QUIET_GAPS or licensed_without_amac or key in MATERIAL_ITEMS
                    or item.source in {"material", "user_reviews"}
                    or item.source.startswith(("reg_", "param_"))
                    or key == "reputation.user_reviews"):
                excluded_ids.add(key)
                continue
            projected = OverviewItem(
                id=key, label=item.label, text=item.value, status=item.status,
                category=CATEGORY[item.status], gap=item.gap, source=item.source, ref=item.ref,
                axis=ITEM_AXIS.get(key, SIGNAL_AXIS[signal.key]))
            previous = by_id.get(key)
            if previous is None or DEDUP_PRIORITY[projected.status] > DEDUP_PRIORITY[previous.status]:
                by_id[key] = projected

    items = list(by_id.values())
    counts = OverviewCounts(**{category: sum(i.category == category for i in items)
                              for category in ("normal", "attention", "abnormal", "unknown")})
    # Only applicable company checks can establish coverage. No assertion id,
    # not-applicable licence, material gap or scenario-unrelated positive may
    # substitute for a missing key company check.
    expected_keys = {key for key in get_scenario(version.scenario).first_items
                     if key.partition(".")[0] in SIGNAL_AXIS and key not in MATERIAL_ITEMS
                     and (key not in excluded_ids or key in by_id)
                     and (key not in OPTIONAL_KEY_ITEMS or key in by_id)}
    missing_keys = expected_keys - by_id.keys()
    key_items = [by_id[key] for key in expected_keys if key in by_id]
    key_complete = bool(key_items) and not missing_keys and all(i.category == "normal" for i in key_items)
    if counts.abnormal:
        status = "bad"
    elif counts.attention:
        status = "warn"
    elif counts.normal and key_complete:
        status = "ok"
    else:
        status = "none"

    core_gaps = [key for key in TRUST_CORE_KEYS if key not in by_id or by_id[key].category == "unknown"]
    headline, summary = build_company_summary(version, items)
    detail = (f"本版适用公司核查 {len(items)} 项：{counts.normal} 项已核验正常，"
              f"{counts.attention} 项需了解，{counts.abnormal} 项异常记录，{counts.unknown} 项待核实。")
    if missing_keys:
        detail += f"关键核查尚有 {len(missing_keys)} 个项目未返回，不计为正常。"
    elif not key_items:
        detail += "本次需求的关键公司资料尚未形成完整核查。"
    if any(i.category == "unknown" for i in key_items):
        detail += "关键公司资料仍有缺口。"
    elif counts.unknown:
        detail += "正常仅指已核验项目，其余缺口仍需补查。"
    if core_gaps:
        detail += f"核心核查尚有 {len(core_gaps)} 项未完成：{'、'.join(TRUST_CORE_KEYS[key] for key in core_gaps)}。"
    return ReportOverview(status=status, trust_level="unknown", trust_label=headline, trust_note="",
                          headline=headline, detail=detail, counts=counts, items=items, summary=summary)


def refresh_overviews(case: Case) -> Case:
    """Refresh derived projections for every saved version, without changing evidence."""
    for version in case.versions:
        version.overview = build_overview(version)
    return case
