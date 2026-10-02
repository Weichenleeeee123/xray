"""Regression cases for the backend audit; all provider/model inputs are synthetic."""
import asyncio
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models import CaseIn, ChatIn, RawRecord, Shareholder, Status
from tests.helpers import DEMO_COMPANY, make_case, add, svc


def test_recheck_survives_store_roundtrip(tmp_path):
    from app.analysis.pipeline import resolve
    from app.models import ResolveIn
    from app.store import CaseStore
    c = make_case(DEMO_COMPANY, '收款户名：张某。请转账到个人账户。')
    c = resolve(c, ResolveIn(judgment_id='check.A7', action='recheck'))
    s = CaseStore(tmp_path)
    s.save(c)
    assert s.get(c.id).versions[-1].judgments
    assert next(j for j in c.versions[-1].judgments if j.id == 'check.A7').state == 'needs_check'


def test_store_rejects_stale_write(tmp_path):
    from app.store import CaseStore
    s = CaseStore(tmp_path)
    c = s.save(make_case(DEMO_COMPANY))
    stale = s.get(c.id)
    fresh = add(s.get(c.id), 'material', '本次新材料')
    s.save(fresh)
    with pytest.raises(Exception, match='更新|冲突|changed'):
        s.save(stale)
    assert s.get(c.id).current == 2


def test_chat_append_preserves_concurrent_supplement(tmp_path, monkeypatch):
    import app.main as main
    from app.models import ChatMessage
    from app.store import CaseStore
    monkeypatch.setattr(main, 'store', CaseStore(tmp_path))
    client = TestClient(main.app)
    c = client.post('/api/cases', json={'company_name': DEMO_COMPANY}).json()
    entered, release = threading.Event(), threading.Event()
    def slow(c, body, llm, **kw):
        entered.set()
        assert release.wait(5)
        return ChatMessage(role='assistant', text='测试回答', version=c.current, created_at='2026-10-02')
    monkeypatch.setattr(main, 'answer', slow)
    with ThreadPoolExecutor(1) as pool:
        f = pool.submit(client.post, f"/api/cases/{c['id']}/chat", json={'text': '查询'})
        assert entered.wait(5)
        try:
            r = client.post(f"/api/cases/{c['id']}/supplements", json={'kind': 'material', 'text': '新材料唯一标记'})
        finally:
            release.set()
        assert r.status_code == f.result().status_code == 200
    final = client.get('/api/cases/' + c['id']).json()
    assert final['current'] == 2 and len(final['chat']) == 2
    assert any(r['content'] == '新材料唯一标记' for r in final['raw'])


@pytest.mark.parametrize('text,kind', [
    ('招聘入职不收取任何押金或培训费。', 'upfront_fee'),
    ('禁止转账到个人账户。', 'payee'),
    ('不承诺零风险。', 'return_promise'),
    ('不能随时退款，合同以约定为准。', 'refund'),
])
def test_negation_is_not_a_positive_claim(text, kind):
    from app.analysis.extract import RuleExtractor
    assert kind not in RuleExtractor().extract(text).claims


def test_diff_tracks_values_and_never_calls_missing_evidence_improvement():
    from app.analysis.diff import diff
    before = make_case(DEMO_COMPANY).versions[0]
    old = next(i for s in before.signals for i in s.items if s.key == 'credit' and i.key == 'penalties')
    old.status, old.value = Status.bad, '1 条'
    after = before.model_copy(deep=True)
    item = next(i for s in after.signals for i in s.items if s.key == 'credit' and i.key == 'penalties')
    item.value = '10 条'
    change = next(c for c in diff(before, after, {})[0] if c.target == 'credit.penalties')
    assert change.kind != 'unchanged'
    item.status, item.value = Status.none, '查询失败'
    change = next(c for c in diff(before, after, {})[0] if c.target == 'credit.penalties')
    assert change.kind != 'clarified' and '轻了' not in change.plain


@pytest.mark.parametrize('source,short', [('未登记', '已登记'), ('没有处罚记录', '有处罚记录'), ('禁止转账', '可以转账')])
def test_short_cannot_reverse_polarity(source, short):
    from app.plain import _short_ok
    assert not _short_ok(short, source, source)


def test_model_cannot_invent_status_from_real_reference(tmp_path):
    from app.assistant import answer
    from tests.test_llm_assistant import FakeLLM
    c = make_case(DEMO_COMPANY)
    r = next(r for r in c.raw if r.source_id == 'registry')
    payload = json.dumps({'segments': [{'text': '这家公司已经停止营业。', 'citations': [r.id]}]}, ensure_ascii=False)
    reply = answer(c, ChatIn(text='登记状态如何'), FakeLLM([payload] * 3, tmp_path))
    assert '已经停止营业' not in reply.text


def test_license_subtype_matters():
    from app.analysis.verify import claimed_licenses_check
    from app.models import LicenseHit, LicenseRecord, AmacHit, Coverage
    lic = LicenseHit(query='测试银行', found=True, record=LicenseRecord(name='测试银行', name_en='', code='X', type='商业银行', regulator=''))
    check = claimed_licenses_check(['信托'], lic, AmacHit(coverage=Coverage.not_found, registered=False), [])
    assert check.status != Status.ok


def test_nine_shareholders_do_not_break_report():
    from app.analysis.charts import holders_chart
    p = make_case(DEMO_COMPANY).versions[0].company.model_copy(deep=True)
    p.shareholders = [Shareholder(name=f'股东{i}', type='自然人', pct=10) for i in range(9)]
    assert len(holders_chart(p, [], {}).points) == 9


def qcc(tmp_path, tools=None, **kw):
    from tests.test_qcc_agent import client, TOOLS
    return client(tmp_path, tools=TOOLS if tools is None else tools, **kw)


def test_secondary_identity_mismatch_is_not_applied(tmp_path):
    from tests.test_qcc_agent import NAME, TOOLS
    data = dict(TOOLS, get_company_risk_scan={'企业名称': '另一家公司', '风险因子扫描': [{'风险因子': '失信信息', '条目数': 1}]})
    r = qcc(tmp_path, data).fetch(NAME)
    assert not r.profile.known('dishonest') and not r.profile.dishonest


def test_partial_abnormal_rows_cannot_clear_total(tmp_path):
    from tests.test_qcc_agent import NAME, TOOLS
    data = dict(TOOLS, get_company_risk_scan={'企业名称': NAME, '风险因子扫描': [{'风险因子': '经营异常', '条目数': 100}]},
                get_business_exception={'企业名称': NAME, '摘要': '共有100条', '经营异常信息': [{'列入日期':'2020-01-01','移出日期':'2021-01-01'}]})
    assert qcc(tmp_path, data).fetch(NAME).profile.abnormal


def test_partial_registration_does_not_break_report(tmp_path):
    from tests.test_qcc_agent import NAME, TOOLS
    from app.analysis.signals import credit_signal
    r = qcc(tmp_path, dict(TOOLS, get_company_registration_info={'企业名称': NAME})).fetch(NAME)
    if r.profile:
        assert not r.profile.known('founded')
        assert next(i for i in credit_signal(r.profile, date.today()).items if i.key == 'status').status != Status.ok
    else:
        assert r.failed


def test_qcc_cache_is_scrubbed(tmp_path):
    from tests.test_qcc_agent import NAME
    q = qcc(tmp_path); q.fetch(NAME)
    contents = '\n'.join(p.read_text(encoding='utf-8') for p in tmp_path.glob('*.json'))
    assert '甲某' not in contents and '0571-00000000' not in contents and '法定代表人' not in contents


def test_qcc_expired_cache_refreshes(tmp_path):
    from tests.test_qcc_agent import NAME
    q = qcc(tmp_path)
    p = q._path(NAME, 'get_company_registration_info')
    p.write_text(json.dumps({'data':{'企业名称':NAME,'登记状态':'旧状态'},'retrieved_at':'2000-01-01T00:00:00+08:00'}), encoding='utf-8')
    r = q.call('company', 'get_company_registration_info', NAME)
    assert r.data['登记状态'] != '旧状态' and not r.cached


def test_qcc_corrupt_cache_falls_back_without_deleting(tmp_path):
    from tests.test_qcc_agent import NAME
    q = qcc(tmp_path); p = q._path(NAME, 'get_company_registration_info'); p.write_text('{', encoding='utf-8')
    r = q.call('company', 'get_company_registration_info', NAME)
    assert r.error is None and r.data['企业名称'] == NAME
    assert any(x.read_text(encoding='utf-8') == '{' for x in tmp_path.glob('*') if x.is_file())


def test_concurrent_budget_reservation(tmp_path, monkeypatch):
    from app.sources.qcc_agent import QccAgentClient
    q = QccAgentClient('fake', max_points=3, cache_dir=tmp_path)
    entered, release = threading.Event(), threading.Event()
    def post(*args): entered.set(); release.wait(2); return {'企业名称': args[-1]}
    monkeypatch.setattr(q, '_post_any', post)
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(q.call, 'company', 'get_company_registration_info', '甲公司')
        assert entered.wait(2)
        two = pool.submit(q.call, 'company', 'get_company_registration_info', '乙公司')
        time.sleep(.03); release.set(); result = [one.result(), two.result()]
    assert sum(r.error is None for r in result) == 1 and q.points <= 3


def test_money_does_not_relabel_dollars_as_yuan():
    from app.sources.commercial import to_profile
    from app.analysis.signals import finance_signal
    p = to_profile('qcc', {'Name':'测试公司','StartDate':'2020-01-01','Status':'存续','RegistCapi':'100万美元','RecCap':'100万美元'})
    item = next(i for i in finance_signal(p, None).items if i.key == 'paid_capital')
    assert '¥' not in item.value and '美元' in item.value


@pytest.mark.parametrize('text,expected', [('投资1亿元', 100000000), ('需要付1,200元', 1200), ('月薪2万元，入职先交500元押金', 500)])
def test_amount_parsing(text, expected):
    from app.scenarios import parse_amount
    assert parse_amount(text) == expected


def test_provenance_not_deduplicated_across_dates():
    from app.analysis.pipeline import attach
    r = RawRecord(id='', source_id='registry', title='登记', kind='commercial', content={'状态':'存续'}, retrieved_at='2025-01-01', url='https://old.example')
    raw=[]; old=attach(raw,r)
    new=attach(raw,r.model_copy(update={'retrieved_at':'2026-10-02','url':'https://new.example'}))
    assert old != new


def test_non_official_domain_rejected_in_official_search(monkeypatch):
    from app.sources.web import WebClient
    w=WebClient(base_url='https://unused.invalid',api_key='fake')
    monkeypatch.setattr(w,'search',lambda *a: ([{'name':'测试公司介绍','url':'https://ordinary.example','site':'普通网站','date':'2026-10-02','text':'测试公司介绍'}],False))
    assert not w.find_official('测试公司').official


def test_upload_offloads_sync_work(monkeypatch):
    import app.main as main
    from app.models import ReadResult
    from starlette.datastructures import UploadFile
    def slow(*a): time.sleep(.15); return ReadResult(text='test',method='text')
    monkeypatch.setattr(main,'read_upload',slow)
    async def check():
        start=time.monotonic(); ticks=[]
        async def tick(): await asyncio.sleep(.02);ticks.append(time.monotonic()-start)
        await asyncio.gather(main.read_file(UploadFile(filename='test.txt',file=io.BytesIO(b'hi'))),tick())
        return ticks[0]
    assert asyncio.run(check()) < .12


@pytest.mark.parametrize('data',[{'company_name':'  '},{'company_name':'测试公司','amount':'Infinity'}, {'company_name':'测试公司','material_text':'x'*200001}])
def test_case_input_is_bounded_and_finite(data):
    with pytest.raises(ValidationError): CaseIn(**data)


def test_withdrawal_refreshes_projection():
    from app.analysis.pipeline import resolve
    from app.models import ResolveIn
    c=make_case(DEMO_COMPANY,'收款户名：张某。请转账到个人账户。')
    before=c.versions[-1].onepager.model_dump()
    c=resolve(c,ResolveIn(judgment_id='check.A7',action='withdrawn',note='误识别',by='测试人'))
    v=c.versions[-1]
    assert v.onepager.model_dump()!=before
    assert next(a for a in v.assertions if a.id=='A7').color!='red'


def test_run_state_visible_outside_owner_memory(tmp_path, monkeypatch):
    import app.main as main
    from app.store import CaseStore
    monkeypatch.setattr(main,'RUNS_DIR',tmp_path/'runs')
    monkeypatch.setattr(main.privacy, 'identity', lambda: 'test-owner')
    entered,release=threading.Event(),threading.Event()
    c=make_case(DEMO_COMPANY)
    def work(): entered.set();release.wait(3);return c
    r=main._start_run({'type':'begin'},work);assert entered.wait(2)
    try:
        monkeypatch.setattr(main,'_active_runs',set())
        assert main.get_run(r['run_id'],after=0)['status']=='running'
    finally: release.set()


@pytest.mark.parametrize('text', ['这家公司现在已经关闭。', '全部处罚已撤销。', '已取得所有牌照。', '不存在任何风险。'])
def test_raw_reference_cannot_ground_new_semantics(text, tmp_path):
    from app.assistant import answer
    from tests.test_llm_assistant import FakeLLM
    c = make_case(DEMO_COMPANY)
    ref = next(r.id for r in c.raw if r.source_id == 'registry')
    output = json.dumps({'segments': [{'text': text, 'citations': [ref]}]}, ensure_ascii=False)
    result = answer(c, ChatIn(text='记录写了什么'), FakeLLM([output] * 3, tmp_path))
    assert text not in result.text


def test_fact_selection_renders_server_text(tmp_path):
    from app.assistant import answer, citable
    from tests.test_llm_assistant import FakeLLM
    c = make_case(DEMO_COMPANY)
    payload = json.dumps({'segments': [{'fact_id': 'credit.status', 'text': '这家公司已经停止营业。'}]})
    result = answer(c, ChatIn(text='登记状态'), FakeLLM([payload], tmp_path))
    assert '已经停止营业' not in result.text
    item = next(i for s in c.versions[-1].signals if s.key == 'credit' for i in s.items if i.key == 'status')
    assert all(part in result.text for part in (item.label, item.value, item.detail))
    assert result.citations == ['credit.status']


def test_run_idempotency_and_payload_conflict(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, 'RUNS_DIR', tmp_path)
    client = TestClient(main.app)
    calls = []
    monkeypatch.setattr(main, '_create', lambda body: calls.append(body) or make_case(DEMO_COMPANY))
    header = {'Idempotency-Key': 'synthetic-key'}
    body = {'company_name': DEMO_COMPANY}
    first = client.post('/api/runs', json=body, headers=header)
    second = client.post('/api/runs', json=body, headers=header)
    assert first.json()['run_id'] == second.json()['run_id']
    assert len(calls) == 1
    assert client.post('/api/runs', json={**body, 'need': 'changed'}, headers=header).status_code == 409


def test_indexed_list_does_not_load_entire_cases(tmp_path, monkeypatch):
    from app.store import CaseStore
    store = CaseStore(tmp_path)
    for _ in range(3): store.save(make_case(DEMO_COMPANY))
    restarted = CaseStore(tmp_path)
    monkeypatch.setattr(restarted, 'get', lambda *_: pytest.fail('full case read'))
    assert len(restarted.list(limit=1, offset=1)) == 1


def test_upload_keeps_page_status():
    from app.readers import read_upload
    from app.llm import LLM
    result = read_upload('test.txt', '测试材料'.encode(), LLM(mode='off'))
    assert result.status == 'ready' and result.pages[0]['text'] == '测试材料'


def test_negated_contract_does_not_create_prepayment_judgment():
    c = make_case(DEMO_COMPANY, '劳动合同：入职不收取押金，不收培训费。')
    assert not any(j.id.startswith('contract.prepay.') for j in c.versions[-1].judgments)


@pytest.mark.parametrize('text,kind', [('不持有信托牌照。', 'qualification'), ('无国资背景。', 'background'), ('非银行存管。', 'partner')])
def test_other_negated_claims(text, kind):
    from app.analysis.extract import RuleExtractor
    assert kind not in RuleExtractor().extract(text).claims


def test_recheck_restores_previously_withdrawn_card():
    from app.analysis.pipeline import resolve
    from app.models import ResolveIn
    c = make_case(DEMO_COMPANY, '收款户名：张某。请转账到个人账户。')
    original = next(a for a in c.versions[-1].assertions if a.id == 'A7').model_dump()
    resolve(c, ResolveIn(judgment_id='check.A7', action='withdrawn', note='待复查'))
    resolve(c, ResolveIn(judgment_id='check.A7', action='recheck', note='重新核实'))
    card = next(a for a in c.versions[-1].assertions if a.id == 'A7')
    judgment = next(j for j in c.versions[-1].judgments if j.id == 'check.A7')
    assert card.color == original['color'] and judgment.unknown


def test_stale_write_rejected_between_processes(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from app.store import CaseStore
    s = CaseStore(tmp_path)
    case = s.save(make_case(DEMO_COMPANY))
    script = '''import sys, time
from pathlib import Path
from app.store import CaseStore, ConflictError
s=CaseStore(Path(sys.argv[1])); c=s.get(sys.argv[2])
print('ready', flush=True); sys.stdin.readline()
try:
 s.save(c); print('saved', flush=True)
except ConflictError:
 print('conflict', flush=True)
'''
    workers = [subprocess.Popen([sys.executable, '-B', '-c', script, str(tmp_path), case.id],
               cwd=Path(__file__).parents[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               text=True) for _ in range(2)]
    for process in workers: assert process.stdout.readline().strip() == 'ready'
    for process in workers: process.stdin.write('\n'); process.stdin.flush()
    outputs = [process.communicate(timeout=10)[0].strip() for process in workers]
    assert sorted(outputs) == ['conflict', 'saved']


def test_concurrent_reviews_do_not_overwrite(tmp_path):
    from app.reviews import ReviewStore
    from app.models import ReviewIn
    stores = [ReviewStore(tmp_path), ReviewStore(tmp_path)]
    bodies = [ReviewIn(company='测试公司', stars=3, relation='customer', text='这是一个合成测试的用户评价', author=f'author-{i:04d}') for i in range(2)]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda i: stores[i].add(bodies[i]), range(2)))
    assert len(ReviewStore(tmp_path).all('测试公司')) == 2


def test_expired_lease_is_interrupted(tmp_path, monkeypatch):
    import app.main as main
    from app import runs
    monkeypatch.setattr(main, 'RUNS_DIR', tmp_path)
    monkeypatch.setattr(main.privacy, 'identity', lambda: 'test-owner')
    rid = 'a' * 24
    runs.append(tmp_path, rid, {'type': 'begin'})
    runs.touch(tmp_path, rid, finished=True)
    runs.set_owner(tmp_path, rid, 'test-owner')
    assert main.get_run(rid, after=0)['status'] == 'interrupted'


def test_busy_run_is_rejected_before_work(tmp_path, monkeypatch):
    import app.main as main
    from fastapi import HTTPException
    monkeypatch.setattr(main, 'RUNS_DIR', tmp_path)
    semaphore = threading.BoundedSemaphore(1); semaphore.acquire()
    monkeypatch.setattr(main, '_run_slots', semaphore)
    with pytest.raises(HTTPException) as caught:
        main._start_run({'type': 'begin'}, lambda: pytest.fail('must not start'))
    assert caught.value.status_code == 503


def test_bad_provider_types_degrade_to_failed(tmp_path):
    from tests.test_qcc_agent import NAME, TOOLS
    data = dict(TOOLS, get_company_registration_info={'企业名称': NAME, '成立日期': '2020-99-99', '注册资本': float('inf')})
    result = qcc(tmp_path, data).fetch(NAME)
    assert result.failed and result.profile is None


def test_unknown_currency_is_not_yuan():
    from app.sources.commercial import currency, parse_money
    assert currency('100万瑞士法郎') != '人民币'
    assert parse_money('-10万元') is None


def test_cache_write_failure_does_not_discard_live_data(tmp_path, monkeypatch):
    from tests.test_qcc_agent import NAME
    import app.sources.qcc_agent as module
    q = qcc(tmp_path)
    monkeypatch.setattr(module, 'atomic_json', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    response = q.call('company', 'get_company_registration_info', NAME)
    assert response.error is None and response.data['企业名称'] == NAME


def test_negative_fee_clause_does_not_hide_positive_clause():
    from app.analysis.extract import RuleExtractor
    negative = RuleExtractor().extract('入职不需要交押金。')
    mixed = RuleExtractor().extract('入职不收押金，但是需要先交培训费。')
    assert 'upfront_fee' not in negative.claims
    assert mixed.claims['upfront_fee'].words == ['培训费']


def test_bare_provider_claim_cannot_reverse_report_status(tmp_path):
    from app.assistant import answer
    from tests.test_llm_assistant import FakeLLM
    c = make_case(DEMO_COMPANY)
    payload = json.dumps({'segments': [{'text': '这家公司已经关闭。', 'citations': ['credit.status']}]})
    result = answer(c, ChatIn(text='登记状态'), FakeLLM([payload] * 3, tmp_path))
    assert '已经关闭' not in result.text
