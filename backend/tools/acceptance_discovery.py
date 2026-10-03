"""Isolated, offline Edge acceptance of discovery -> report -> Xiaoqi -> versions.

Uses synthetic public provider responses, a fresh guest and temporary storage.
No live model, corporate APIs, existing user data or deployment is touched.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
sys.path.insert(0, str(BASE))
NAME = '成都云笺科技有限公司'


def serve(port):
    import uvicorn
    import app.main as main
    from app.sources.discovery import discover, Policy
    from app.sources.web import WebFindings
    from app.sources.page_reader import PageRead

    class SyntheticWeb:
        configured = True
        mode = 'live'
        version = 0

        def find_official(self, name):
            return WebFindings(searched=True)

        def find_opinion(self, name):
            return WebFindings(searched=True), WebFindings(searched=True)

        def search(self, query, **kwargs):
            return [{'name': '官网 · 合成产品说明', 'url': 'https://synthetic.example/about',
                     'text': f'{NAME}旗下品牌“云笺协作”开发文档产品。资料版次{self.version}。'}], False

        def read(self, url, **kwargs):
            return PageRead(url, reason='synthetic_no_network')

        def discover(self, name):
            self.version += 1
            return discover(self, name, policy=Policy(reads=0, seconds=1), reader=self)

    main.svc.web = SyntheticWeb()
    uvicorn.run(main.app, host='127.0.0.1', port=port, log_level='warning')


def run():
    from playwright.sync_api import sync_playwright, expect
    data = Path(tempfile.mkdtemp(prefix='qier-discovery-browser-'))
    env = dict(os.environ)
    for name in ('CASES', 'CACHE', 'REVIEWS', 'RUNS', 'PRIVATE', 'CASE_MEMORY', 'DEMO_PREBUILT'):
        env[f'XRAY_{name}_DIR'] = str(data / name.lower())
    env.update(XRAY_LLM_MODE='off', XRAY_COMMERCIAL='', XRAY_AMAC_DETAIL='0', XRAY_CNINFO='0',
               XRAY_WEB_DISCOVERY='1', XRAY_WEB_DISCOVERY_LLM='0', XRAY_CASE_MEMORY_ENABLED='1',
               XRAY_ASSISTANT_CONTEXT_MODE='selective', XRAY_RESEND_KEY='',
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
                with urlopen(base + '/api/health', timeout=1) as r:
                    assert json.load(r)['web_discovery']['enabled']
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Preview server did not start')
        with sync_playwright() as pw:
            edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            browser = pw.chromium.launch(headless=True, **({'executable_path': str(edge)} if edge.exists() else {}))
            ctx = browser.new_context(viewport={'width': 1600, 'height': 1000}, reduced_motion='reduce')
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/')
            expect(page.locator('#company-query')).to_be_visible()
            expect(page.locator('#research-need')).to_be_visible()
            request = {'company_name': NAME, 'need': '了解品牌产品'}
            created = ctx.request.post(base + '/api/runs', data=request, headers={'Idempotency-Key': 'synthetic-public-once'})
            assert created.status == 202
            run_id = created.json()['run_id']
            assert ctx.request.post(base + '/api/runs', data=request, headers={'Idempotency-Key': 'synthetic-public-once'}).json()['run_id'] == run_id
            # Repeated polling is the same recovery contract used after a refresh.
            for _ in range(200):
                result = ctx.request.get(base + '/api/runs/' + run_id).json()
                if result['status'] != 'running':
                    break
                page.wait_for_timeout(30)
            assert result['status'] == 'complete'
            case_id = result['case_id']
            events = result['events']
            assert [(e['id'], e['phase']) for e in events if e.get('id') == 'web'] == [('web', 'start'), ('web', 'done')]
            case = ctx.request.get(base + '/api/cases/' + case_id).json()
            raw = next(r for r in case['raw'] if r.get('discovery'))
            assert raw['id'] in case['versions'][0]['raw_ids']
            page.goto(base + '/xray/#/case/' + case_id)
            page.wait_for_function('S.case && S.case.id === ' + json.dumps(case_id))
            page.locator('.source-collection > summary').click()
            group = page.locator('.source-entry').filter(has_text='企业公开资料与关联线索')
            group.locator('summary').click()
            group.locator('[data-act="raw"]').first.click()
            expect(page.locator('#rawDlg')).to_be_visible()
            expect(page.locator('#rawDlg')).to_contain_text('仅搜索摘要')
            expect(page.locator('#rawDlg')).to_contain_text('云笺协作')
            expect(page.locator('#rawDlg a[target="_blank"]').first).to_have_attribute('href', raw['url'])
            page.locator('#rawDlg [data-act="close-dlg"]').click()
            response = ctx.request.post(base + '/api/cases/' + case_id + '/chat',
                data={'text': '它有什么品牌和产品', 'refs': [raw['id']], 'version': 1})
            assert response.ok, response.text()
            reply = response.json()
            assert raw['id'] in reply['citations'] and '仅搜索摘要' in reply['text']
            page.reload()
            page.locator('.workspace-assistant-toggle').click()
            page.locator('[data-act="chat-sources"]').last.click()
            expect(page.locator('#rawDlg')).to_contain_text('原文出处 · 第 1 版')
            page.locator('#rawDlg [data-act="raw"]').click()
            expect(page.locator('#rawDlg')).to_contain_text('资料版次1')
            page.locator('#rawDlg [data-act="close-dlg"]').click()
            supplemented = ctx.request.post(base + '/api/cases/' + case_id + '/supplements',
                data={'kind': 'material', 'text': '合成私有材料，不应进入公开搜索。'})
            assert supplemented.ok and supplemented.json()['current'] == 2
            page.reload()
            page.locator('.workspace-assistant-toggle').click()
            page.locator('[data-act="chat-sources"]').last.click()
            page.locator('#rawDlg [data-act="raw"]').click()
            expect(page.locator('#rawDlg')).to_contain_text('资料版次1')
            expect(page.locator('#rawDlg')).not_to_contain_text('资料版次2')
            stranger = browser.new_context()
            assert stranger.request.get(base + '/api/cases/' + case_id).status == 404
            assert stranger.request.get(base + '/api/runs/' + run_id).status == 404
            assert not errors, errors
            browser.close()
            print(json.dumps({'passed': ['home_inputs', 'idempotent_run', 'progress_contract', 'version_sources',
                'existing_source_directory', 'raw_dialog_and_link', 'xiaoqi_retrieval', 'chat_source_entry',
                'historical_source_after_supplement', 'guest_isolation', 'no_browser_errors'],
                'external_calls': 0}, ensure_ascii=False))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', type=int)
    args = parser.parse_args()
    serve(args.serve) if args.serve else run()
