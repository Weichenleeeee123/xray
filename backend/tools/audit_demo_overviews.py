"""Offline structural audit of saved cases and prebuilt demo bundles.

Does not research a company, call paid services, change evidence, or write back
to an input file. A passing audit verifies traceability and consistency, not the
truth/completeness of a company's records or its suitability for a transaction.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analysis.overview import build_overview, refresh_overviews  # noqa: E402
from app.models import Case, PrebuiltProvenance  # noqa: E402


def audit_case(case: Case) -> dict:
    """Audit a deep copy; never expose needs, material text, raw bodies or chat."""
    original = case.model_dump(mode="json")
    projected = refresh_overviews(case.model_copy(deep=True))
    errors, warnings, versions = [], [], []
    raw = {record.id: record for record in projected.raw}
    if len(raw) != len(projected.raw):
        errors.append("duplicate_raw_id")
    if len({version.no for version in case.versions}) != len(case.versions):
        errors.append("duplicate_version_number")
    after = projected.model_dump(mode="json")
    for data in (original, after):
        for version in data["versions"]:
            version.pop("overview", None)
    if original != after:
        errors.append("overview_refresh_changed_evidence_or_provenance")

    for saved, version in zip(case.versions, projected.versions):
        overview = version.overview
        findings, notices = [], []
        expected = build_overview(version)
        if overview != expected:
            findings.append("derived_overview_mismatch")
        if saved.overview is not None and saved.overview != expected:
            findings.append("stored_overview_needs_refresh")
        if len({item.id for item in overview.items}) != len(overview.items):
            findings.append("duplicate_overview_item")
        observed = Counter(item.category for item in overview.items)
        if any(observed[key] != count for key, count in overview.counts.model_dump().items()):
            findings.append("count_does_not_match_visible_items")
        if overview.status == "bad" and not observed["abnormal"]:
            findings.append("anomaly_headline_without_abnormal_item")
        if observed["abnormal"] and overview.status != "bad":
            findings.append("abnormal_item_missing_from_headline")
        if observed["unknown"]:
            notices.append("coverage_gaps_remain")
        missing = sorted(set(version.raw_ids) - raw.keys())
        if missing:
            findings.append("missing_version_raw:" + ",".join(missing))

        evidence = []
        for item in overview.items:
            record = raw.get(item.ref) if item.ref else None
            source = version.sources.get(item.source)
            local_ref = bool(record and item.ref in version.raw_ids)
            source_link = bool(source and source.url)
            if item.ref and not local_ref:
                findings.append(f"broken_item_reference:{item.id}")
            elif item.category != "unknown" and not (local_ref or source_link):
                findings.append(f"missing_item_evidence:{item.id}")
            as_of = record.as_of if record else source.as_of if source else None
            if item.category != "unknown" and not as_of:
                notices.append(f"source_date_unspecified:{item.id}")
            evidence.append({
                "item": item.id, "category": item.category,
                "status": item.status.value, "gap": item.gap,
                "ref": item.ref, "source": item.source,
                "local_reference_resolves": local_ref,
                "source_link_present": source_link,
                "as_of": as_of,
                "retrieved_at": record.retrieved_at if record else None,
            })

        versions.append({
            "version": version.no, "created_at": version.created_at,
            "prebuilt": version.prebuilt.model_dump() if version.prebuilt else None,
            "schema_version": overview.schema_version,
            "status": overview.status, "headline": overview.headline,
            "counts": overview.counts.model_dump(),
            "source_dates": sorted({raw[rid].as_of for rid in version.raw_ids
                                    if rid in raw and raw[rid].as_of}),
            "failed_queries": [item.id for item in overview.items if item.gap == "failed"],
            "evidence": evidence, "errors": findings, "warnings": notices,
        })
    errors.extend(f"v{version['version']}:{error}" for version in versions for error in version["errors"])
    return {"company": case.case.company_name, "integrity": "fail" if errors else "pass",
            "errors": errors, "warnings": warnings, "versions": versions}


def audit_document(data: dict) -> dict:
    if "stages" not in data:
        result = audit_case(Case.model_validate(data))
        result.update(kind="saved_case", demo_id=None, built_at=None)
        result["warnings"].append("saved_case_is_not_a_prebuilt_demo_package")
        return result

    stages = data.get("stages") or []
    errors, warnings, results = [], [], []
    if not stages:
        errors.append("empty_prebuilt_package")
    if not data.get("demo_id"):
        errors.append("missing_demo_id")
    previous = None
    for index, stage in enumerate(stages):
        case = Case.model_validate(stage["case"])
        if len(case.versions) != index + 1 or case.current != index + 1:
            errors.append(f"stage_{index + 1}:version_sequence_mismatch")
        if previous is not None:
            old_versions = {version.no: version.model_dump(mode="json", exclude={"overview", "prebuilt"})
                            for version in previous.versions}
            now_versions = {version.no: version.model_dump(mode="json", exclude={"overview", "prebuilt"})
                            for version in case.versions}
            if any(now_versions.get(no) != version for no, version in old_versions.items()):
                errors.append(f"stage_{index + 1}:previous_version_changed")
            now_raw = {record.id: record for record in case.raw}
            if any(now_raw.get(record.id) != record for record in previous.raw):
                errors.append(f"stage_{index + 1}:previous_raw_changed")
        # Same provenance as replay: each saved version keeps the date of the
        # stage which first introduced it, not the latest supplement's date.
        for version in case.versions:
            origin_stage = stages[version.no - 1] if 0 < version.no <= len(stages) else {}
            expected = PrebuiltProvenance(
                demo_id=data.get("demo_id"),
                built_at=origin_stage.get("built_at") or data.get("built_at"))
            if not expected.built_at:
                errors.append(f"stage_{index + 1}:v{version.no}:missing_build_date")
            if version.prebuilt is not None and version.prebuilt != expected:
                errors.append(f"stage_{index + 1}:v{version.no}:provenance_mismatch")
            version.prebuilt = expected
        result = audit_case(case)
        result["stage"] = index + 1
        results.append(result)
        errors.extend(f"stage_{index + 1}:{error}" for error in result["errors"])
        previous = case
    if data.get("problems"):
        warnings.append("package_has_recorded_source_failures")
    companies = sorted({result["company"] for result in results})
    if len(companies) > 1:
        errors.append("company_changed_between_stages")
    return {"kind": "prebuilt_package", "demo_id": data.get("demo_id"),
            "built_at": data.get("built_at"), "company": companies[0] if len(companies) == 1 else None,
            "integrity": "fail" if errors else "pass", "errors": errors,
            "warnings": warnings, "stages": results}


def audit_paths(paths: list[Path], expected_companies: list[str] | None = None) -> dict:
    files = set()
    for path in paths:
        files.update(path.glob("*.json") if path.is_dir() else [path])
    reports = []
    for path in sorted(files):
        try:
            report = audit_document(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Pydantic errors can include private input; only expose the class.
            report = {"integrity": "fail", "errors": ["invalid_input:" + type(exc).__name__]}
        report["file"] = path.name
        reports.append(report)
    available = {report.get("company") for report in reports if report.get("kind") == "prebuilt_package"
                 and report["integrity"] == "pass"}
    return {"scope": "offline_structure_only",
            "note": "仅核对概况口径、引用与来源日期；不重新联网、不证明企业安全或资料完整，不修改输入文件。",
            "integrity": "pass" if reports and all(r["integrity"] == "pass" for r in reports) else "fail",
            "prebuilt_availability": {company: "available" if company in available else "not_prepared"
                                      for company in expected_companies or []},
            "reports": reports}


def to_markdown(audit: dict) -> str:
    lines = ["# 企业概况离线审计", "", audit["note"], "",
             f"结构检查：{audit['integrity']}。预制包存在不表示其资料已完整或已人工复核。", ""]
    for company, availability in audit["prebuilt_availability"].items():
        lines.append(f"- {company}：{'已有结构通过的预制包' if availability == 'available' else '尚未准备完整预制包'}")
    for report in audit["reports"]:
        lines.extend(["", f"## {report['file']} — {report.get('company') or '无法读取'}", "",
                      f"类型：{report.get('kind', 'invalid')}；结构检查：{report['integrity']}。"])
        for stage in report.get("stages", [report]):
            for version in stage.get("versions", []):
                counts = version["counts"]
                lines.extend(["", f"- 第 {version['version']} 版：{version['headline']}",
                              f"  正常 {counts['normal']} / 需了解 {counts['attention']} / 异常 {counts['abnormal']} / 待核实 {counts['unknown']}。",
                              f"  来源数据日期：{'、'.join(version['source_dates']) or '未注明'}。",
                              f"  预制来源：{json.dumps(version['prebuilt'], ensure_ascii=False)}。"])
                for notice in version["errors"] + version["warnings"]:
                    lines.append(f"  - {notice}")
        for notice in report.get("errors", []) + report.get("warnings", []):
            lines.append(f"- {notice}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="预制包目录、JSON 包或已保存案卷；不修改输入")
    parser.add_argument("--expect-company", action="append", default=[], help="报告该公司是否已有可用预制包")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    result = audit_paths(args.paths or [ROOT / "data" / "demo_prebuilt"], args.expect_company)
    print(to_markdown(result) if args.format == "markdown" else json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["integrity"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
