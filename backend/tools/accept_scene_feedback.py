"""Check the built desktop scene with localhost-only fixtures; no paid queries.

Build research-room with build:home and serve FastAPI first, then run:
  python tools/accept_scene_feedback.py --url http://127.0.0.1:8001
Requires requirements-browser.txt and Edge or Playwright Chromium.
"""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from playwright.async_api import async_playwright


async def run(base):
    root = Path(__file__).resolve().parents[2]
    (root / '.tmp').mkdir(exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='scene-feedback-', dir=root / '.tmp'))
    errors, writes = [], []
    async with async_playwright() as p:
        edge = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
        browser = await p.chromium.launch(headless=True, **({'executable_path': str(edge)} if edge.exists() else {}))

        async def start(fixture, company='杭州示例科技有限公司', reduced=False, pause=False):
            page = await browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce' if reduced else 'no-preference')
            page.on('pageerror', lambda e: errors.append(str(e)))

            async def guard(route):
                if route.request.method not in ('GET', 'HEAD'):
                    writes.append(route.request.url)
                    await route.abort()
                else:
                    await route.continue_()
            await page.route('**/api/**', guard)
            await page.goto(base + '/?animationTest=' + fixture, wait_until='networkidle')
            await page.locator('.test-mode-badge').wait_for()
            await page.locator('#company-query').fill(company)
            await page.get_by_role('button', name='开始查询', exact=True).click()
            if pause:
                await page.get_by_role('button', name='暂停动画', exact=True).click()
            return page

        # Real changing styles, not a screenshot of a permanently lit label.
        page = await start('report-slow')
        await page.locator('.scene-status-running').wait_for()
        values = await page.locator('.scene-message-type').evaluate('''async e => {
          const values=[];for(let n=0;n<10;n++){values.push(+getComputedStyle(e).opacity);await new Promise(r=>setTimeout(r,310))}return values;
        }''')
        assert max(values) - min(values) > .3, values
        assert await page.locator('.live-status').is_hidden()
        assert await page.locator('.scene-status-complete').count() == 0
        await page.get_by_role('button', name='任务与动作详情', exact=True).click()
        assert await page.locator('.live-inspector .stage-progress li').count() == 5
        await page.get_by_role('button', name='关闭任务详情', exact=True).click()
        for width, height in [(1280, 720), (1440, 900), (1920, 1080)]:
            await page.set_viewport_size({'width': width, 'height': height})
            await page.wait_for_timeout(150)
            room = await page.locator('.office-stage').bounding_box()
            text = await page.locator('.scene-message-type').bounding_box()
            badge = await page.locator('.source-social').bounding_box()
            clock = await page.locator('.clock-progress').bounding_box()
            assert badge['x'] + badge['width'] < clock['x']
            assert (text['x'] - room['x']) / room['width'] > .335
            assert (text['x'] + text['width'] - room['x']) / room['width'] < .605
            assert (text['y'] - room['y']) / room['height'] > .49
            assert (text['y'] + text['height'] - room['y']) / room['height'] < .623
        await page.set_viewport_size({'width': 1440, 'height': 900})
        await page.screenshot(path=str(out / 'generating.png'))
        await page.close()
        print('Generating breath, on-demand detail, clear clock and desktop positioning: PASS', flush=True)

        page = await start('fast')
        await page.locator('.scene-status-complete').wait_for()
        await page.wait_for_timeout(850)
        scale = await page.locator('.scene-message-type').evaluate('(e)=>new DOMMatrixReadOnly(getComputedStyle(e).transform).a')
        assert scale > 1.14, scale
        await page.screenshot(path=str(out / 'complete-flash.png'))
        await page.locator('.dossier-settled').wait_for()
        await page.wait_for_function("+getComputedStyle(document.querySelector('.scene-status-complete')).opacity < .01")
        assert await page.locator('.dossier-inscription small').count() == 0
        assert await page.locator('.dossier-inscription strong').text_content() == '杭州示例科技有限公司'
        assert await page.locator('.cover-name-main').text_content() == '杭州示例科技'
        assert await page.locator('.cover-name-suffix').text_content() == '有限公司'
        assert await page.locator('.name-scrollable').count() == 0
        values = await page.locator('.dossier-book').evaluate('''async e => {
          const values=[];for(let n=0;n<11;n++){values.push(parseFloat(getComputedStyle(e).translate.split(' ')[1]));await new Promise(r=>setTimeout(r,330))}return values;
        }''')
        assert max(values) - min(values) > 3.4, values
        await page.locator('.dossier-hit-area').hover()
        await page.wait_for_timeout(300)
        hover = await page.locator('.dossier-book').evaluate('(e)=>getComputedStyle(e).translate')
        assert hover == '0px -8px', hover
        await page.screenshot(path=str(out / 'book-hover.png'))
        await page.get_by_role('button', name='任务与动作详情', exact=True).click()
        await page.get_by_role('button', name='关闭任务详情', exact=True).click()
        assert float(await page.locator('.scene-status-complete').evaluate('(e)=>getComputedStyle(e).opacity')) < .01
        await page.locator('.dossier-hit-area').click()
        await page.get_by_role('dialog', name='测试结果').wait_for()
        await page.get_by_role('button', name='关闭', exact=True).click()
        await page.get_by_role('button', name='切换公司', exact=True).click()
        assert await page.locator('.scene-status').count() == 0
        await page.close()
        print('Confirmed save flashes once, fades, readable cover, idle/hover and report entry: PASS', flush=True)

        async def recovery(fixture):
            page = await start(fixture)
            await page.locator('.scene-status-attention').wait_for()
            assert await page.locator('.scene-status-complete').count() == 0
            assert await page.get_by_role('progressbar').get_attribute('aria-valuenow') != '100'
            if fixture == 'save-unconfirmed':
                await page.get_by_role('button', name='保存未确认，点击重试', exact=True).click()
                await page.locator('.scene-status-complete').wait_for()
            elif fixture == 'save-failed':
                await page.get_by_role('button', name='保存失败，点击重试', exact=True).click()
                await page.get_by_role('button', name='确认重新查询', exact=True).click()
                await page.locator('.scene-status-complete').wait_for()
            else:
                assert await page.get_by_role('button', name='重新查询', exact=True).is_visible()
            await page.close()
        await asyncio.gather(*(recovery(f) for f in ['save-unconfirmed', 'save-failed', 'disconnect']))
        print('Save unconfirmed / failed / disconnect stay truthful and recoverable: PASS', flush=True)

        page = await start('switch', pause=True)
        await page.locator('.scene-status-complete').wait_for()
        assert await page.get_by_role('progressbar').get_attribute('aria-valuenow') == '100'
        await page.wait_for_function("+getComputedStyle(document.querySelector('.scene-status-complete')).opacity < .01")
        await page.get_by_role('button', name='报告已就绪 · 查看报告', exact=True).click()
        await page.get_by_role('dialog', name='测试结果').wait_for()
        await page.close()
        print('Paused actor still allows save acknowledgement, fade and immediate report access: PASS', flush=True)

        long_name = '长' * 76 + '有限公司'
        page = await start('fast', company=long_name, reduced=True)
        await page.locator('.dossier-settled').wait_for()
        assert await page.locator('.dossier-inscription strong').text_content() == long_name
        assert await page.locator('.dossier-name-field').get_attribute('title') == long_name
        assert await page.locator('.name-scrollable').count() == 1
        assert await page.locator('.dossier-book').evaluate('(e)=>getComputedStyle(e).animationName') == 'none'
        assert await page.locator('.scene-message-type').evaluate('(e)=>getComputedStyle(e).animationName') == 'none'
        await page.wait_for_function("+getComputedStyle(document.querySelector('.scene-status-complete')).opacity < .01")
        await page.close()
        assert not errors, errors
        assert not writes, writes
        print('Long names retained; reduced-motion preference honored; no script errors or API writes: PASS', flush=True)
        print(json.dumps({'screenshots': str(out), 'errors': errors, 'api_writes': writes}, ensure_ascii=False))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    args = parser.parse_args()
    target = urlsplit(args.url)
    if target.scheme != 'http' or target.hostname not in ('localhost', '127.0.0.1') or target.username or target.password:
        parser.error('Use a localhost HTTP server; this check never drives a public site.')
    asyncio.run(run(args.url.rstrip('/')))
