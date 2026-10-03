"""The headline, counts and axes must explain the same saved company records."""
import json

import pytest
from fastapi.testclient import TestClient

from app.analysis.overview import build_overview, refresh_overviews
from app.models import Case, ReportOverview, ResolveIn, Signal, SignalItem, Status
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


def complete_trust(**statuses):
    return "credit", [item(key, statuses.get(key, "ok"),
                           gap="not_covered" if statuses.get(key) == "none" else None)
                      for key in ("status", "penalties", "abnormal", "serious_illegal", "dishonest")]


def test_two_key_normals_and_outside_key_warning_share_one_scope():
    v = version(normal_credit(), ("reputation", [item("news_negative", "warn", source="qcc_news")]))
    summary = build_overview(v)
    assert summary.status == "warn"
    assert "报道或投诉线索" in summary.headline and summary.summary.tone == "attention"
    assert "核心核查尚有 3 项未完成" in summary.detail
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
    assert summary.headline == "发现监管风险提示"
    assert summary.summary.tone == "critical" and summary.trust_level == "unknown"
    assert summary.counts.abnormal == 1 and summary.counts.normal == 2
    assert summary.items[-1].status == Status.bad


def test_missing_key_check_is_unknown_not_anomaly_or_normal():
    v = version(("credit", [item("status", "none", gap="failed"), item("penalties")]),
                ("reputation", [item("news_negative", "warn")]))
    summary = build_overview(v)
    assert "报道或投诉线索" in summary.headline and summary.trust_level == "unknown"
    assert summary.counts.model_dump() == {"normal": 1, "attention": 1, "abnormal": 0, "unknown": 1}
    assert "关键公司资料仍有缺口" in summary.detail
    assert summary.items[0].gap == "failed"


@pytest.mark.parametrize("signals,status,counts", [
    ([normal_credit()], "ok", (2, 0, 0, 0)),
    ([normal_credit(), ("reputation", [item("news", "warn")])],
     "warn", (2, 1, 0, 0)),
    ([normal_credit(), ("reputation", [item("news", "warn"), item("media", "warn")])],
     "warn", (2, 2, 0, 0)),
    ([("credit", [item("status"), item("penalties", "warn")])],
     "warn", (1, 1, 0, 0)),
    ([("credit", [item("status", "none", gap="failed"), item("penalties", "warn")])],
     "warn", (0, 1, 0, 1)),
    ([("credit", [item("status", "warn")])],
     "warn", (0, 1, 0, 0)),
    ([("reputation", [item("news", "warn")])],
     "warn", (0, 1, 0, 0)),
    ([("credit", [item("status", "none", gap="failed"), item("penalties", "bad")])],
     "bad", (0, 0, 1, 1)),
    ([], "none", (0, 0, 0, 0)),
    ([complete_trust()], "ok", (5, 0, 0, 0)),
    ([complete_trust(), ("reputation", [item("news", "warn")])],
     "warn", (5, 1, 0, 0)),
    ([complete_trust(), ("reputation", [item("news", "warn"), item("media", "warn")])],
     "warn", (5, 2, 0, 0)),
    ([complete_trust(penalties="warn")],
     "warn", (4, 1, 0, 0)),
])
def test_findings_preserve_fact_status_counts_without_company_trust_rating(signals, status, counts):
    summary = build_overview(version(*signals))
    assert summary.status == status
    assert (summary.trust_level, summary.trust_label, summary.trust_note) == ("unknown", summary.headline, "")
    assert "信任度" not in summary.headline
    assert set(summary.summary.basis_ids) <= {i.id for i in summary.items}
    assert summary.counts.model_dump() == dict(zip(("normal", "attention", "abnormal", "unknown"), counts))
    assert sum(counts) == len(summary.items)


def test_non_key_gap_does_not_hide_key_attention_or_become_low_trust():
    v = version(complete_trust(penalties="warn"),
                ("finance", [item("cashflow", "none", gap="undisclosed")]))
    summary = build_overview(v)
    assert summary.status == "warn" and summary.summary.tone == "attention"
    assert summary.counts.unknown == 1 and "其余缺口仍需补查" in summary.detail


@pytest.mark.parametrize("scenario", ["general", "savings", "prepaid", "contract", "job", "takeover"])
def test_registration_only_never_implies_high_trust_in_any_scenario(scenario):
    v = version(("credit", [item("status")]))
    v.scenario = scenario
    summary = build_overview(v)
    assert summary.trust_level == "unknown" and summary.headline.startswith("登记信息已核实")
    assert summary.summary.tone == "unknown"
    assert summary.counts.model_dump() == {"normal": 1, "attention": 0, "abnormal": 0, "unknown": 0}
    assert len(summary.items) == 1 and "核心核查尚有 4 项未完成" in summary.detail
    if scenario == "prepaid":
        assert summary.status == "ok"  # The factual scenario classification is unchanged.


@pytest.mark.parametrize("key", ["status", "penalties", "abnormal", "serious_illegal", "dishonest"])
@pytest.mark.parametrize("state,level", [("missing", "unknown"), ("none", "unknown"),
                                         ("warn", "pending"), ("bad", "low")])
def test_each_common_core_check_affects_trust_even_outside_scenario_first_items(key, state, level):
    credit_key, rows = complete_trust(**({key: state} if state != "missing" else {}))
    if state == "missing":
        rows = [row for row in rows if row.key != key]
    summary = build_overview(version((credit_key, rows)))
    assert summary.trust_level == "unknown"  # A record state is never a company trust grade.
    if state in {"warn", "bad"}:
        assert f"credit.{key}" in summary.summary.priority_ids
    else:
        assert summary.summary.tone == "unknown"
    assert summary.counts.normal == 4
    assert len(summary.items) == (4 if state == "missing" else 5)
    assert summary.counts.unknown == (1 if state == "none" else 0)
    assert summary.counts.attention == (1 if state == "warn" else 0)
    assert summary.counts.abnormal == (1 if state == "bad" else 0)
    if state in {"missing", "none"}:
        assert "核心核查尚有 1 项未完成" in summary.detail
        if key not in {"status", "penalties"}:
            assert summary.status == "ok"


@pytest.mark.parametrize("gap", ["listed", "reference", "not_applicable"])
def test_quiet_marker_cannot_exempt_a_common_core_check_from_trust_coverage(gap):
    v = version(complete_trust())
    next(i for i in v.signals[0].items if i.key == "dishonest").gap = gap
    summary = build_overview(v)
    assert summary.status == "ok" and summary.trust_level == "unknown"
    assert summary.counts.normal == 4 and len(summary.items) == 4
    assert "核心核查尚有 1 项未完成：失信被执行人" in summary.detail


@pytest.mark.parametrize("scenario,extra", [
    ("general", []), ("prepaid", []),
    ("savings", [("risk", [item("bank_list"), item("amac"), item("scope")])]),
    ("contract", [("risk", [item("bank_list")])]),
    ("job", [("finance", [item("insured")])]),
    ("takeover", [("finance", [item("pledges"), item("executions"), item("tax_arrears"), item("mortgages")])]),
])
def test_high_trust_requires_common_core_and_scenario_coverage(scenario, extra):
    v = version(complete_trust(), *extra)
    v.scenario = scenario
    summary = build_overview(v)
    assert summary.trust_level == "unknown" and "信任度" not in summary.headline
    assert "核心核查" not in summary.detail
    assert summary.counts.normal == 5 + sum(len(rows) for _, rows in extra)
    if extra:
        v.signals[-1].items.pop()
        missing = build_overview(v)
        assert missing.trust_level == "unknown" and "项目未返回" in missing.detail


def test_core_gap_has_priority_over_key_attention_but_confirmed_bad_still_wins():
    v = version(complete_trust(penalties="warn", dishonest="none"))
    summary = build_overview(v)
    assert summary.status == "warn" and summary.trust_level == "unknown"
    v.signals[0].items[1].status = Status.bad
    summary = build_overview(v)
    assert summary.status == "bad" and summary.summary.tone == "attention"
    assert summary.counts.unknown == 1 and "核心核查尚有 1 项未完成" in summary.detail


def test_complete_core_with_non_key_gap_keeps_scoped_high_trust_and_visible_gap():
    v = version(complete_trust(), ("finance", [item("cashflow", "none", gap="undisclosed")]))
    summary = build_overview(v)
    assert summary.summary.tone == "neutral" and summary.headline == "已查关键项目未见异常，另有资料未覆盖"
    assert summary.counts.unknown == 1 and "其余缺口仍需补查" in summary.detail


def test_pre_trust_summary_schema_loads_with_compatible_defaults():
    old = build_overview(version(normal_credit())).model_dump()
    for field in ("trust_level", "trust_label", "trust_note"):
        old.pop(field)
    old["headline"] = "已核验信息整体正常"
    loaded = ReportOverview.model_validate(old)
    assert loaded.trust_level == "unknown" and loaded.trust_label == "资料较少" and loaded.trust_note == "需谨慎判断"
    assert loaded.counts.model_dump() == old["counts"] and loaded.status == old["status"]


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


def test_normal_scenario_checks_do_not_imply_high_trust_without_core_coverage():
    v = version(normal_credit(), ("finance", [item("cashflow", "none", gap="undisclosed")]))
    summary = build_overview(v)
    assert summary.status == "ok" and summary.summary.tone == "unknown"
    assert summary.trust_level == "unknown" and summary.counts.normal == 2
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
    assert "报道或投诉线索" in build_overview(v).headline


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


@pytest.mark.parametrize("legacy_shape", ["no_overview", "no_trust_fields"])
def test_api_projects_legacy_versions_after_ownership_check_without_rewriting_disk(monkeypatch, legacy_shape):
    import threading
    from app import main
    monkeypatch.setattr(main, "_stopping", threading.Event())
    with TestClient(main.app) as client:
        created = client.post("/api/cases", json={"company_name": DEMO_COMPANY, "need": "了解公司"})
        assert created.status_code == 200
        case = created.json()
        assert case["versions"][0]["overview"]["schema_version"] == 1
        current_summary = case["versions"][0]["overview"]
        assert current_summary["headline"] == current_summary["trust_label"] and current_summary["summary"]
        path = main.store._path(case["id"])
        legacy = json.loads(path.read_text(encoding="utf-8"))
        if legacy_shape == "no_overview":
            legacy["versions"][0].pop("overview")
        else:
            for field in ("trust_level", "trust_label", "trust_note"):
                legacy["versions"][0]["overview"].pop(field)
            legacy["versions"][0]["overview"]["headline"] = "旧版概况用语"
        original_signals = legacy["versions"][0]["signals"]
        path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        validated = Case.model_validate(legacy).versions[0].overview
        assert validated is None if legacy_shape == "no_overview" else validated.trust_level == "unknown"
        loaded = client.get(f"/api/cases/{case['id']}").json()
        response = client.get(f"/api/cases/{case['id']}/versions/1").json()
        assert response["version"]["overview"] == loaded["versions"][0]["overview"]
        assert response["version"]["overview"] == current_summary
        assert response["version"]["signals"] == original_signals
        assert json.loads(path.read_text(encoding="utf-8")) == legacy
        supplemented = client.post(f"/api/cases/{case['id']}/supplements",
                                   json={"kind": "material", "text": "服务合同：款项退还条件需另行书面确认。"})
        assert supplemented.status_code == 200
        saved = json.loads(path.read_text(encoding="utf-8"))["versions"]
        assert all(v["overview"]["schema_version"] == 1 for v in saved)
        assert all(v["overview"]["headline"] == v['overview']['trust_label'] and v['overview']['summary'] for v in saved)
        with TestClient(main.app) as outsider:
            assert outsider.get(f"/api/cases/{case['id']}").status_code == 404
