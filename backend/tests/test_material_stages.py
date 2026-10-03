"""Material supplements reuse enterprise evidence and add visible document findings."""
from copy import deepcopy

import pytest

from app import main, progress
from app.analysis import pipeline
from app.analysis.materials import ensure_material_analyses
from app.models import ResolveIn, SupplementIn
from tests.helpers import DEMO_COMPANY, make_case, svc


def supplement(case, body, intake, services):
    return ensure_material_analyses(pipeline.supplement(case, body, intake, services))


@pytest.mark.parametrize("kind", ["material", "reply"])
def test_material_only_reuses_enterprise_snapshot(monkeypatch, kind):
    case = make_case(DEMO_COMPANY)
    first = deepcopy(case.versions[0].model_dump())
    def unexpected(*args, **kwargs):
        pytest.fail("a material supplement must not collect or rebuild enterprise research")
    monkeypatch.setattr(pipeline, "_collect_into", unexpected)
    monkeypatch.setattr(pipeline, "build_version", unexpected)
    result = supplement(case, SupplementIn(kind=kind, text="收款户名：张某某，年化收益9%，保本保息"), None, svc)
    v = result.versions[-1]
    assert result.versions[0].model_dump() == first
    for field in ("company", "license", "amac", "signals", "charts", "sources", "company_keywords"):
        assert v.model_dump()[field] == first[field]
    assert v.no == 2 and v.trigger == kind
    assert any(a.id == "A7" for a in v.assertions)
    analysis = result.material_analyses[-1]
    assert analysis.base_version == 1 and analysis.report_version == 2
    assert analysis.raw_ids and set(analysis.raw_ids) <= set(v.raw_ids)
    assert any(f.id == "A7" for f in analysis.findings)


def test_repeated_materials_keep_first_snapshot_and_prior_versions():
    case = make_case(DEMO_COMPANY)
    supplement(case, SupplementIn(kind="reply", text="随时可退，全额退款"), None, svc)
    old = [v.model_dump() for v in case.versions]
    supplement(case, SupplementIn(kind="material", title="协议节选", text="服务协议\n第一条 收款户名：张某某\n第二条 付款后概不退款，违约金20%。"), None, svc)
    v = case.versions[-1]
    assert [x.model_dump() for x in case.versions[:-1]] == old
    assert len(case.material_analyses) == 2
    assert case.material_analyses[-1].base_version == 2
    assert len(case.material_analyses[-1].raw_ids) == 1
    assert any(a.id == "A8" and a.color in ("red", "amber") for a in v.assertions)
    assert any(j.id.startswith("contract.refund.") for j in v.judgments)


def test_supplement_progress_has_only_processing_steps():
    event = progress.begin("supplement", DEMO_COMPANY, intake=False)
    assert not any(s["lookup"] for s in event["steps"])
    assert [s["id"] for s in event["steps"]] == ["rules", "plain"]


def test_demo_first_inputs_have_no_materials_and_material_is_first_supplement():
    for demo in main._demo_cases():
        if demo.ready:
            assert not demo.input.material_text
            assert not demo.input.material_title
            assert demo.supplements and demo.supplements[0].kind == "material"


def test_contract_company_can_be_second_party_and_blanks_are_unconfirmed():
    text = (f"服务合同\n甲方：李某某\n乙方：{DEMO_COMPANY}\n"
            "第一条 无需支付保证金。\n第二条 付款后概不退款。\n"
            "第三条 提前解除合同须支付20%违约金。\n签订日期：____年__月__日\n甲方签字：____\n乙方盖章：____")
    case = make_case(DEMO_COMPANY)
    supplement(case, SupplementIn(kind="material", title="服务合同", text=text), None, svc)
    v = case.versions[-1]
    parties = [j for j in v.judgments if j.id.startswith("contract.party.")]
    assert any(DEMO_COMPANY in j.text and j.state == "holds" for j in parties)
    assert not any("李某某" in j.text and j.state == "needs_check" for j in parties)
    assert not any(j.id.startswith("contract.prepay.") for j in v.judgments)
    assert any(j.id.startswith("contract.refund.") for j in v.judgments)
    assert any(j.id.startswith("contract.breach.") for j in v.judgments)
    assert any(j.id.startswith("contract.blank.") and "日期" in j.text for j in v.judgments)
    sign = [j for j in v.judgments if j.id.startswith("contract.signature.")]
    assert sign and sign[0].state == "unconfirmed"
    for j in v.judgments:
        if j.id.startswith(("contract.refund.", "contract.breach.", "contract.signature.")):
            assert j.basis[0].ref in case.material_analyses[-1].raw_ids
            assert j.basis[0].quote in text


def test_unrelated_material_still_has_a_document_analysis():
    case = make_case(DEMO_COMPANY)
    supplement(case, SupplementIn(kind="material", title="停水通知", text="明天上午小区停水两小时。"), None, svc)
    analysis = case.material_analyses[-1]
    assert analysis.raw_ids and analysis.summary == "尚未提取到可核对的具体说法"


def test_contract_findings_from_different_documents_have_unique_citable_ids():
    case = make_case(DEMO_COMPANY)
    for text in ("第一条 付款后概不退款。", "第一条 可以全额退款。"):
        supplement(case, SupplementIn(kind="material", title="合同", text=f"服务合同\n甲方：{DEMO_COMPANY}\n{text}"), None, svc)
    v = case.versions[-1]
    ids = [j.id for j in v.judgments]
    assert len(set(ids)) == len(ids)
    parties = [j for j in v.judgments if j.id.startswith("contract.party.")]
    assert {j.basis[0].ref for j in parties} == {rid for a in case.material_analyses for rid in a.raw_ids}


def test_partner_bank_claim_does_not_query_current_bank_index(monkeypatch):
    case = make_case(DEMO_COMPANY)
    def unexpected(*args, **kwargs):
        pytest.fail("new partner names need their own evidence, not another entity's lookup")
    monkeypatch.setattr(svc.licenses, "lookup", unexpected)
    supplement(case, SupplementIn(kind="material", text="资金由杭州银行存管"), None, svc)
    partner = next(a for a in case.versions[-1].assertions if a.id == "A3")
    assert partner.checks[0].status == "none"
    assert partner.checks[0].source == "material"


@pytest.mark.parametrize("target", ["record.risk.bank_list", "check.A7"])
def test_unrelated_supplement_preserves_manual_resolution_and_change_summary(target):
    case = make_case(DEMO_COMPANY)
    supplement(case, SupplementIn(kind="material", text="收款户名：张某某"), None, svc)
    pipeline.resolve(case, ResolveIn(judgment_id=target, action="clarified", by="核对者", note="已核实原件"))
    before = next(j for j in case.versions[-1].judgments if j.id == target).model_dump()
    supplement(case, SupplementIn(kind="material", text="小区停水通知"), None, svc)
    v = case.versions[-1]
    assert next(j for j in v.judgments if j.id == target).model_dump() == before
    assert all(c.kind == "unchanged" for c in v.changes if c.target == target.split(".", 1)[1])


def test_b2b_contract_lists_other_party_without_false_company_mismatch_and_covers_gaps():
    case = make_case(DEMO_COMPANY)
    text = f"服务合同\n甲方：合作客户有限公司\n乙方：{DEMO_COMPANY}\n第一条 提供日常咨询服务。"
    supplement(case, SupplementIn(kind="material", text=text), None, svc)
    judgments = case.versions[-1].judgments
    partner = next(j for j in judgments if j.id.startswith("contract.party.") and "合作客户" in j.text)
    assert partner.state == "unconfirmed" and "写错" not in partner.plain
    for category in ("refund", "payment", "breach"):
        check = next(j for j in judgments if j.id.startswith(f"contract.{category}."))
        assert check.state == "unconfirmed" and "未见" in check.text


def test_contract_only_findings_reach_saved_and_exported_onepager():
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    first = client.post("/api/cases", json={"company_name": DEMO_COMPANY}).json()
    result = client.post(f"/api/cases/{first['id']}/supplements", json={
        "kind": "material", "title": "服务合同", "text": "服务合同\n第一条 提前解除合同，剩余费用不予退还。\n第二条 违约金20%。"}).json()
    saved = result["versions"][-1]["onepager"]
    for page in [saved, *[client.get(f"/api/cases/{first['id']}/onepager", params={"audience": a}).json() for a in ("family", "teller")]]:
        lines = page["mismatch"] + page["unknown"] + page["next_steps"]
        assert any("退款" in line["text"] or "退还" in line["text"] for line in lines)
        assert any("20%" in line["text"] for line in lines)
        assert any(any(ref.startswith("contract.") for ref in line["refs"]) for line in lines)


@pytest.mark.parametrize("category", ["party", "prepay", "blank"])
def test_legacy_contract_identity_keeps_resolution_on_unrelated_reply(category):
    from app.analysis.judgments import _stable
    case = make_case(DEMO_COMPANY)
    line = "第一条 开始服务前支付服务费100元。"
    supplement(case, SupplementIn(kind="material", title="旧合同", text=f"服务合同\n甲方：{DEMO_COMPANY}\n{line}"), None, svc)
    j = next(j for j in case.versions[-1].judgments if j.id.startswith(f"contract.{category}."))
    legacy_key = {"party": DEMO_COMPANY, "prepay": line, "blank": "旧合同签订日期｜双方的签字或盖章"}[category]
    j.id = f"contract.{category}.{_stable(legacy_key)}"
    if category == "blank":
        j.text = "这份材料上没有签订日期，也没有双方的签字或盖章"
    pipeline.resolve(case, ResolveIn(judgment_id=j.id, action="withdrawn", by="核对者", note="已核对完整原件"))
    previous = deepcopy(case.versions[-1].model_dump())
    old = next(item for item in case.versions[-1].judgments if item.id == j.id)
    supplement(case, SupplementIn(kind="reply", text="明天再联系。"), None, svc)
    current = next(item for item in case.versions[-1].judgments if item.id == j.id)
    assert current.state == "withdrawn"
    assert current.history == old.history and current.since == old.since
    assert not any(c.kind == "dropped" and c.target == j.id for c in case.versions[-1].judgment_changes)
    assert case.versions[-2].model_dump() == previous


def test_party_drafting_alias_does_not_change_company_identity():
    case = make_case(DEMO_COMPANY)
    supplement(case, SupplementIn(kind="material", text=f"服务合同\n甲方：客户有限公司\n乙方：{DEMO_COMPANY}（以下简称乙方）\n第一条 日常咨询服务。"), None, svc)
    parties = [j for j in case.versions[-1].judgments if j.id.startswith("contract.party.")]
    assert any(DEMO_COMPANY in j.text and j.state == "holds" for j in parties)
    assert not any(j.state == "needs_check" for j in parties)


@pytest.mark.parametrize("kind,refresh", [("need", False), ("material", True), ("reply", True)])
def test_changed_need_or_explicit_refresh_still_collects_enterprise_data(monkeypatch, kind, refresh):
    from unittest.mock import Mock
    from app.scenarios import keyword_intake
    case = make_case(DEMO_COMPANY)
    collect = Mock(wraps=pipeline._collect_into)
    monkeypatch.setattr(pipeline, "_collect_into", collect)
    body = SupplementIn(kind=kind, text="我想在这家公司入职", refresh_sources=refresh)
    supplement(case, body, keyword_intake(body.text) if kind == "need" else None, svc)
    collect.assert_called_once()
    event = progress.begin("supplement", DEMO_COMPANY, intake=kind == "need", refresh_sources=refresh)
    assert any(s["lookup"] for s in event["steps"])


def test_api_appendix_uses_snapshot_and_new_contract_findings(monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    initial = client.post("/api/cases", json={"company_name": DEMO_COMPANY}).json()
    def unexpected(*args, **kwargs):
        pytest.fail("the public supplement API must reuse the saved company snapshot")
    monkeypatch.setattr(pipeline, "_collect_into", unexpected)
    monkeypatch.setattr(pipeline, "build_version", unexpected)
    response = client.post(f"/api/cases/{initial['id']}/supplements/stream", json={
        "kind": "material", "title": "合同", "text": "服务合同\n第一条 付款后不得退款。\n第二条 违约金20%。"})
    import json
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [s["id"] for s in events[0]["steps"]] == ["rules", "plain"]
    result = events[-1]["case"]
    assert result["versions"][0] == initial["versions"][0]
    appendix, = result["material_analyses"]
    assert appendix["base_version"] == 1 and appendix["report_version"] == 2
    categories = {j["id"].split(".")[1] for j in appendix["observations"]}
    assert {"refund", "breach", "payment"} <= categories
    assert set(appendix["raw_ids"]) == {r["id"] for r in result["raw"] if r["source_id"] == "material"}
    for field in ("company", "signals", "charts", "sources", "company_keywords"):
        assert result["versions"][-1][field] == initial["versions"][0][field]


def test_bank_demo_keeps_annual_report_after_moving_initial_material():
    demo = next(d for d in main._demo_cases() if d.id == "B")
    assert len(demo.supplements) == 2
    assert "2022" in demo.supplements[0].title
    assert "2025" in demo.supplements[1].title
