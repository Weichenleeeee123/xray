import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import { runInNewContext } from 'node:vm';
import { imageUpgradePlan, officeImages, previewSources, upgradeImages } from '../app/progressive-images.ts';

// Execute the production hook and decoder, with deterministic browser APIs and
// only React's state/ref/effect scheduling supplied by this small Node harness.
const hookSource = stripTypeScriptTypes(readFileSync(
  new URL('../app/use-progressive-images.ts', import.meta.url), 'utf8',
)).replace(/^import .*;\r?\n/gm, '').replace('export function useProgressiveImages', 'function useProgressiveImages');
const tick = () => new Promise(resolve => setImmediate(resolve));
const full = Object.fromEntries(officeImages.map(asset => [asset.id, asset.full]));

function mountHook(t, { hidden = false } = {}) {
  const slots = [], effects = [], timers = new Map(), images = [];
  let cursor = 0, now = 0, nextTimer = 0, mounted = true;
  let result, pendingEffects, phase = 'idle';
  const document = Object.assign(new EventTarget(), { hidden, readyState: 'complete' });
  const window = new EventTarget();
  const setTimeout = (callback, delay = 0) => {
    const id = ++nextTimer;
    timers.set(id, { callback, at: now + delay });
    return id;
  };
  const clearTimeout = id => timers.delete(id);
  window.requestIdleCallback = callback => setTimeout(callback, 1);
  window.cancelIdleCallback = clearTimeout;
  const hook = runInNewContext(`${hookSource}\nuseProgressiveImages;`, {
    document, window, AbortController, setTimeout, clearTimeout,
    requestAnimationFrame: callback => setTimeout(callback, 16),
    cancelAnimationFrame: clearTimeout,
    imageUpgradePlan, previewSources, upgradeImages,
    Image: class {
      cancelled = false;
      set src(url) { this.url = url; images.push(this); }
      removeAttribute(name) { if (name === 'src') this.cancelled = true; }
      decode() {
        return new Promise((resolve, reject) => { this.resolve = resolve; this.reject = reject; });
      }
    },
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => {
        assert.ok(mounted, 'the unmounted hook must not update state');
        slots[index] = typeof value === 'function' ? value(slots[index]) : value;
        render();
      }];
    },
    useRef(initial) {
      const index = cursor++;
      return slots[index] ??= { current: initial };
    },
    useEffect(setup, deps) {
      const index = cursor++;
      const previous = effects[index];
      if (!previous || deps.some((value, i) => !Object.is(value, previous.deps[i]))) {
        pendingEffects.push(() => {
          previous?.cleanup?.();
          effects[index] = { deps, cleanup: setup() };
        });
      }
    },
  });
  function render(nextPhase = phase) {
    phase = nextPhase;
    cursor = 0;
    pendingEffects = [];
    result = hook(true, phase);
    for (const apply of pendingEffects) apply();
  }
  function unmount() {
    if (!mounted) return;
    mounted = false;
    for (const effect of effects) effect?.cleanup?.();
  }
  t.after(unmount);
  render();
  return {
    images, render, unmount,
    get sources() { return result; },
    get pendingTimers() { return timers.size; },
    setHidden(value) {
      document.hidden = value;
      document.dispatchEvent(new Event('visibilitychange'));
    },
    advance(milliseconds = 3000) {
      const end = now + milliseconds;
      while (true) {
        const entry = [...timers].filter(([, timer]) => timer.at <= end)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!entry) break;
        const [id, timer] = entry;
        timers.delete(id);
        now = timer.at;
        timer.callback();
      }
      now = end;
    },
  };
}

test('hiding the page cancels an in-flight image and prevents the next download', async t => {
  const h = mountHook(t);
  h.advance();
  assert.equal(h.images[0].url, full.background);
  h.setHidden(true);
  assert.equal(h.images[0].cancelled, true);
  h.images[0].resolve();
  await tick();
  h.advance();
  assert.equal(h.images.length, 1);
  assert.equal(h.sources.background, previewSources.background);
});

test('becoming visible starts a fresh queue before the cancelled queue settles', async t => {
  const h = mountHook(t);
  h.advance();
  h.setHidden(true);
  h.setHidden(false);
  // Deliberately keep the old rejection/finally microtasks pending during restart.
  h.advance();
  assert.deepEqual(h.images.map(image => image.url), [full.background, full.background]);
  assert.equal(h.images[1].cancelled, false);
  await tick();
  h.images[0].resolve();
  await tick();
  assert.equal(h.sources.background, previewSources.background);
  assert.equal(h.images.length, 2);
  h.images[1].resolve();
  await tick();
  assert.equal(h.sources.background, full.background);
  assert.equal(h.images[2].url, full.action);
});

test('visibility recovery skips completed images and retries only unfinished images', async t => {
  const h = mountHook(t);
  h.advance();
  h.images[0].resolve();
  await tick();
  assert.equal(h.images[1].url, full.action);
  h.setHidden(true);
  await tick();
  h.setHidden(false);
  h.advance();
  assert.deepEqual(h.images.map(image => image.url), [full.background, full.action, full.action]);
  assert.equal(h.sources.background, full.background);
  assert.equal(h.sources.action, previewSources.action);
});

test('phase changes cancel old work and research visibility changes never download artwork', async t => {
  const h = mountHook(t);
  h.advance();
  h.images[0].resolve();
  await tick();
  h.render('research');
  assert.equal(h.images[1].cancelled, true);
  h.setHidden(true);
  h.setHidden(false);
  h.advance();
  h.images[1].resolve();
  await tick();
  assert.equal(h.images.length, 2);
  assert.equal(h.sources.action, previewSources.action);
  h.render('complete');
  h.advance();
  assert.equal(h.images[2].url, full.action);
  for (let i = 2; i < officeImages.length + 1; i++) {
    h.images[i].resolve();
    await tick();
  }
  assert.deepEqual(h.images.map(image => image.url), [full.background, full.action,
    ...officeImages.slice(1).map(asset => asset.full)]);
});

test('an initially hidden page waits for visibility before scheduling upgrades', t => {
  const h = mountHook(t, { hidden: true });
  h.advance();
  assert.equal(h.images.length, 0);
  h.setHidden(false);
  h.advance();
  assert.equal(h.images[0].url, full.background);
});

test('unmount cancels scheduled work and removes the visibility listener', t => {
  const h = mountHook(t);
  h.unmount();
  h.setHidden(true);
  h.setHidden(false);
  h.advance();
  assert.equal(h.images.length, 0);
  assert.equal(h.pendingTimers, 0);
});

test('unmount during decoding cancels the request without a stale state update', async t => {
  const h = mountHook(t);
  h.advance();
  h.unmount();
  assert.equal(h.images[0].cancelled, true);
  h.images[0].resolve();
  await tick();
  assert.equal(h.images.length, 1);
  assert.equal(h.pendingTimers, 0);
});
