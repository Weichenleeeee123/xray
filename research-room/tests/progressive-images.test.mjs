import test from 'node:test';
import assert from 'node:assert/strict';
import { upgradeImages, imageUpgradePlan, officeImages, previewSources } from '../app/progressive-images.ts';

const assets = [{ id: 'background', full: '/background.webp' }, { id: 'actor', full: '/actor.webp' }];
const tick = () => new Promise((resolve) => setImmediate(resolve));

test('the idle room upgrades only the artwork currently visible', () => {
  assert.deepEqual(imageUpgradePlan('idle', previewSources).map(a => a.id), ['background', 'action', 'motion']);
});

test('research requests have priority over optional high resolution downloads', () => {
  assert.deepEqual(imageUpgradePlan('research', previewSources), []);
  assert.deepEqual(imageUpgradePlan('complete', previewSources).map(a => a.id), officeImages.map(a => a.id));
});

test('resuming upgrades never downloads an already upgraded image again', () => {
  const sources = { ...previewSources, background: officeImages[0].full };
  assert.deepEqual(imageUpgradePlan('idle', sources).map(a => a.id), ['action', 'motion']);
  assert.equal(imageUpgradePlan('complete', sources).some(a => a.id === 'background'), false);
});

test('keeps the preview until decoded, then upgrades images one at a time', async () => {
  const started = [], applied = [], pending = [];
  const work = upgradeImages(assets, (url) => {
    started.push(url);
    return new Promise((resolve) => pending.push(resolve));
  }, (asset) => applied.push(asset.id), new AbortController().signal);
  assert.deepEqual(started, ['/background.webp']);
  assert.deepEqual(applied, []);
  pending[0]();
  await tick();
  assert.deepEqual(applied, ['background']);
  assert.deepEqual(started, ['/background.webp', '/actor.webp']);
  pending[1]();
  await work;
  assert.deepEqual(applied, ['background', 'actor']);
});

test('a failed high resolution image keeps its preview and does not block the next image', async () => {
  const applied = [];
  await upgradeImages(assets, async (url) => {
    if (url === '/background.webp') throw new Error('decode failed');
  }, (asset) => applied.push(asset.id), new AbortController().signal);
  assert.deepEqual(applied, ['actor']);
});

test('unmount during decoding prevents both a stale update and the next download', async () => {
  const controller = new AbortController(), started = [], applied = [];
  let finish;
  const work = upgradeImages(assets, (url) => {
    started.push(url);
    return new Promise((resolve) => { finish = resolve; });
  }, (asset) => applied.push(asset.id), controller.signal);
  controller.abort();
  finish();
  await work;
  assert.deepEqual(applied, []);
  assert.deepEqual(started, ['/background.webp']);
});

test('an already cancelled queue does not download anything', async () => {
  const controller = new AbortController();
  controller.abort();
  await upgradeImages(assets, async () => assert.fail('unexpected download'),
    () => assert.fail('unexpected update'), controller.signal);
});
