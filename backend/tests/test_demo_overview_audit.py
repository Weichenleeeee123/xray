"""Offline demo checks must not turn an incomplete snapshot into a positive one."""
from copy import deepcopy
import json

import pytest

from app.analysis.overview import build_overview
from app.models import Signal, SignalItem, Status
from tests.helpers import make_case
from tools.audit_demo_overviews import audit_case, audit_document, audit_paths, to_markdown


@pytest.fixture
def saved_case():
    case = make_case("杭州满盈禾康养健康咨询有限公司")
    version = case.versions[0]
    raw = case.raw[0]
    version.signals = [Signal(key="credit", title="信用", lede="", flags=1, items=[
        SignalItem(key="status", label="登记状态", value="已核查", status="ok",
                   source=raw.source_id, ref=raw.id),
        SignalItem(key="penalty", label="一般关注记录", value="需要了解处理情况", status="warn",
                   source=raw.source_id, ref=raw.id),
        SignalItem(key="registry", label="登记详情", value="本次尚未覆盖", status="none",
                   source=raw.source_id, ref=raw.id, gap="not_covered"),
    ])]
    version.overview = None
    version.need = "不应出现在审计输出的私人需求"
    raw.content = "不应出现在审计输出的材料正文"
    return case


def test_offline_audit_preserves_evidence_and_reports_missing_coverage(saved_case):
    before = saved_case.model_dump(mode="json")
    result = audit_case(saved_case)
    assert result["integrity"] == "pass"
    version = result["versions"][0]
    assert version["counts"] == {"normal": 1, "attention": 1, "abnormal": 0, "unknown": 1}
    assert version["status"] == "warn"
    assert "coverage_gaps_remain" in version["warnings"]
    assert saved_case.model_dump(mode="json") == before
    assert "私人需求" not in json.dumps(result, ensure_ascii=False)
    assert "材料正文" not in json.dumps(result, ensure_ascii=False)


def test_abnormal_record_is_never_rewritten_as_positive(saved_case):
    saved_case.versions[0].signals[0].items[1].status = Status.bad
    result = audit_case(saved_case)
    assert result["versions"][0]["counts"]["abnormal"] == 1
    assert result["versions"][0]["status"] == "bad"
    assert result["integrity"] == "pass"


def test_audit_rejects_broken_clickable_reference(saved_case):
    saved_case.versions[0].signals[0].items[1].ref = "R999999"
    result = audit_case(saved_case)
    assert result["integrity"] == "fail"
    assert any("broken_item_reference:credit.penalty" in error for error in result["errors"])


def test_audit_detects_stale_stored_headline(saved_case):
    version = saved_case.versions[0]
    version.overview = build_overview(version)
    version.overview.headline = "任意好评"
    result = audit_case(saved_case)
    assert result["integrity"] == "fail"
    assert "v1:stored_overview_needs_refresh" in result["errors"]
    assert version.overview.headline == "任意好评"


def test_bundle_audit_keeps_each_stages_build_date_without_changing_input(saved_case):
    first = saved_case.model_dump(mode="json")
    second = deepcopy(first)
    second["versions"].append({**deepcopy(first["versions"][0]), "no": 2, "trigger": "material"})
    second["current"] = 2
    bundle = {"demo_id": "T", "built_at": "2026-10-02 10:00", "stages": [
        {"case": first}, {"built_at": "2026-10-03 15:00", "case": second}]}
    before = deepcopy(bundle)
    result = audit_document(bundle)
    assert result["integrity"] == "pass"
    final = result["stages"][1]["versions"]
    assert [version["prebuilt"]["built_at"] for version in final] == ["2026-10-02 10:00", "2026-10-03 15:00"]
    assert final[0]["source_dates"] == result["stages"][0]["versions"][0]["source_dates"]
    assert bundle == before


def test_bundle_without_generation_date_is_not_ready(saved_case):
    result = audit_document({"demo_id": "T", "stages": [{"case": saved_case.model_dump(mode="json")}]})
    assert result["integrity"] == "fail"
    assert any("missing_build_date" in error for error in result["errors"])


def test_bundle_cannot_replace_prior_evidence_when_adding_a_stage(saved_case):
    first = saved_case.model_dump(mode="json")
    second = deepcopy(first)
    second["versions"].append({**deepcopy(first["versions"][0]), "no": 2})
    second["current"] = 2
    second["raw"][0]["as_of"] = "2099-01-01"
    second["versions"][0]["signals"][0]["items"][1]["status"] = "ok"
    result = audit_document({"demo_id": "T", "built_at": "2026-10-03", "stages": [
        {"case": first}, {"case": second}]})
    assert result["integrity"] == "fail"
    assert "stage_2:previous_version_changed" in result["errors"]
    assert "stage_2:previous_raw_changed" in result["errors"]


def test_saved_case_does_not_claim_a_real_company_prebuilt_package(tmp_path, saved_case):
    path = tmp_path / "case.json"
    saved_case.case.company_name = "杭州银行股份有限公司"
    path.write_text(saved_case.model_dump_json(), encoding="utf-8")
    before = path.read_bytes()
    result = audit_paths([path], ["杭州银行股份有限公司", "华为技术有限公司"])
    assert result["integrity"] == "pass"
    assert set(result["prebuilt_availability"].values()) == {"not_prepared"}
    assert "尚未准备完整预制包" in to_markdown(result)
    assert path.read_bytes() == before


def test_invalid_saved_data_does_not_print_private_payload(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"case":{"need":"private-secret"}}', encoding="utf-8")
    result = audit_paths([path])
    assert result["integrity"] == "fail"
    assert "private-secret" not in json.dumps(result)


def test_missing_directory_is_not_reported_as_success(tmp_path):
    assert audit_paths([tmp_path / "absent"])["integrity"] == "fail"
