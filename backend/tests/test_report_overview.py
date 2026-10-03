"""The headline, counts and axes must explain the same saved company records."""
import json

import pytest
from fastapi.testclient import TestClient

from app.analysis.overview import build_overview, refresh_overviews
from app.models import Case, ResolveIn, Signal, SignalItem, Status
from tests.helpers import DEMO_COMPANY, add, make_case


def item(key, status="ok", *, source="registry", gap=None):
    return SignalItem(key=key, label=f"核查{key}", value=f"记录{key}", status=status,
                      source=source, ref="R1", gap=gap)


def version(*signals):
    report = make_case(DEMO_COMPANY, need="了解这家公司的公开资料").versions[0]
    report.signals = [Signal(key=key, title=key, lede="已保存的记录", flags=0, items=items)
                      for key, items in signals]
    return report


def normal_credit():
    return "credit", [item("status"), item("penalties")]


def test_two_key_normals_and_outside_key_warning_share_one_scope():
    v = version(normal_credit(), ("reputation", [item("news_negative", "warn", source="qcc_news")]))
    summary = build_overview(v)
    assert summary.status == "warn"
    assert summary.headline == "基础核查正常，另有事项需了解"
    assert summary.counts.model_dump() == {"normal": 2, "attention": 1, "abnormal": 0, "unknown": 0}
    assert summary.items[-1].id == "reputation.news_negative"
    assert summary.items[-1].axis == "news" and summary.items[-1].ref == "R1"
    assert "1 项需了解" in summary.detail and "0 项异常记录" in summary.detail


@pytest.mark.parametrize("name", ["华为技术有限公司", "杭州银行股份有限公司", "普通测试有限公司"])
def test_real_bad_record_cannot_be_masked_by_company_name_or_positive_items(name):
    v = version(normal_credit(), ("risk", [item("regulator_warning", "bad", source="web_official")]))
    v.company.name = name
    summary = build_overview(v)
    assert summary.status == "bad"
    assert summary.headline == "发现异常记录，建议重点核实"
    assert summary.counts.abnormal == 1 and summary.counts.normal == 2
    assert summary.items[-1].status == Status.bad


def test_missing_key_check_is_unknown_not_anomaly_or_normal():
    v = version(("credit", [item("status", "none", gap="failed"), item("penalties")]),
                ("reputation", [item("news_negative", "warn")]))
    summary = build_overview(v)
    assert summary.headline == "有事项需了解，建议进一步核实"
    assert summary.counts.model_dump() == {"normal": 1, "attention": 1, "abnormal": 0, "unknown": 1}
    assert "关键公司资料仍有缺口" in summary.detail
    assert summary.items[0].gap == "failed"


@pytest.mark.parametrize("status,gap", [("none", "not_covered"), ("none", "not_found"),
                                         ("none", "failed"), ("miss", None)])
def test_open_gaps_are_counted_once_without_negative_rating(status, gap):
    summary = build_overview(version(("credit", [item("status", status, gap=gap)])))
    assert summary.status == "none"
    assert summary.counts.unknown == 1
    assert summary.counts.attention == summary.counts.abnormal == summary.counts.normal == 0
    assert summary.items[0].status == status


def test_not_applicable_is_never_counted_as_passed_even_with_ok_status():
    v = version(("risk", [item("bank_list", "ok", gap="not_applicable"),
                           item("listed", "none", gap="listed"),
                           item("reference", "none", gap="reference")]))
    summary = build_overview(v)
    assert summary.status == "none" and summary.items == []
    assert summary.counts.normal == 0


def test_material_rules_reviews_and_assertions_stay_out_of_company_summary():
    v = version(normal_credit(), ("risk", [item("payee", "bad", source="nfra_bank_list"),
                  item("pressure", "bad", source="material"), item("promise", "bad", source="reg_wm_sales"),
                  item("product_code", "miss", source="wm_code", gap="needs_input"),
                  item("rule", "bad", source="param_capital")]),
                  ("reputation", [item("user_reviews", "warn", source="user_reviews")]))
    bad_material = add(make_case(DEMO_COMPANY), "material", "收款户名：张某某，保本保息年化收益18%").versions[-1]
    v.assertions, v.missing = bad_material.assertions, bad_material.missing
    before = v.model_dump()
    summary = build_overview(v)
    assert summary.status == "ok" and summary.counts.normal == 2
    assert len(summary.items) == 2
    assert v.model_dump() == before  # This projection must never rewrite original evidence.


def test_duplicate_ids_keep_stronger_record_and_counts_equal_visible_items():
    v = version(("credit", [item("status"), item("penalties"), item("penalties", "warn"),
                              item("penalties", "bad"), item("abnormal", "none", gap="failed")]))
    summary = build_overview(v)
    assert len(summary.items) == 3
    assert len({i.id for i in summary.items}) == len(summary.items)
    assert sum(summary.counts.model_dump().values()) == len(summary.items)
    assert summary.counts.abnormal == 1 and summary.counts.attention == 0
    assert {i.id: i.axis for i in summary.items} == {
        "credit.status": "basics", "credit.penalties": "stability", "credit.abnormal": "basics"}


def test_positive_headline_requires_applicable_key_checks_and_keeps_other_gaps():
    v = version(normal_credit(), ("finance", [item("cashflow", "none", gap="undisclosed")]))
    summary = build_overview(v)
    assert summary.status == "ok" and summary.headline == "已核验信息整体正常"
    assert summary.counts.unknown == 1 and "其余缺口仍需补查" in summary.detail
    v.signals = v.signals[1:]
    v.signals[0].items = [item("cashflow")]
    assert build_overview(v).status == "none"  # A non-key positive does not establish key coverage.


def test_absent_expected_key_check_cannot_silently_count_as_completed():
    v = version(("credit", [item("status")]))
    summary = build_overview(v)
    assert summary.status == "none"
    assert summary.counts.normal == 1 and len(summary.items) == 1
    assert "关键核查尚有 1 个项目未返回" in summary.detail
    v.signals.append(Signal(key="reputation", title="口碑", lede="", flags=1,
                           items=[item("news_negative", "warn")]))
    assert build_overview(v).headline == "有事项需了解，建议进一步核实"


def test_explicit_not_applicable_key_is_excluded_but_company_needs_input_stays_visible():
    v = version(("credit", [item("status"), item("penalties", "ok", gap="not_applicable")]))
    assert build_overview(v).status == "ok"
    v.signals[0].items[1] = item("penalties", "none", gap="needs_input")
    summary = build_overview(v)
    assert summary.status == "none" and summary.counts.unknown == 1
    assert summary.items[-1].gap == "needs_input"


def test_optional_private_fund_tip_does_not_make_bank_coverage_incomplete():
    v = version(("risk", [item("bank_list"), item("amac", "ok", gap="not_applicable"),
                           item("scope"), item("product_code", "none", source="material", gap="needs_input")]))
    v.scenario = "savings"
    summary = build_overview(v)
    assert summary.status == "ok" and summary.counts.normal == 2


def test_real_bank_does_not_count_unneeded_amac_registration_as_passed():
    case = make_case("杭州银行股份有限公司", need="想了解这家银行的登记和资质")
    v = case.versions[0]
    assert v.license.found and not v.amac.registered
    amac = next(i for s in v.signals if s.key == "risk" for i in s.items if i.key == "amac")
    assert amac.status == "ok" and amac.gap == "not_applicable"
    assert "不需要私募登记" in amac.value
    expected = v.overview.model_dump()
    assert "risk.bank_list" in {i.id for i in v.overview.items}
    assert "risk.amac" not in {i.id for i in v.overview.items}
    amac.gap = None  # The historical snapshot shown in the browser.
    assert build_overview(v).model_dump() == expected
    assert amac.gap is None  # Compatibility projection does not rewrite saved evidence.


@pytest.mark.parametrize("status,category", [("warn", "attention"), ("bad", "abnormal")])
def test_old_licensed_bank_with_flagged_amac_record_keeps_the_record(status, category):
    v = make_case("杭州银行股份有限公司", need="了解这家银行").versions[0]
    amac = next(i for s in v.signals if s.key == "risk" for i in s.items if i.key == "amac")
    amac.gap, amac.status = None, Status(status)
    found = next(i for i in build_overview(v).items if i.id == "risk.amac")
    assert found.category == category and found.status == status


def test_existing_amac_registration_is_kept_even_for_licensed_company():
    v = make_case("杭州银行股份有限公司", need="了解这家银行").versions[0]
    amac = next(i for s in v.signals if s.key == "risk" for i in s.items if i.key == "amac")
    v.amac.registered = True
    amac.gap, amac.value = None, "已登记"
    found = next(i for i in build_overview(v).items if i.id == "risk.amac")
    assert found.category == "normal"


def test_registered_private_fund_from_real_saved_list_remains_in_overview():
    v = make_case("杭州巨鲸财富管理有限公司", need="了解这家公司的私募基金管理人登记").versions[0]
    assert v.amac.registered
    found = next(i for i in v.overview.items if i.id == "risk.amac")
    assert found.category in {"normal", "attention"} and found.source == "amac"


def test_new_and_material_versions_get_summary_without_changing_company_scope():
    case = make_case(DEMO_COMPANY)
    before = case.versions[0].overview.model_dump()
    add(case, "material", "收款户名：张某某，保本保息年化收益18%")
    assert case.versions[-1].overview.model_dump() == before
    old_signals = [s.model_dump() for s in case.versions[0].signals]
    refresh_overviews(case)
    assert [s.model_dump() for s in case.versions[0].signals] == old_signals


def test_human_resolution_refreshes_current_overview_and_preserves_old_version():
    from app.analysis.pipeline import resolve
    case = make_case(DEMO_COMPANY)
    first = case.versions[0].model_dump()
    abnormal = {i.id for i in case.versions[0].overview.items if i.category == "abnormal"}
    judgment = next(j for j in case.versions[0].judgments
                    if j.id.startswith("record.") and j.target in abnormal)
    resolve(case, ResolveIn(judgment_id=judgment.id, action="withdrawn", by="核查人员", note="来源主体核对后排除"))
    summary = case.versions[-1].overview
    assert summary.counts.abnormal == first["overview"]["counts"]["abnormal"] - 1
    assert next(i for i in summary.items if i.id == judgment.target).category == "unknown"
    assert case.versions[0].model_dump() == first


def test_api_projects_legacy_versions_after_ownership_check_without_rewriting_disk(monkeypatch):
    import threading
    from app import main
    monkeypatch.setattr(main, "_stopping", threading.Event())
    with TestClient(main.app) as client:
        created = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": "了解公司"})
        assert created.status_code == 200
        case = created.json()
        assert case["versions"][0]["overview"]["schema_version"] == 1
        path = main.store._path(case["id"])
        legacy = json.loads(path.read_text())
        legacy["versions"][0].pop("overview")
        original_signals = legacy["versions"][0]["signals"]
        path.write_text(json.dumps(legacy, ensure_ascii=False))
        assert Case.model_validate(legacy).versions[0].overview is None
        loaded = client.get(f"/api/cases/{case['id']}").json()
        response = client.get(f"/api/cases/{case['id']}/versions/1").json()
        assert response["version"]["overview"] == loaded["versions"][0]["overview"]
        assert response["version"]["signals"] == original_signals
        assert "overview" not in json.loads(path.read_text())["versions"][0]
        supplemented = client.post(f"/api/cases/{case['id']}/supplements",
                                   json={"kind": "material", "text": "服务合同：款项退还条件需另行书面确认。"})
        assert supplemented.status_code == 200
        assert all(v["overview"]["schema_version"] == 1 for v in json.loads(path.read_text())["versions"])
        with TestClient(main.app) as outsider:
            assert outsider.get(f"/api/cases/{case['id']}").status_code == 404
