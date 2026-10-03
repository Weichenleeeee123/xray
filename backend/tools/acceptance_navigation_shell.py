"""Offline browser regression for report shells and navigation to the homepage.

Runs the real app with temporary storage and fictional fixtures. Finite server
delays keep each outgoing document alive long enough to sample rendered frames;
no Playwright navigation route is held indefinitely. No deployed cases or paid
services are used. Requires Playwright and Edge (or Playwright Chromium).
"""
import argparse
import asyncio
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


def serve(port):
    # Install the guard before importing application services.
    original_connect = socket.socket.connect

    def offline_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'127.0.0.1', '::1'}:
            raise AssertionError('External network disabled during navigation acceptance')
        return original_connect(sock, address)

    socket.socket.connect = offline_connect
    import uvicorn
    from fastapi import Request
    from fastapi.responses import JSONResponse
    import app.main as main
    from app import privacy
    from tests import helpers

    helpers.svc.web = helpers.svc.commercial = None
    main.svc.web = main.svc.commercial = None
    state = {'home_delay': 0.8, 'reads': {}, 'requests': []}

    @main.app.middleware('http')
    async def finite_fixture_delay(request, call_next):
        path = request.url.path
        if path == '/':
            state['requests'].append(path)
            await asyncio.sleep(state['home_delay'])
        rule = state['reads'].get(path) if request.method == 'GET' else None
        if rule:
            await asyncio.sleep(rule.get('delay', 0))
            if rule.get('failures', 0):
                rule['failures'] -= 1
                return JSONResponse({'detail': '合成验收：暂时无法读取，请重试'}, status_code=503)
        return await call_next(request)

    @main.app.post('/api/__navigation_seed')
    def seed():
        ids = []
        for need in ('合成导航验收：查看企业资料', '合成导航验收：核对第二份资料'):
            case = helpers.make_case(helpers.DEMO_COMPANY, need=need)
            case.owner_id = privacy.identity()
            main.store.save(case)
            ids.append(case.id)
        return {'ids': ids, 'synthetic_only': True}

    main.app.router.routes.insert(0, main.app.router.routes.pop())

    @main.app.post('/api/__navigation_control')
    async def control(request: Request):
        update = await request.json()
        state['reads'] = update.get('reads', {})
        return {'ok': True}

    main.app.router.routes.insert(0, main.app.router.routes.pop())
    uvicorn.run(main.app, host='127.0.0.1', port=port, log_level='warning')


# sessionStorage survives navigation within the test origin. Sampling with rAF
# observes the outgoing DOM while the delayed home document is still pending.
FRAME_PROBE = r"""(() => {
  let active = false;
  let frames = [];
  const snapshot = event => {
    const body = document.body, top = document.querySelector('#topbar');
    if (!body || !top) return;
    const nav = document.querySelector('#shellNav');
    const icon = document.querySelector('.collection-header-actions svg');
    const frame = {event, time:performance.now(), hash:location.hash,
      classes:body.className, navParent:nav?.parentElement?.className || '',
      navItems:nav?.childElementCount || 0,
      topbarColor:getComputedStyle(top).backgroundColor,
      title:document.querySelector('h1')?.textContent || '',
      view:document.querySelector('#view')?.textContent?.trim().slice(0, 100) || '',
      iconWidth:icon ? icon.getBoundingClientRect().width : null};
    frames.push(frame);
    if (frames.length > 300) frames.shift();
    sessionStorage.setItem('__navigation_frames', JSON.stringify(frames));
  };
  window.__startNavigationProbe = () => {
    frames = []; active = true;
    sessionStorage.removeItem('__navigation_frames');
    snapshot('start');
  };
  addEventListener('hashchange', () => {if(active) snapshot('hashchange');});
  addEventListener('pagehide', () => {if(active) snapshot('pagehide');});
  const sample = () => {
    if (active) snapshot('frame');
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
  // Also capture the first paint of cold report routes.
  if (/^#\/case\//.test(location.hash)) window.__startNavigationProbe();
})();"""


def frames(page):
    return page.evaluate("JSON.parse(sessionStorage.getItem('__navigation_frames') || '[]')")


def assert_workspace(samples, *, collections=False):
    assert samples, 'Expected rendered-frame samples'
    for sample in samples:
        classes = sample['classes'].split()
        assert 'research-mode' in classes, sample
        assert 'report-workspace' in classes, sample
        if sample['navItems']:
            assert 'workspace-global-nav' in sample['navParent'], sample
        if collections:
            assert 'collections-mode' in classes, sample
            if sample['iconWidth'] is not None:
                assert 0 < sample['iconWidth'] <= 24, sample


def run(out):
    from playwright.sync_api import sync_playwright, expect

    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='qier-navigation-') as data_dir:
        data = Path(data_dir)
        env = dict(os.environ)
        for name in ('CASES', 'CACHE', 'REVIEWS', 'RUNS', 'PRIVATE', 'CASE_MEMORY', 'DEMO_PREBUILT'):
            env[f'XRAY_{name}_DIR'] = str(data / name.lower())
        env.update(XRAY_LLM_MODE='off', XRAY_COMMERCIAL='', XRAY_AMAC_DETAIL='0', XRAY_CNINFO='0',
                   XRAY_WEB_DISCOVERY='0', XRAY_WEB_DISCOVERY_LLM='0', XRAY_RESEND_KEY='',
                   XRAY_QUOTA_GUEST='0', XRAY_QUOTA_IP='0', XRAY_QUOTA_ACCOUNT='0')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        proc = subprocess.Popen([sys.executable, __file__, '--serve', str(port)], cwd=BASE, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        passed = []
        measurements = {}
        blocked_external = []
        try:
            for _ in range(150):
                try:
                    with urlopen(base + '/api/health', timeout=1) as response:
                        assert json.load(response)['llm']['mode'] == 'off'
                    break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError('Isolated server exited before startup')
                    time.sleep(.1)
            else:
                raise RuntimeError('Isolated server did not start')

            with sync_playwright() as pw:
                edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
                browser = pw.chromium.launch(headless=True, **({'executable_path': str(edge)} if edge.exists() else {}))
                context = browser.new_context(viewport={'width': 1600, 'height': 960}, reduced_motion='reduce')
                context.set_default_timeout(10000)
                context.set_default_navigation_timeout(15000)
                context.add_init_script(FRAME_PROBE)

                def local_only(route):
                    if route.request.url.startswith(base + '/'):
                        route.continue_()
                    else:
                        blocked_external.append(route.request.url)
                        route.abort()

                context.route('**/*', local_only)
                seed = context.request.post(base + '/api/__navigation_seed')
                assert seed.ok, seed.text()
                first, second = seed.json()['ids']
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def control(**rules):
                    response = context.request.post(base + '/api/__navigation_control', data={'reads': rules})
                    assert response.ok, response.text()

                def loaded_report(case_id):
                    page.wait_for_function('(id) => typeof S !== "undefined" && S.case?.id === id && !!document.querySelector("#research-overview")', arg=case_id)
                    expect(page.locator('.workspace-sidebar')).to_be_visible()

                def home_transition(route, *, legacy=None):
                    page.goto(base + '/xray/' + route, wait_until='domcontentloaded')
                    if route.startswith('#/case/'):
                        loaded_report(route.removeprefix('#/case/'))
                    else:
                        expect(page.locator('.collection-header-actions')).to_be_visible()
                        page.wait_for_function('document.body.classList.contains("report-workspace")')
                    page.evaluate('window.__startNavigationProbe()')
                    if legacy:
                        page.evaluate('(hash) => {location.hash = hash}', legacy)
                    else:
                        page.locator('#shellNav [data-sec="check"]').click(no_wait_after=True)
                    page.wait_for_url(base + '/', wait_until='domcontentloaded')
                    samples = frames(page)
                    assert len([sample for sample in samples if sample['event'] == 'frame']) >= 8, samples
                    assert_workspace(samples, collections=not route.startswith('#/case/'))
                    if not legacy:
                        assert all(sample['hash'] == route for sample in samples), samples
                    else:
                        assert any(sample['hash'] == legacy for sample in samples), samples
                    key = route.split('/')[1] + ('_legacy_' + legacy.split('/')[-1] if legacy else '_direct_home')
                    measurements[key] = {'frames': len(samples), 'first': samples[0], 'last': samples[-1]}
                    passed.append(key)
                    if not legacy:
                        page.go_back(wait_until='domcontentloaded')
                        assert page.url.endswith('/xray/' + route), page.url
                        if route.startswith('#/case/'):
                            loaded_report(route.removeprefix('#/case/'))
                        else:
                            expect(page.locator('.collection-header-actions')).to_be_visible()
                        page.evaluate('window.__startNavigationProbe()')
                        page.wait_for_timeout(60)
                        assert_workspace(frames(page), collections=not route.startswith('#/case/'))
                        page.go_forward(wait_until='domcontentloaded')
                        assert page.url == base + '/', page.url
                        passed.append(key + '_browser_history')

                for route in ('#/library', '#/cases', '#/case/' + first):
                    home_transition(route)
                for legacy in ('#/check', '#/new'):
                    home_transition('#/library', legacy=legacy)

                # Direct '/' never traverses the legacy report hash router.
                page.goto(base + '/', wait_until='domcontentloaded')
                assert page.url == base + '/'
                expect(page.locator('#topbar')).to_have_count(0)
                passed.append('direct_home_document')

                # Delay both a cold report and a different report requested from
                # an existing one; inspect loading and failure before retry.
                first_path = '/api/cases/' + first
                second_path = '/api/cases/' + second
                control(**{first_path: {'delay': 1.0, 'failures': 1}})
                page.goto(base + '/xray/#/case/' + first, wait_until='domcontentloaded')
                expect(page.locator('#view')).to_contain_text('读取案卷')
                page.wait_for_timeout(120)
                assert_workspace(frames(page))
                page.screenshot(path=str(out / 'cold-report-loading.png'))
                expect(page.locator('#view')).to_contain_text('打不开这个案卷')
                assert_workspace(frames(page))
                page.locator('[data-act="retry-read"]').click()
                expect(page.locator('#view')).to_contain_text('读取案卷')
                loaded_report(first)
                passed += ['cold_report_loading_shell', 'cold_report_error_shell', 'cold_report_retry']

                control(**{second_path: {'delay': .9, 'failures': 1}})
                page.evaluate('window.__startNavigationProbe()')
                page.evaluate('(hash) => {location.hash = hash}', '#/case/' + second)
                expect(page.locator('#view')).to_contain_text('读取案卷')
                page.wait_for_timeout(120)
                assert_workspace(frames(page))
                expect(page.locator('#view')).to_contain_text('打不开这个案卷')
                assert_workspace(frames(page))
                page.screenshot(path=str(out / 'changed-report-error.png'))
                page.locator('[data-act="retry-read"]').click()
                expect(page.locator('#view')).to_contain_text('读取案卷')
                loaded_report(second)
                assert_workspace(frames(page))
                passed += ['changed_report_loading_shell', 'report_error_shell', 'report_failure_retry']

                # Browser history restores the matching modern layout.
                control()
                page.locator('#shellNav [data-sec="library"]').click()
                expect(page.locator('.collection-header-actions')).to_be_visible()
                page.go_back(wait_until='domcontentloaded')
                loaded_report(second)
                page.go_forward(wait_until='domcontentloaded')
                expect(page.locator('.collection-header-actions')).to_be_visible()
                page.evaluate('window.__startNavigationProbe()')
                page.wait_for_timeout(60)
                assert_workspace(frames(page), collections=True)
                passed.append('back_forward_workspace')

                # Explicit classic report URLs keep their established layout,
                # including their finite loading and failed-read states.
                control(**{first_path: {'delay': .9, 'failures': 1}})
                page.goto(base + '/xray/?classic#/case/' + first, wait_until='domcontentloaded')
                expect(page.locator('#view')).to_contain_text('读取案卷')
                page.wait_for_timeout(60)
                assert all('research-mode' not in sample['classes'].split() for sample in frames(page)), frames(page)
                expect(page.locator('#view')).to_contain_text('打不开这个案卷')
                page.locator('[data-act="retry-read"]').click()
                expect(page.locator('.case-head')).to_be_visible()
                assert page.locator('body').get_attribute('class') in (None, '')
                passed.append('classic_loading_error_and_report')
                assert not errors, errors
                passed.append('no_browser_errors')
                browser.close()

            result = {'passed': passed, 'measurements': measurements, 'external_calls': 0,
                      'blocked_external_requests': len(blocked_external), 'screenshots': str(out)}
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
    parser.add_argument('--out', type=Path, default=ROOT / '.tmp' / 'navigation-shell-acceptance')
    args = parser.parse_args()
    serve(args.serve) if args.serve else run(args.out.resolve())
