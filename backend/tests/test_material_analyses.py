import threading

from fastapi.testclient import TestClient

from app.analysis.materials import ensure_material_analyses
from app.models import Case
from tests.helpers import DEMO_COMPANY, add, flyer, make_case


def test_only_new_grounded_material_preserves_company_history():
    case = make_case(DEMO_COMPANY, flyer('manyinghe.txt'))
    before = case.versions[0].model_dump()
    text = '退款条款：提前退出收取本金 30% 的违约金。收款户名：张三，转入个人账户。'
    add(case, 'material', text)
    ensure_material_analyses(case)
    assert case.versions[0].model_dump() == before
    analysis, = case.material_analyses
    assert analysis.base_version == 1 and analysis.report_version == 2
    assert analysis.findings
    raws = {r.id: r for r in case.raw}
    assert all(raws[r].content == text for r in analysis.raw_ids)
    for finding in analysis.findings:
        assert finding.quotes and all(q.replace(' ', '') in text.replace(' ', '') for q in finding.quotes)
        assert set(finding.refs) <= set(analysis.raw_ids)
    assert not any(f.kind.value == 'scale' for f in analysis.findings)
    assert [s.key for s in case.versions[-1].signals] == ['risk', 'finance', 'credit', 'reputation']


def test_serialization_and_legacy_backfill_without_duplicates():
    case = make_case(DEMO_COMPANY)
    add(case, 'material', '收款户名：张三，转入个人账户。')
    ensure_material_analyses(case)
    first = case.material_analyses[0].model_dump()
    add(case, 'reply', '放心吧，大家都这么做。')
    ensure_material_analyses(case)
    reloaded = Case.model_validate_json(case.model_dump_json())
    ensure_material_analyses(reloaded)
    assert len(reloaded.material_analyses) == 2
    assert reloaded.material_analyses[0].model_dump() == first
    reloaded.material_analyses = []
    ensure_material_analyses(reloaded)
    assert len(reloaded.material_analyses) == 2
    assert reloaded.material_analyses[0].model_dump() == first


def test_unrecognized_reply_does_not_claim_safety():
    case = make_case(DEMO_COMPANY)
    add(case, 'reply', '你好，收到，明天联系。')
    ensure_material_analyses(case)
    analysis, = case.material_analyses
    assert not analysis.findings
    assert analysis.summary == '尚未提取到可核对的具体说法'
    assert not analysis.questions


def test_contract_specific_checks_are_included():
    case = make_case('杭州明澄家政服务有限公司')
    add(case, 'material', '服务合同\n甲方：另一家服务有限公司\n乙方：客户\n第一条：服务期限一年。\n第二条：付款后不予退款。')
    ensure_material_analyses(case)
    analysis, = case.material_analyses
    assert analysis.observations
    assert all(any(b.ref in analysis.raw_ids for b in o.basis) for o in analysis.observations)


def test_need_updates_do_not_create_material_appendices():
    case = make_case(DEMO_COMPANY)
    add(case, 'need', '我想入职这家公司')
    ensure_material_analyses(case)
    assert case.material_analyses == []


def test_api_persistence_ownership_and_legacy_support(monkeypatch):
    from app import main
    monkeypatch.setattr(main, '_stopping', threading.Event())
    with TestClient(main.app) as client:
        case = client.post('/api/cases', json={'company_name': DEMO_COMPANY, 'need': '核实合同退款'}).json()
        response = client.post(f"/api/cases/{case['id']}/supplements", json={
            'kind': 'material', 'title': '合同补充', 'text': '提前退出收取本金 30% 的违约金。'})
        assert response.status_code == 200, response.text
        saved = response.json()
        assert len(saved['material_analyses']) == 1
        assert saved['material_analyses'][0]['title'] == '合同补充'
        assert 'owner_id' not in saved
        stored = main.store.get(case['id'])
        assert stored.material_analyses[0].title == '合同补充'
        assert client.get(f"/api/cases/{case['id']}").json()['material_analyses'] == saved['material_analyses']
        stored.material_analyses = []
        main.store.save(stored)
        assert client.get(f"/api/cases/{case['id']}").json()['material_analyses'] == saved['material_analyses']
        client.cookies.clear()
        assert client.get(f"/api/cases/{case['id']}").status_code == 404
