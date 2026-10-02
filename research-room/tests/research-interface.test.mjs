import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync(new URL('../app/page.tsx', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../app/globals.css', import.meta.url), 'utf8');

test('research controls do not exist during the idle query state', () => {
  assert.match(page, /\{status !== 'idle' && \([\s\S]*?<div className="research-hud">/);
  assert.match(page, /const restart = \(\) => \{\s*if \(!activeQuery\) return;/);
});

test('pause freezes every animated office element and any in-flight scene transition', () => {
  for (const selector of [
    '.status-paused .window-breeze',
    '.status-paused .visitor-goose',
    '.status-paused .visitor-sprite',
    '.status-paused .evidence-paper',
    '.status-paused .xiaoqi-actor',
  ]) {
    assert.ok(styles.includes(selector), `missing paused-state rule for ${selector}`);
  }
  assert.match(styles, /animation-play-state:\s*paused/);
  assert.match(styles, /\.status-paused \.evidence-paper[\s\S]*transition-duration:\s*0s/);
});

test('the query bar exposes a keyboard-visible focus treatment', () => {
  assert.match(styles, /\.prompt-bar:focus-within\s*\{[\s\S]*?(border-color|outline|box-shadow):/);
});

test('only phase copy is live while progress uses non-live progress semantics', () => {
  assert.doesNotMatch(page, /className="phase-caption"[^>]*aria-live/);
  assert.match(page, /className="phase-copy"[^>]*aria-live="polite"[^>]*aria-atomic="true"/);
  assert.match(page, /<progress[^>]*className="progress-track"[^>]*max=\{100\}[^>]*value=\{progress\}/);
});

test('the windy office treatment is always part of the fixed panorama', () => {
  assert.match(page, /className=\{`office-stage status-\$\{status\} breeze-active`\}/);
  assert.match(page, /breezeItems\.map/);
});

test('walking follows segmented routes and cross-fades direction changes', () => {
  assert.match(page, /route\?: Point\[\]/);
  assert.match(page, /function walkStateFor/);
  assert.match(page, /walkPoses\.map/);
  assert.ok((page.match(/route: \[/g) ?? []).length >= 6, 'each walking phase needs a routed path');
  assert.match(page, /id: 'desk-exit'[^\n]*mode: 'action'[^\n]*route: \[DESK/);
  assert.match(page, /id: 'walk-archive'[^\n]*from: DESK_LEFT/);
  assert.match(page, /id: 'walk-desk'[^\n]*to: DESK_RIGHT/);
  assert.match(page, /id: 'desk-sit'[^\n]*mode: 'action'[^\n]*to: DESK[^\n]*route: \[DESK_RIGHT/);
});

test('five source markers report active and completed research locations', () => {
  for (const source of ['企业资料', '图书年报', '新闻摘要', '经营数据', '社会舆情']) {
    assert.ok(page.includes(source), `missing source marker: ${source}`);
  }
  assert.match(page, /source-markers/);
  assert.match(page, /source\.activeIds\.includes\(phase\.id\)/);
});

test('the visitor is clipped by the real doorway and uses Xiaoqi scale', () => {
  assert.match(styles, /\.visitor-goose\s*\{[\s\S]*?overflow:\s*hidden/);
  assert.match(styles, /\.visitor-sprite\s*\{[\s\S]*?width:\s*104%/);
  assert.match(styles, /\.xiaoqi-actor\s*\{[\s\S]*?width:\s*12%/);
});

test('source markers use a non-overlapping labeled rail on narrow screens', () => {
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.source-marker\s*\{[\s\S]*?min-width:\s*64px/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.source-enterprise\s*\{[^}]*top:\s*12%[^}]*left:\s*12%/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.source-data\s*\{[^}]*top:\s*80%[^}]*left:\s*12%/);
});
