"""Offline browser acceptance for the timeline and four signal detail dialogs.

Uses a temporary FastAPI instance and a new guest's fictional demo case. Dense
layout fixtures are intercepted in this test browser only, never saved as facts.
No production server, existing private case or paid API is used.
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


def serve(port):
    import uvicorn
    from app.main import app
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


def layout_fixture(case):
    """Keep the real response contract; all added values are synthetic test data."""
    version = case['versions'][-1]
    raw = next(r for r in case['raw'] if r['id'] in version['raw_ids'])

    def item(key, label, value, status='warn', detail='布局验收的虚构记录，不构成公司事实。'):
        return dict(key=key, label=label, value=value, status=status, detail=detail,
                    source=raw['source_id'], ref=raw['id'])

    credit = next(s for s in version['signals'] if s['key'] == 'credit')
    credit['items'] = [
        item('layout_counts', '其他风险记录', '裁判文书 3297、立案信息 3607、开庭公告 3645、法院公告 416、送达公告 350、诉前调解 43、劳动仲裁 5、公示催告 3',
             detail='布局验收的分类统计，各条记录可能关联或重叠；条数不代表已确认的责任，不合计。'),
        item('layout_labor', '劳动仲裁和劳动纠纷', '劳动仲裁 5 条，当被告的劳动官司 1 条',
             detail='这是虚构的布局测试说明。' + '；'.join(f'2025-02-{i:02d}，第 {i} 条虚构明细，保留日期和完整文字' for i in range(1, 6))),
        item('layout_missing', '尚未覆盖的资料', '未覆盖', 'none'),
        item('layout_ok', '其他核查项', '存续', 'ok'),
    ]
    for sig in version['signals']:
        sig['lede'] = '布局验收使用虚构记录；仅检查展示与交互。'
    version['charts'] = [c for c in version['charts'] if c['kind'] != 'timeline'] + [{
        'kind': 'timeline', 'id': 'layout_timeline', 'note': '布局验收虚构时间线，不代表真实公司事件。',
        'events': [dict(date=date, label=label, tone='warn', ref=raw['id']) for date, label in [
            ('1987-09-15', '公司成立（虚构）'),
            ('2025-02-18', '第一条资料记录，完整的较长标题保留在这里'),
            ('2025-02-18', '同一天的另一条记录，不擅自合并'),
            ('2025-02-18', '第三条虚构记录'),
            ('2025-04-19', '最后一条记录，用于检查连接线的末端'),
        ]],
    }]
    return case


def run(out):
    from playwright.sync_api import sync_playwright, expect
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix='qier-report-layout-'))
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
    try:
        for _ in range(150):
            try:
                with urlopen(base + '/api/health', timeout=1) as response:
                    assert json.load(response)['llm']['mode'] == 'off'
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Temporary server did not start')
        with sync_playwright() as pw:
            edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            browser = pw.chromium.launch(headless=True, **({'executable_path': str(edge)} if edge.exists() else {}))
            ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
            demo = ctx.request.get(base + '/api/demo?case=C').json()
            response = ctx.request.post(base + '/api/cases', data=demo['input'])
            assert response.ok, response.text()
            case = layout_fixture(response.json())
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route(base + '/api/cases/' + case['id'], lambda route: route.fulfill(json=case))
            page.goto(base + '/xray/#/case/' + case['id'])
            page.wait_for_function('S.case && document.querySelector(".timeline-axis")')
            assert page.locator('.timeline-stop').count() == 5
            page.locator('#research-details-tab-timeline').click()
            timeline = page.locator('#research-timeline')
            timeline.scroll_into_view_if_needed()
            page.mouse.move(0, 0)
            page.wait_for_timeout(400)
            # Track is independent of selection and is present between every node.
            track = page.locator('.timeline-axis').evaluate_all('''els => els.map(el => {
              const s=getComputedStyle(el,'::before'), r=el.getBoundingClientRect();
              return {content:s.content,height:parseFloat(s.height),opacity:s.opacity,
                color:s.backgroundColor,display:s.display,x:r.x,width:r.width};
            })''')
            assert all(t['content'] != 'none' and t['height'] >= 1 and t['display'] != 'none' and t['opacity'] == '1' and t['color'] != 'rgba(0, 0, 0, 0)' for t in track)
            assert all(abs(a['x'] + a['width'] - b['x']) < 1 for a, b in zip(track, track[1:]))
            timeline.screenshot(path=str(out / 'timeline-idle.png'))
            passed.append('continuous_idle_track')
            for i in range(5):
                node = page.locator('.timeline-stop').nth(i)
                before = node.locator('.timeline-year').bounding_box()
                node.hover()
                page.wait_for_timeout(420)
                after = node.locator('.timeline-year').bounding_box()
                dot = node.locator('.timeline-dot').bounding_box()
                assert abs(before['y'] - after['y']) < 1
                assert dot['y'] - (after['y'] + after['height']) >= 10, (i, after, dot)
                expect(node).to_have_attribute('aria-pressed', 'true')
            timeline.screenshot(path=str(out / 'timeline-hover.png'))
            passed += ['stationary_years_and_clear_dots', 'hover_selection']
            page.locator('.timeline-stop').nth(1).focus()
            expect(page.locator('.timeline-stop').nth(1)).to_have_attribute('aria-pressed', 'true')
            passed.append('keyboard_timeline')

            for sig in case['versions'][-1]['signals']:
                page.locator(f'.signal-card[data-key="{sig["key"]}"]').click()
                dlg = page.locator('#signalDlg')
                expect(dlg).to_be_visible()
                expect(dlg.locator('.signal-total')).to_contain_text(f'{len(sig["items"])} 项核查项')
                assert dlg.locator('.signal-item').count() == len(sig['items'])
                assert dlg.locator('.signal-item').evaluate_all('els => els.every(el => parseFloat(getComputedStyle(el).paddingLeft) >= 20)')
                assert dlg.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
                dlg.screenshot(path=str(out / f'signal-{sig["key"]}.png'))
                if sig['key'] == 'credit':
                    assert dlg.locator('.signal-metrics dd').count() == 8
                    assert dlg.locator('.signal-value-prose').first.evaluate('el => parseFloat(getComputedStyle(el).fontSize)') <= 18
                    ask = dlg.locator('.ask').first
                    expect(ask).to_have_text('问小企')
                    ask.click()
                    expect(ask).to_have_text('已选')
                    expect(ask).to_have_attribute('aria-pressed', 'true')
                    ask.click()
                    expect(ask).to_have_text('问小企')
                    dlg.locator('[data-act="raw"]').first.click()
                    expect(page.locator('#rawDlg')).to_be_visible()
                    page.locator('#rawDlg [data-act="close-dlg"]').click()
                    expect(dlg).to_be_visible()
                    dlg.locator('.signal-records-more>summary').click()
                    expect(dlg.locator('.signal-records-more')).to_have_attribute('open', '')
                    assert dlg.locator('.signal-records li:visible').count() == 5
                    passed += ['selection_and_deselection', 'original_source_dialog', 'all_record_details']
                dlg.locator('.dlg-x').click()
                expect(dlg).not_to_be_visible()
                passed.append('signal_' + sig['key'])

            for width in (1280, 2560, 390):
                page.set_viewport_size({'width': width, 'height': 900})
                page.locator('.signal-card[data-key="credit"]').click()
                dlg = page.locator('#signalDlg')
                assert dlg.evaluate('el => el.scrollWidth <= el.clientWidth + 1')
                assert dlg.locator('.signal-item').evaluate_all('els => els.every(el => el.scrollWidth <= el.clientWidth + 1)')
                head_before = dlg.locator('.dlg-head').bounding_box()
                dlg.locator('.dlg-body').evaluate('el => el.scrollTop = el.scrollHeight')
                head_after = dlg.locator('.dlg-head').bounding_box()
                assert abs(head_before['y'] - head_after['y']) < 1
                expect(dlg.locator('.dlg-x')).to_be_visible()
                page.keyboard.press('Escape')
                expect(dlg).not_to_be_visible()
            passed.append('dialog_widths_fixed_header_and_escape')
            page.emulate_media(reduced_motion='reduce')
            page.set_viewport_size({'width': 1600, 'height': 1000})
            page.locator('#research-details-tab-timeline').click()
            page.locator('.timeline-stop').nth(2).focus()
            assert page.locator('.timeline-dot').nth(2).evaluate('el => getComputedStyle(el).transitionDuration') == '0s'
            assert not errors, errors
            passed += ['reduced_motion', 'no_browser_errors']
            browser.close()
        print(json.dumps({'passed': passed, 'screenshots': str(out), 'external_calls': 0}, ensure_ascii=False))
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
    parser.add_argument('--out', type=Path, default=ROOT / '.tmp' / 'report-layout-acceptance')
    args = parser.parse_args()
    serve(args.serve) if args.serve else run(args.out.resolve())
