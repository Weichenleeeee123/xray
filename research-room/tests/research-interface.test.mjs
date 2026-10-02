import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { phases, motionAt, doorAt, DURATION } from '../app/office-motion.ts';

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

test('the goose clears both desk corners with body-width clearance', () => {
  for (const p of phases.filter(p => p.mode === 'walk')) {
    for (let t=p.start; t<p.end; t+=16) {
      const {x,y}=motionAt(p,t).position;
      const inDesk = x>27.5 && x<72.5 && y>71 && y<95;
      assert.ok(!inDesk, `${p.id} intersects desk at ${x},${y}`);
    }
  }
});

test('action phases keep feet stationary and phase boundaries never teleport', () => {
  for (const [i,p] of phases.entries()) {
    if(p.mode==='action') {
      assert.deepEqual(motionAt(p,p.start).position,motionAt(p,p.end).position);
      assert.equal(motionAt(p,p.start+300).frame,0);
    }
    if(i) {
      const a=motionAt(phases[i-1],p.start).position,b=motionAt(p,p.start).position;
      assert.ok(Math.hypot(a.x-b.x,a.y-b.y)<.001);
    }
  }
});

test('footsteps advance with traveled distance, not with idle time', () => {
  const walk={...phases[2],start:0,end:1000,route:[{x:0,y:0},{x:10,y:0}]};
  const halfway=motionAt(walk,500);
  assert.equal(halfway.position.x,5);
  assert.equal(halfway.facing,'right');
  assert.equal(halfway.frame,3);
  assert.equal(motionAt({...walk,route:undefined,to:{x:5,y:0}},500).frame,0);
});

test('door stays open for the conversation and closes before returning', () => {
  assert.equal(doorAt(0),0);
  assert.equal(doorAt(25500),1);
  assert.equal(doorAt(DURATION),0);
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
