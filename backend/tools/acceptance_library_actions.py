"""Offline Edge acceptance for explanation -> library actions.

All cases, accounts/storage and source records are isolated fixtures. No model,
company lookup, deployed case, or real account is used. Requires Playwright.
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
            raise AssertionError('External network disabled in library acceptance')
        return connect(sock, address)

    socket.socket.connect = local_connect
    import uvicorn
    import app.main as main
    from app import privacy
    from app.models import ChatMessage, Term
    from tests import helpers

    main.app.debug = True  # Isolated fixtures only; surface setup errors to the runner.

    helpers.svc.web = helpers.svc.commercial = None
    main.svc.web = main.svc.commercial = None

    @main.app.post('/api/__library_seed')
    def seed():
        cases = {}
        for kind in ('fresh', 'another', 'old', 'multi', 'blocked'):
            case = helpers.make_case(helpers.DEMO_COMPANY, need='合成收藏功能验收')
            case.owner_id = privacy.identity()
            if kind in {'old', 'multi'}:
                terms = [Term(id='paid_capital', term='实缴资本', plain='合成旧版解释快照：保留本版原文。',
                              why='合成例外条件不省略。', law='合成解释依据，仅用于功能验收')]
                if kind == 'multi':
                    terms.append(Term(id='reg_capital', term='注册资本', plain='合成第二个词的解释。'))
                case.chat = [ChatMessage(role='assistant', answer_kind='glossary',
                    knowledge_terms=terms, text='\n'.join(t.term + '：' + t.plain for t in terms),
                    version=1, created_at='2026-10-04T00:00:00Z', mode='template')]
            if kind == 'old':
                version = case.versions[0].model_copy(deep=True, update={'no': 2,
                    'trigger': 'need', 'trigger_label': '合成第二版'})
                case.versions.append(version)
                case.current = 2
            main.store.save(case)
            cases[kind] = case.id
        return cases

    main.app.router.routes.insert(0, main.app.router.routes.pop())
    uvicorn.run(main.app, host='127.0.0.1', port=port, log_level='warning')


def run(out):
    from playwright.sync_api import sync_playwright, expect

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='qier-library-') as directory:
        env = dict(os.environ)
        for name in ('CASES', 'CACHE', 'REVIEWS', 'RUNS', 'PRIVATE', 'CASE_MEMORY', 'DEMO_PREBUILT'):
            env[f'XRAY_{name}_DIR'] = str(Path(directory) / name.lower())
        env.update(XRAY_LLM_MODE='off', XRAY_COMMERCIAL='', XRAY_AMAC_DETAIL='0', XRAY_CNINFO='0',
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
                        assert json.load(response)['llm']['mode'] == 'off'
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError('Isolated library server exited')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated library server did not start')
            with sync_playwright() as pw:
                edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
                browser = pw.chromium.launch(headless=True, **({'executable_path': str(edge)} if edge.exists() else {}))
                context = browser.new_context(viewport={'width': 1600, 'height': 1050}, reduced_motion='reduce')
                context.set_default_timeout(15000)
                context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                seeded = context.request.post(base + '/api/__library_seed')
                assert seeded.ok, seeded.text()
                ids = seeded.json()
                page = context.new_page()
                errors, passed = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def open_case(key):
                    page.goto(base + '/xray/#/case/' + ids[key], wait_until='domcontentloaded')
                    page.wait_for_function('(id) => typeof S !== "undefined" && S.case?.id === id && !!document.querySelector("#research-overview")', arg=ids[key])
                    if not page.locator('#assist').evaluate('(e) => e.classList.contains("open")'):
                        page.locator('.workspace-assistant-toggle').click()

                def ask(text):
                    count = page.locator('#asBody .msg.ai').count()
                    page.locator('#asForm textarea').fill(text)
                    page.locator('#asForm button[type="submit"]').click()
                    page.wait_for_function('(count) => !S.busy && document.querySelectorAll("#asBody .msg.ai").length > count', arg=count)
                    return page.locator('#asBody .msg.ai').last

                def library():
                    return page.evaluate('JSON.parse(localStorage.getItem("xray.library") || "[]")')

                open_case('fresh')
                answer = ask('什么是实缴资本')
                expect(answer.locator('[data-act="chat-lib-save"]')).to_have_count(1)
                passed.append('glossary_has_save_button')
                answer = ask('将这一词收藏进知识库')
                expect(answer).to_contain_text('知识库操作')
                assert len(library()) == 1 and library()[0]['id'] == 'paid_capital'
                assert library()[0]['seen'][0]['version'] == 1
                assert library()[0]['seen'][0]['caseId'] == ids['fresh']
                expect(answer).to_contain_text(re.compile('已.*保存在|已.*保存|已.*收藏'))
                page.screenshot(path=str(out / 'chat-save.png'))
                passed.append('natural_command_saves_exact_term')
                ask('收藏这个词')
                assert len(library()) == 1
                passed.append('repeated_command_is_idempotent')
                open_case('another')
                answer = ask('什么是实缴资本')
                expect(answer.locator('[data-act="chat-lib-save"]')).to_be_enabled()
                answer.locator('[data-act="chat-lib-save"]').click()
                page.wait_for_function('JSON.parse(localStorage.getItem("xray.library")||"[]")[0]?.seen.length === 2')
                assert len(library()) == 1
                assert {source['caseId'] for source in library()[0]['seen']} == {ids['fresh'], ids['another']}
                expect(answer.locator('[data-act="chat-lib-save"]')).to_be_disabled()
                passed.append('same_term_button_records_another_report_source')
                page.locator('#shellNav [data-sec="library"]').click()
                expect(page.locator('#libList')).to_contain_text('实缴资本')
                page.screenshot(path=str(out / 'saved-library.png'))
                page.locator('[data-act="lib-remove"]').click()
                assert library() == []
                open_case('fresh')
                expect(page.locator('[data-act="chat-lib-save"]').first).to_be_enabled()
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function('typeof S !== "undefined" && S.case && !S.busy')
                assert library() == []
                passed += ['saved_term_visible_in_library', 'history_reload_never_resaves_removed_term']

                open_case('old')
                page.locator('[data-act="chat-lib-save"][data-term="paid_capital"]').click()
                page.wait_for_function('JSON.parse(localStorage.getItem("xray.library")||"[]").length === 1')
                old = library()[0]
                assert old['plain'] == '合成旧版解释快照：保留本版原文。'
                assert old['seen'][0]['version'] == 1 and old['seen'][0]['caseId'] == ids['old']
                assert old['basis'] == '合成解释依据，仅用于功能验收'
                passed.append('old_message_uses_its_snapshot_and_version')

                open_case('multi')
                before = library()
                answer = ask('收藏这个词')
                expect(answer.locator('[data-act="chat-lib-save"]')).to_have_count(2)
                assert library() == before
                answer.locator('[data-act="chat-lib-save"][data-term="reg_capital"]').click()
                page.wait_for_function('JSON.parse(localStorage.getItem("xray.library")||"[]").length === 2')
                passed.append('ambiguous_terms_require_explicit_choice')

                open_case('blocked')
                answer = ask('收藏这个词')
                assert not answer.locator('[data-act="chat-lib-save"]').count()
                passed.append('missing_context_does_not_invent_a_term')
                ask('什么是存续')
                before = library()
                page.evaluate('''() => { const original = Storage.prototype.setItem;
                    Storage.prototype.setItem = function(key,value) {
                        if(key === 'xray.library') throw new DOMException('Synthetic blocked storage','QuotaExceededError');
                        return original.call(this,key,value);
                    }; }''')
                answer = ask('把刚才的解释记下来')
                assert library() == before
                expect(answer).to_contain_text(re.compile('未保存|无法保存|存储'))
                page.screenshot(path=str(out / 'blocked-storage.png'))
                passed.append('blocked_storage_never_claims_success')

                # Mock only the account-library transport: no real account is
                # created. Real chat, action resolution and local persistence
                # still run, and the account-owner request header is checked.
                # Navigating to an identical hash URL can be same-document.
                # Reload explicitly to remove the storage-failure test override.
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function('typeof S !== "undefined" && S.case && !!document.querySelector("#research-overview")')
                if not page.locator('#assist').evaluate('(e) => e.classList.contains("open")'):
                    page.locator('.workspace-assistant-toggle').click()
                account_transport = {'fail': True, 'saved': [], 'headers': []}

                def account_library(route):
                    request = route.request
                    account_transport['headers'].append(request.headers.get('x-xray-library-owner'))
                    if request.method == 'GET':
                        route.fulfill(json=account_transport['saved'])
                    elif account_transport['fail']:
                        route.fulfill(status=503, json={'detail': '合成账号同步失败'})
                    else:
                        account_transport['saved'] = request.post_data_json
                        route.fulfill(json=account_transport['saved'])

                page.route('**/api/me/library', account_library)
                page.evaluate('''() => { S.session = {...S.session, account:{id:'synthetic-account',
                    email:'library-fixture@example.test'}}; }''')
                ask('什么是存续')
                answer = ask('收藏这个词')
                expect(answer).to_contain_text('账号同步未完成')
                assert any(entry['term'] == '存续' for entry in library())
                assert account_transport['headers'] and set(account_transport['headers']) == {'library-fixture@example.test'}
                passed.append('account_sync_failure_reports_local_save_only')
                account_transport['fail'] = False
                answer.locator('[data-act="chat-lib-save"]').click()
                expect(answer).to_contain_text('已保存并同步到账号')
                assert any(entry['term'] == '存续' for entry in account_transport['saved'])
                assert not page.evaluate('LibraryActions.hasPending()')
                page.screenshot(path=str(out / 'account-sync.png'))
                passed.append('account_retry_confirms_only_after_server_ack')

                other = browser.new_context()
                unauthorized = other.request.get(base + '/api/cases/' + ids['fresh'])
                assert unauthorized.status == 404
                other.close()
                assert not errors, errors
                passed += ['other_visitor_still_cannot_read_case', 'no_browser_errors']
                browser.close()
                print(json.dumps({'passed': passed, 'count': len(passed), 'external_calls': 0,
                                  'screenshots': str(out)}, ensure_ascii=False))
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
    parser.add_argument('--out', type=Path, default=ROOT / '.tmp' / 'library-actions-acceptance')
    args = parser.parse_args()
    serve(args.serve) if args.serve else run(args.out.resolve())
