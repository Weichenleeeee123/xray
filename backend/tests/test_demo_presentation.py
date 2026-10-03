import json

import pytest

from app.models import CaseIn, PrebuiltProvenance
from tests.helpers import DEMO_COMPANY, make_case


def prepared():
    from app.demo_presentation import bind_presentation
    case = make_case(DEMO_COMPANY)
    v = case.versions[0]
    v.prebuilt = PrebuiltProvenance(demo_id='T', built_at='2026-10-04 00:00')
    ref = next(r.id for r in case.raw if r.id in v.raw_ids and r.coverage == 'found')
    bind_presentation(case, v, title='基础核查摘要', note='历史事项仍需了解', body='保留全部记录。', refs=[ref])
    return case


def test_replayed_identity_does_not_change_presentation_or_evidence():
    from app.demo_presentation import refresh_presentations
    case = prepared()
    before = case.versions[0].overview.model_dump()
    case.id, case.owner_id = 'newid', 'newowner'
    refresh_presentations(case)
    assert case.versions[0].report_presentation.title == '基础核查摘要'
    assert case.versions[0].overview.model_dump() == before


@pytest.mark.parametrize('change', ['raw', 'company', 'scenario', 'need', 'version', 'status', 'not_prebuilt', 'missing_ref'])
def test_changed_evidence_or_scope_discards_presentation(change):
    from app.demo_presentation import refresh_presentations
    case = prepared()
    v = case.versions[0]
    if change == 'raw':
        next(r for r in case.raw if r.id == v.report_presentation.refs[0]).content = {'changed': True}
    elif change == 'company':
        case.case.company_name = '不同公司'
    elif change == 'scenario':
        v.scenario = 'job'
    elif change == 'need':
        v.need += '新需求'
    elif change == 'version':
        v.no += 1
    elif change == 'status':
        v.signals[0].items[0].value = '新情况'
    elif change == 'not_prebuilt':
        v.prebuilt = None
    else:
        v.report_presentation.refs = ['R99999']
    refresh_presentations(case)
    assert v.report_presentation is None


def test_public_input_cannot_assign_presentation():
    body = CaseIn.model_validate({'company_name': DEMO_COMPANY, 'report_presentation': {'title': '伪造'}})
    assert 'report_presentation' not in body.model_dump()


def test_live_supplement_drops_copy_but_keeps_historical_presentation():
    from app.demo_presentation import refresh_presentations
    from tests.helpers import add
    case = prepared()
    first = case.versions[0].report_presentation.model_dump()
    add(case, 'need', '现在改为了解是否适合入职')
    refresh_presentations(case)
    assert case.versions[0].report_presentation.model_dump() == first
    assert case.versions[-1].report_presentation is None


def test_empty_presentation_preserves_existing_assistant_recording_context():
    from app.assistant import context
    case = make_case(DEMO_COMPANY)
    assert 'report_presentation' not in context(case, case.versions[0])['报告']


def test_api_prebuilt_replay_and_read_keep_bound_presentation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import demo_prebuilt, main
    from app.store import CaseStore
    case = prepared()
    data = {'demo_id': 'T', 'built_at': '2026-10-04 00:00', 'stages': [
        {'events': [], 'case': case.model_dump(mode='json'), 'supplement': None}]}
    monkeypatch.setattr(demo_prebuilt, 'DIR', tmp_path)
    monkeypatch.setattr(main, 'store', CaseStore(tmp_path / 'cases'))
    (tmp_path / 'T.json').write_text(json.dumps(data), encoding='utf-8')
    client = TestClient(main.app)
    response = client.post('/api/cases', json=case.case.model_dump(mode='json'))
    assert response.status_code == 200
    saved = response.json()
    assert saved['versions'][0]['report_presentation']['title'] == '基础核查摘要'
    assert client.get('/api/cases/' + saved['id']).json()['versions'][0]['report_presentation'] == saved['versions'][0]['report_presentation']
