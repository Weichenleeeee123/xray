from app.analysis.company_keywords import company_keywords, refresh_company_keywords
from app.models import RawRecord
from tests.helpers import DEMO_COMPANY, make_case


def snapshot():
    case = make_case(DEMO_COMPANY)
    version = case.versions[0]
    record = next(r for r in case.raw if r.id in version.raw_ids and r.source_id == 'registry')
    return case, version, record


def test_keywords_describe_recorded_business_with_clickable_evidence():
    case, version, record = snapshot()
    version.company.scope = '软件开发；人工智能应用软件开发；信息技术咨询服务'
    record.content = {'工商信息': {'企业标签': ['高新技术企业', '科技型中小企业'], '融资轮次': '天使轮'}}
    words = company_keywords(version, case.raw)
    labels = [word.label for word in words]
    assert labels[:3] == ['高新技术企业', '科技型中小企业', '天使轮']
    assert '软件开发' in labels and '人工智能' in labels
    assert len(words) <= 6 and len(labels) == len(set(labels))
    assert all(word.ref == record.id and word.basis for word in words)


def test_claims_names_shareholders_and_expired_honours_do_not_become_keywords():
    case, version, record = snapshot()
    version.company.scope = '健康咨询（不含诊疗服务）；不得从事资产管理；非高新技术企业'
    version.company.name = '高新技术天使轮有限公司'
    record.content = {'工商信息': {
        '企业标签': ['申请中：高新技术企业', {'名称': '科技型中小企业', '状态': '已撤销'},
                 {'名称': '绿色工厂', '有效期至': '2020-01-01'}]},
        '股东': [{'企业标签': ['高新技术企业']}]}
    material = RawRecord(id='claim', source_id='material', title='自述', kind='user_material',
                         retrieved_at=version.created_at, content={'企业标签': ['高新技术企业']})
    case.raw.append(material)
    version.raw_ids.append(material.id)
    labels = [word.label for word in company_keywords(version, case.raw)]
    assert '健康咨询' in labels
    assert not {'高新技术企业', '科技型中小企业', '绿色工厂', '天使轮', '资产管理'} & set(labels)


def test_old_version_does_not_borrow_new_version_honours():
    case, version, record = snapshot()
    record.content = {'企业标签': ['小微企业']}
    newer_record = record.model_copy(deep=True, update={'id': 'new', 'content': {'企业标签': ['高新技术企业']}})
    newer_version = version.model_copy(deep=True, update={'no': 2, 'raw_ids': ['new']})
    case.raw.append(newer_record)
    case.versions.append(newer_version)
    before = version.onepager.model_dump()
    refresh_company_keywords(case)
    assert '小微企业' in [word.label for word in version.company_keywords]
    assert '高新技术企业' not in [word.label for word in version.company_keywords]
    assert '高新技术企业' in [word.label for word in newer_version.company_keywords]
    assert version.onepager.model_dump() == before


def test_missing_or_failed_registry_cannot_invent_descriptors():
    case, version, record = snapshot()
    record.coverage = 'failed'
    assert company_keywords(version, case.raw) == []
    record.coverage = 'found'
    version.company = None
    assert company_keywords(version, case.raw) == []


def test_api_adds_keywords_to_old_reports_without_rewriting_saved_conclusions(monkeypatch):
    import threading
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main, '_stopping', threading.Event())
    with TestClient(main.app) as client:
        response = client.post('/api/cases', json={'company_name': DEMO_COMPANY, 'need': '了解公司'})
        assert response.status_code == 200
        case = response.json()
        assert case['versions'][0]['company_keywords']
        stored = main.store.get(case['id'])
        stored.versions[0].company_keywords = []  # An existing saved report before this feature.
        main.store.save(stored)
        old_headline = stored.versions[0].onepager.headline
        loaded = client.get(f"/api/cases/{case['id']}").json()
        assert loaded['versions'][0]['company_keywords']
        version_response = client.get(f"/api/cases/{case['id']}/versions/1").json()
        assert version_response['version']['company_keywords'] == loaded['versions'][0]['company_keywords']
        assert version_response['version']['onepager']['headline'] == old_headline
        assert main.store.get(case['id']).versions[0].company_keywords == []
