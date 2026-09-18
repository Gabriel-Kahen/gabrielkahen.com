import test from 'node:test';
import assert from 'node:assert/strict';
import { DRAWING_VERSION, INK_LIMIT, PAPER, MAX_POINTS, MAX_STROKES, drawingLength, clipToPaper, spendInk, validDraft } from '../geometry.mjs';

test('length follows ordered strokes and does not count pen-up travel', () => {
  assert.equal(drawingLength([[[0, 0], [3, 4], [0, 0]], [[200, 200]]]), 10);
});

test('budget ends exactly on the submitted segment', () => {
  const part = spendInk([10, 10], [40, 50], 25);
  assert.deepEqual(part, { point: [25, 30], used: 25, exhausted: true });
  assert.equal(spendInk([0, 0], [2000, 0], INK_LIMIT).point[0], INK_LIMIT);
});

test('paper clipping stops at the first edge, retaining the segment direction', () => {
  assert.deepEqual(clipToPaper([10, 20], [-10, -20]), [0, 0]);
  assert.deepEqual(clipToPaper([165, 80], [205, 190]), [PAPER.width, 107.5]);
  assert.deepEqual(clipToPaper([10, 10], [10, 20]), [10, 20]);
  assert.deepEqual(clipToPaper([0, 0], [-10, 10]), [0, 0]);
});

test('dots and repeated samples cost no line length', () => {
  assert.equal(drawingLength([[[1, 1]], [[2, 2], [2, 2]]]), 0);
  assert.deepEqual(spendInk([1, 1], [1, 1], 10), { point: [1, 1], used: 0, exhausted: false });
});

test('zero budget adds no movement', () => {
  assert.deepEqual(spendInk([1, 1], [10, 10], 0), { point: [1, 1], used: 0, exhausted: true });
});

test('drafts reject invalid geometry and enforce cumulative limits', () => {
  const valid = strokes => validDraft({ version: DRAWING_VERSION, strokes });
  assert.ok(valid([[[0, 0], [1, 1]]]));
  assert.ok(valid([]));
  assert.ok(!valid([[]]));
  assert.ok(!valid([[[NaN, 0]]]));
  assert.ok(!valid([[[1, Infinity]]]));
  assert.ok(!valid([[[PAPER.width + 1, 1]]]));
  assert.ok(!valid([[[0, -1]]]));
  assert.ok(!valid([Array.from({ length: 8 }, (_, i) => [0, i % 2 ? PAPER.height : 0])]));
  assert.ok(!valid(Array.from({ length: MAX_STROKES + 1 }, () => [[0, 0]])));
  assert.ok(!valid([Array.from({ length: MAX_POINTS + 1 }, () => [0, 0])]));
});


test('calibrated dimensions and versioning keep older drafts separate', () => {
  assert.deepEqual(PAPER, { width: 175, height: 175 });
  assert.ok(validDraft({ version: 3, strokes: [[[0, 0], [175, 175]]] }));
  assert.ok(!validDraft({ version: 2, strokes: [[[0, 0], [200, 200]]] }));
  assert.ok(validDraft({ version: 2, strokes: [[[0, 0], [200, 200]]] }, 2));
  const legacy = { version: 1, strokes: [[[215.9, 279.4]]] };
  assert.ok(!validDraft(legacy));
  assert.ok(validDraft(legacy, 1));
  assert.ok(!validDraft({ ...legacy, version: 4 }, 4));
});
