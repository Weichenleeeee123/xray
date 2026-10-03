import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('home menu lists all five functions in order and retires the old material query', () => {
  const page = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
  const menu = page.match(/<nav className="office-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(menu);
  const links = [...menu.matchAll(/<a href="([^"]+)">([^<]+)<\/a>/g)].map(m => [m[1], m[2]]);
  assert.deepEqual(links, [
    ['/', '查企'], ['/xray/#/cases', '案卷'], ['/xray/#/library', '资料库'],
    ['/xray/#/me', '我的'], ['/xray/#/guide', '使用说明'],
  ]);
  assert.doesNotMatch(menu, /附带材料查询|#\/new/);
});
