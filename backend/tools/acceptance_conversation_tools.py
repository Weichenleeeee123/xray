"""Offline Edge acceptance for Xiaoqi dialogue, term focus and explicit actions.

Uses synthetic report snapshots and temporary browser/server storage. The real
local chat API, rendering, navigation and library persistence are exercised;
model keys and external network access are disabled. No production data is used.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
sys.path.insert(0, str(BASE))


def serve(port):
    connect = socket.socket.connect

    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'127.0.0.1', '::1'}:
            raise AssertionError('External network disabled in conversation acceptance')
        return connect(sock, address)

    socket.socket.connect = local_connect
    import uvicorn
    import app.main as main
    from app import privacy
    from app.models import SignalItem, Term
    from tests import helpers

    helpers.svc.web = helpers.svc.commercial = None
    main.svc.web = main.svc.commercial = None

    @main.app.post('/api/__conversation_seed')
    def seed():
        case = helpers.make_case(helpers.DEMO_COMPANY, need='合成对话及词条功能验收')
        case.owner_id = privacy.identity()
        version = case.versions[0]
        term = Term(id='m_term_deadline_filing', term='期限备案', origin='model',
                    plain='合成第一版词义：约定期限相关资料的报备流程，具体含义要结合原句。',
                    why='不代表取得许可，也不能据此判断企业资质。')
        version.terms.append(term)
        credit = next(signal for signal in version.signals if signal.key == 'credit')
        record = next(raw for raw in case.raw if raw.id in version.raw_ids)
        credit.items.insert(0, SignalItem(key='term_fixture', label='期限备案', value='合成词条位置',
            detail='合成界面验收：这里的期限备案是词语位置，不代表已核实企业事实。',
            status='warn', source=record.source_id, ref=record.id))
        credit.flags += 1
        later = version.model_copy(deep=True, update={'no': 2, 'trigger': 'need', 'trigger_label': '合成第二版'})
        later.terms = [item.model_copy(update={'plain':'合成第二版词义：报备材料涉及的期限说明，应结合具体文本。'})
                       if item.id == term.id else item for item in later.terms]
        case.versions.append(later)
        case.current = 2
        main.store.save(case)
        return {'id':case.id, 'term_id':term.id, 'entry_ref':'credit.term_fixture', 'raw_ref':record.id}

    main.app.router.routes.insert(0, main.app.router.routes.pop())
    uvicorn.run(main.app, host='127.0.0.1', port=port, log_level='warning')


def run(out):
    from playwright.sync_api import sync_playwright, expect

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='qier-conversation-') as directory:
        env = dict(os.environ)
        for name in ('CASES', 'CACHE', 'REVIEWS', 'RUNS', 'PRIVATE', 'CASE_MEMORY', 'DEMO_PREBUILT'):
            env[f'XRAY_{name}_DIR'] = str(Path(directory) / name.lower())
        env.update(XRAY_LLM_MODE='off', TOKENDANCE_API_KEY='', TOKENDANCE_BASE_URL='',
                   TOKENDANCE_MODEL='', XRAY_COMMERCIAL='', XRAY_AMAC_DETAIL='0', XRAY_CNINFO='0',
                   XRAY_WEB_DISCOVERY='0', XRAY_WEB_DISCOVERY_LLM='0', XRAY_RESEND_KEY='',
                   XRAY_QUOTA_GUEST='0', XRAY_QUOTA_IP='0', XRAY_QUOTA_ACCOUNT='0')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        proc = subprocess.Popen([sys.executable, __file__, '--serve', str(port)], cwd=BASE, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(150):
                try:
                    with urlopen(base + '/api/health', timeout=1) as response:
                        health = json.load(response)
                        assert health['llm']['mode'] == 'off' and not health['llm']['configured']
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError('Isolated conversation server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated conversation server did not start')
            with sync_playwright() as pw:
                edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
                browser = pw.chromium.launch(headless=True, **({'executable_path':str(edge)} if edge.exists() else {}))
                context = browser.new_context(viewport={'width':1600, 'height':1050}, reduced_motion='reduce')
                context.set_default_timeout(15000)
                external = []

                def local_route(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        external.append(route.request.url)
                        route.abort()

                context.route('**/*', local_route)
                seeded = context.request.post(base + '/api/__conversation_seed')
                assert seeded.ok, seeded.text()
                fixture = seeded.json()
                case_url = base + '/xray/#/case/' + fixture['id']
                chat_url = base + '/api/cases/' + fixture['id'] + '/chat'
                page = context.new_page()
                errors, passed, sent = [], [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: sent.append(request.post_data_json)
                        if request.url == chat_url and request.method == 'POST' else None)

                def open_assistant():
                    if not page.locator('#assist').evaluate('(e) => e.classList.contains("open")'):
                        page.locator('.workspace-assistant-toggle').click()

                def open_case(version=1):
                    page.goto(case_url + f'/v/{version}', wait_until='domcontentloaded')
                    page.wait_for_function('(args) => typeof S !== "undefined" && S.case?.id === args[0] && ver()?.no === args[1] && !!document.querySelector("#research-overview")',
                                           arg=[fixture['id'], version])
                    open_assistant()

                def ask(text=None):
                    count = page.locator('#asBody .msg.ai').count()
                    if text is not None:
                        page.locator('#asForm textarea').fill(text)
                    with page.expect_response(lambda response: response.url == chat_url and response.request.method == 'POST') as result:
                        page.locator('#asForm button[type="submit"]').click()
                    response = result.value
                    assert response.ok, response.text()
                    payload = response.json()
                    page.wait_for_function('(count) => !S.busy && document.querySelectorAll("#asBody .msg.ai").length > count', arg=count)
                    return page.locator('#asBody .msg.ai').last, payload

                def prepare_term():
                    if page.viewport_size['width'] < 900:
                        page.locator('#assist [data-act="close-assist"]').click()
                    page.locator('.signal-card[data-key="credit"]').click()
                    dialog = page.locator('#signalDlg')
                    expect(dialog).to_be_visible()
                    dialog.locator(f'[data-act="term"][data-term="{fixture["term_id"]}"]').first.click()
                    popup = page.locator('#pop')
                    expect(popup).to_contain_text('AI 解释')
                    expect(popup).to_contain_text('没有经过人工核对')
                    return popup

                def library():
                    return page.evaluate('JSON.parse(localStorage.getItem("xray.library") || "[]")')

                open_case()
                for text in ['你好', '我饿了', '我想哭']:
                    answer, payload = ask(text)
                    assert payload['answer_kind'] == 'conversation' and not payload['not_found']
                    assert not payload.get('error_code') and not payload['actions']
                    expect(answer.locator('.msg-meta')).not_to_contain_text(re.compile('资料缺失|仍待核实|材料处理|按需核对|基础答复'))
                    expect(answer.locator('[data-act="chat-action"], [data-act="supplement"]')).to_have_count(0)
                    expect(answer).not_to_contain_text(re.compile('收款账户|加入案卷|合同名称'))
                page.screenshot(path=str(out / '01-natural-conversation.png'))
                passed.append('ordinary_chat_has_no_missing_evidence_or_material_controls')

                popup = prepare_term()
                popup.screenshot(path=str(out / '02-ai-term-popup.png'))
                before = len(sent)
                popup.locator('[data-act="ask-term"]').click()
                expect(page.locator('#signalDlg')).not_to_be_visible()
                expect(page.locator('#asForm textarea')).to_have_value('期限备案是什么意思？')
                expect(page.locator('#asSel .term-context')).to_contain_text('期限备案 · 第 1 版')
                assert len(sent) == before, 'Selecting a term must not send a hidden request'
                page.screenshot(path=str(out / '03-visible-term-context.png'))
                answer, payload = ask()
                assert sent[-1]['version'] == 1
                assert sent[-1]['term_context'] == {'term_id':fixture['term_id'], 'entry_ref':fixture['entry_ref']}
                assert not any(key in json.dumps(sent[-1], ensure_ascii=False) for key in ['plain', '合成第一版词义'])
                assert payload['answer_kind'] == 'glossary'
                assert payload['knowledge_terms'][0]['origin'] == 'model'
                expect(answer).to_contain_text('合成第一版词义')
                expect(answer).to_contain_text('未人工复核')
                expect(answer).not_to_contain_text(re.compile('合成第二版词义|部分信息仍待核实|本次材料处理未完成'))
                expect(page.locator('#asSel .term-context')).to_have_count(0)
                page.screenshot(path=str(out / '04-ai-term-reply.png'))
                passed.append('popup_sends_only_versioned_identifiers_on_visible_submit')

                answer.get_by_role('button', name='查看词语所在条目', exact=True).click()
                expect(page.locator('#signalDlg')).to_be_visible()
                expect(page.locator('#signalDlg [data-item="credit.term_fixture"]')).to_be_visible()
                page.locator('#signalDlg .dlg-x').click()
                passed.append('explicit_open_ref_reuses_versioned_report_navigation')
                for text in ['说简单点', '举个例子']:
                    answer, followup = ask(text)
                    assert followup['answer_kind'] == 'glossary'
                    assert followup['knowledge_terms'] == payload['knowledge_terms']
                    expect(answer).to_contain_text('未人工复核')
                    assert 'term_context' not in sent[-1]
                passed.append('term_followups_keep_exact_unreviewed_snapshot')

                expect(answer.locator('[data-act="chat-lib-save"]')).to_have_count(1)
                answer.locator('[data-act="chat-lib-save"]').click()
                page.wait_for_function('JSON.parse(localStorage.getItem("xray.library") || "[]").length === 1')
                saved = library()[0]
                assert saved['id'] == fixture['term_id'] and saved['origin'] == 'model'
                assert saved['seen'][0]['version'] == 1 and saved['seen'][0]['caseId'] == fixture['id']
                assert saved['plain'] == payload['knowledge_terms'][0]['plain']
                answer, payload = ask('打开知识库')
                assert payload['actions'][0]['type'] == 'open_library'
                assert page.url.endswith('/v/1')
                answer.get_by_role('button', name='打开知识库', exact=True).click()
                expect(page.locator('#libList')).to_contain_text('期限备案')
                expect(page.locator('#libList')).to_contain_text('AI 解释·未经人工核对')
                page.screenshot(path=str(out / '05-saved-ai-term-library.png'))
                passed.append('save_and_explicit_library_navigation_preserve_snapshot_provenance')

                open_case()
                prepare_term().locator('[data-act="ask-term"]').click()
                page.locator('#dossier-version').select_option('2')
                page.wait_for_function('ver().no === 2')
                expect(page.locator('#asSel .term-context')).to_have_count(0)
                answer, payload = ask('你好')
                assert sent[-1]['version'] == 2 and 'term_context' not in sent[-1]
                assert payload['answer_kind'] == 'conversation'
                prepare_term().locator('[data-act="ask-term"]').click()
                expect(page.locator('#asSel .term-context')).to_contain_text('第 2 版')
                page.locator('#asForm textarea').fill('我饿了')
                expect(page.locator('#asSel .term-context')).to_have_count(0)
                ask()
                assert 'term_context' not in sent[-1]
                prepare_term().locator('[data-act="ask-term"]').click()
                page.locator('[data-act="clear-term-context"]').click()
                expect(page.locator('#asSel .term-context')).to_have_count(0)
                prepare_term().locator('[data-act="ask-term"]').click()
                page.locator('#shellNav [data-sec="library"]').click()
                expect(page.locator('#libList')).to_be_visible()
                open_case(2)
                expect(page.locator('#asSel .term-context')).to_have_count(0)
                passed.append('version_route_unrelated_draft_and_cancel_clear_term_context')

                text = '对方说合同规定收益每月到账，退款要提前30天申请。'
                before = context.request.get(base + '/api/cases/' + fixture['id']).json()
                answer, payload = ask(text)
                assert any(action['type'] == 'offer_material' for action in payload['actions']), payload
                answer.get_by_role('button', name='加入案卷，重新判断', exact=True).click()
                expect(page.locator('#supDlg')).to_be_visible()
                expect(page.locator('#supForm textarea[name="text"]')).to_have_value(text)
                page.screenshot(path=str(out / '06-material-offer-draft.png'))
                after = context.request.get(base + '/api/cases/' + fixture['id']).json()
                assert after['versions'] == before['versions'] and after['raw'] == before['raw']
                page.locator('#supDlg .dlg-x').click()
                passed.append('actual_material_offer_opens_user_text_draft_without_writing_report')

                page.set_viewport_size({'width':390, 'height':844})
                prepare_term().locator('[data-act="ask-term"]').click()
                expect(page.locator('#asSel .term-context')).to_be_visible()
                assert page.locator('#asSel').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
                assert page.locator('#assist').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
                page.screenshot(path=str(out / '07-mobile-term-context.png'))
                page.locator('[data-act="clear-term-context"]').click()
                ask('我想哭')
                assert 'term_context' not in sent[-1]
                passed.append('mobile_term_context_is_visible_and_has_no_horizontal_overflow')

                other = browser.new_context()
                assert other.request.get(base + '/api/cases/' + fixture['id']).status == 404
                other.close()
                assert not errors, errors
                assert not external, external
                passed += ['other_visitor_cannot_read_fixture', 'no_browser_errors_or_external_requests']
                browser.close()
                result = {'passed':passed, 'count':len(passed), 'external_calls':0,
                          'chat_requests':len(sent), 'screenshots':str(out)}
                print(json.dumps(result, ensure_ascii=False))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', type=int)
    parser.add_argument('--out', type=Path, default=ROOT / '.tmp' / 'conversation-tools-acceptance')
    args = parser.parse_args()
    serve(args.serve) if args.serve else run(args.out.resolve())
