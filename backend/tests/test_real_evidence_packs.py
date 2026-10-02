"""Shipped public evidence must enter case records without inventing registry coverage."""
import pytest

from app.analysis.pipeline import load_services, new_case
from app.assistant import citable
from app.models import CaseIn
from app.scenarios import keyword_intake
from app.sources.packs import EvidencePacks


@pytest.mark.parametrize("company,source_id,record_date", [
    ("杭州巨鲸财富管理有限公司", "jujing_csrc_2024", "2024-09-13"),
    ("杭州银行股份有限公司", "hzbank_annual_2025", "2025-12-31"),
])
def test_public_evidence_enters_version_and_assistant_with_original_date(company, source_id, record_date):
    services = load_services()
    services.web = None
    services.amac_detail = None
    assert EvidencePacks.load().get(company) is not None
    case = new_case(CaseIn(company_name=company, need="了解这家公司"), keyword_intake("了解这家公司"), services)
    version = case.versions[0]
    record = next(r for r in case.raw if r.source_id == source_id)
    assert record.kind == "collected" and record.coverage == "found"
    assert record.as_of == record_date and record.retrieved_at.startswith("2026-10-02")
    assert record.url.startswith("https://")
    assert record.id in version.raw_ids and record.id in citable(case, version)
    # Public excerpts do not prove comprehensive GSXT/enforcement/complaint searches.
    assert version.company is None
    for sid in ("registry", "annual_report", "complaints"):
        assert next(r for r in case.raw if r.source_id == sid).coverage == "not_covered"
    assert not any(r.kind == "demo" and r.coverage == "found" for r in case.raw)


def test_vetted_penalty_pack_changes_deterministic_report_without_registry_coverage():
    services = load_services()
    services.web = None
    services.amac_detail = None
    case = new_case(CaseIn(company_name="杭州巨鲸财富管理有限公司", need="了解这家公司"), keyword_intake("了解这家公司"), services)
    version = case.versions[0]
    items = [i for s in version.signals for i in s.items if i.source.startswith("jujing_csrc_")]
    assert len(items) == 2
    penalty = next(i for i in items if i.source == "jujing_csrc_2024")
    measure = next(i for i in items if i.source == "jujing_csrc_2023")
    assert penalty.status == "bad" and measure.status == "bad"
    assert penalty.label == "行政处罚决定（人工采集）"
    assert "2024-09-13" in penalty.value and "36万元" in penalty.value
    assert measure.label == "行政监管措施（人工采集）"
    assert "警示函" in measure.value and "罚款" not in measure.value
    assert next(r for r in case.raw if r.id == penalty.ref).source_id == penalty.source
    assert case.sources[penalty.source].kind == "collected"
    assert "没有不良情况" not in version.onepager.headline
    assert "不代表处罚次数" in version.onepager.footer
    assert any("36万元" in line.text and penalty.ref in line.refs for line in version.onepager.found)
    assert version.company is None
    assert next(r for r in case.raw if r.source_id == "registry").coverage == "not_covered"


@pytest.mark.parametrize("change", [
    {"company": "别的公司有限公司"},
    {"url": "https://csrc.gov.cn.evil.example/penalty"},
    {"result": None},
    {"date": "not-a-date"},
    {"category": "公司宣传"},
])
def test_nonmatching_or_incomplete_pack_evidence_is_not_promoted_to_signal(change):
    data = {"当事企业": change.get("company", "杭州巨鲸财富管理有限公司"), "文书类别": change.get("category", "行政处罚决定"),
            "决定日期": change.get("date", "2024-09-13"), "企业处罚结果": change.get("result", "处36万元罚款")}
    services = load_services()
    services.web = None
    services.amac_detail = None
    services.packs = EvidencePacks([{"company": "杭州巨鲸财富管理有限公司", "as_of": "2026-10-02", "extra": [
        {"source_id": "vetted_pack", "source": {"url": change.get("url", "https://www.csrc.gov.cn/penalty"),
         "retrieved_at": "2026-10-02", "as_of": "2024-09-13"}, "data": data}]}])
    case = new_case(CaseIn(company_name="杭州巨鲸财富管理有限公司", need="了解这家公司"), keyword_intake("了解这家公司"), services)
    assert not any(i.source == "vetted_pack" for s in case.versions[0].signals for i in s.items)
