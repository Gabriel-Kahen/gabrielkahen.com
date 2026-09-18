import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright-core';

// Start `python3 -m http.server 8765` in this checkout first.
const url = process.env.DRAW_TEST_URL || 'http://127.0.0.1:8765/draw/';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome-stable', headless: true });
const key = 'gabe.draw.draft.v3';
const errors = [];
await mkdir('test-results', { recursive: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  page.on('pageerror', error => errors.push(error.message));
  let fail = true;
  const submissions = [];
  await page.route('**/draw-api/drawings', async route => {
    const data = route.request().postDataJSON();
    submissions.push(data);
    if (fail) return route.abort('failed');
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: data.submission_id }) });
  });
  await page.route('**/draw-camera/frame.jpg*', route => route.fulfill({
    status: 200,
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700"/>',
  }));
  await page.route('**/draw-camera/stream.mjpg*', route => route.fulfill({
    status: 200,
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700"/>',
  }));
  await page.route('**/draw-api/status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ state: 'ready', accepting_drawings: true, drawing: false, queued: 0, capacity: 3 }),
  }));
  await page.goto(url);
  await page.waitForFunction(() => document.querySelector('#paper').dataset.locked === 'false');
  await page.waitForFunction(() => document.querySelector('#camera-status').textContent === 'Live');
  await page.waitForFunction(() => document.querySelector('#plotter-status').dataset.state === 'ready');
  assert.equal(await page.locator('#bed-camera').getAttribute('alt'), 'Live view of the Ender 3 drawing bed');
  const draft = () => page.evaluate(key => JSON.parse(localStorage.getItem(key)), key);
  const stroke = async points => {
    const box = await page.locator('#paper').boundingBox();
    await page.mouse.move(box.x + points[0][0] * box.width, box.y + points[0][1] * box.height);
    await page.mouse.down();
    for (const [x, y] of points.slice(1)) await page.mouse.move(box.x + x * box.width, box.y + y * box.height);
    await page.mouse.up();
  };
  const paperBox = await page.locator('#paper').boundingBox();
  assert(Math.abs(paperBox.width / paperBox.height - 215 / 175) < .01);
  assert.equal(await page.locator('#paper').getAttribute('viewBox'), '0 0 215 175');
  assert.equal(await page.locator('.paper-label').textContent(), '21.5 × 17.5 CM');
  const cameraBox = await page.locator('#bed-camera').boundingBox();
  assert(Math.abs(cameraBox.x - paperBox.x) > paperBox.width);
  assert(await page.locator('#submit').isDisabled());
  await stroke([[.2, .2], [.3, .3], [.4, .2]]);
  await stroke([[.6, .6]]);
  assert.equal((await draft()).strokes.length, 2);
  await page.locator('#undo').click();
  assert.equal((await draft()).strokes.length, 1);
  await page.keyboard.press('Control+z');
  assert.equal((await draft()).strokes.length, 0);
  assert.equal(await page.locator('#ink').textContent(), '48.0 in left');

  const circle = Array.from({ length: 65 }, (_, i) => {
    const angle = i / 64 * Math.PI * 2;
    return [.5 + .24 * Math.cos(angle), .42 + .24 * Math.sin(angle)];
  });
  await stroke(circle);
  await stroke([[.42, .39]]);
  await stroke([[.58, .39]]);
  await stroke(Array.from({ length: 25 }, (_, i) => {
    const angle = i / 24 * Math.PI;
    return [.5 + .12 * Math.cos(angle), .45 + .075 * Math.sin(angle)];
  }));
  const original = await draft();
  await page.reload();
  await page.waitForFunction(() => document.querySelector('#strokes').children.length === 4);
  assert.deepEqual((await draft()).strokes, original.strokes);
  await page.screenshot({ path: 'test-results/draw-desktop.png', fullPage: true });
  await page.locator('#submit').click();
  await page.waitForFunction(() => document.querySelector('#status').dataset.error === 'true');
  assert.deepEqual((await draft()).strokes, original.strokes);
  fail = false;
  await page.locator('#submit').click();
  await page.locator('#another').waitFor({ state: 'visible' });
  assert.equal(submissions[0].submission_id, submissions[1].submission_id);
  assert.deepEqual(submissions[1].strokes, original.strokes);
  assert.equal(submissions[1].version, 3);
  await page.locator('#another').click();
  assert.equal((await draft()).strokes.length, 0);

  await stroke(Array.from({ length: 10 }, (_, i) => [i % 2 ? .9 : .1, .2 + i * .04]));
  const limited = (await draft()).strokes;
  const length = limited.reduce((sum, points) => sum + points.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - points[i][0], p[1] - points[i][1]), 0), 0);
  assert(Math.abs(length - 1219.2) < 1e-6);
  assert.equal(await page.locator('#ink').textContent(), '0.0 in left');
  await page.locator('#undo').click();
  assert.equal(await page.locator('#ink').textContent(), '48.0 in left');
  await stroke([[.5, .5], [1.1, .6]]);
  const edge = (await draft()).strokes[0].at(-1);
  assert.equal(edge[0], 215);
  assert(edge[1] >= 0 && edge[1] <= 175);

  const legacy = { version: 1, submission_id: '6f59cd0a-314e-48f7-92db-f1d83e57aba8', strokes: [[[215.9, 279.4]]], submitted: false };
  await page.evaluate(({ key, legacy }) => {
    localStorage.removeItem(key);
    localStorage.setItem('gabe.draw.draft.v1', JSON.stringify(legacy));
  }, { key, legacy });
  await page.reload();
  assert.equal(await page.locator('#strokes').locator('*').count(), 0);
  assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem('gabe.draw.draft.v1'))), legacy);
  await stroke([[.1, .1], [.2, .2]]);
  assert.equal((await draft()).version, 3);
  assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem('gabe.draw.draft.v1'))), legacy);

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  mobile.on('pageerror', error => errors.push(error.message));
  await mobile.route('**/draw-camera/frame.jpg*', route => route.fulfill({
    status: 200,
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700"/>',
  }));
  await mobile.route('**/draw-camera/stream.mjpg*', route => route.fulfill({
    status: 200,
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700"/>',
  }));
  await mobile.route('**/draw-api/status', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ state: 'ready', accepting_drawings: true, drawing: false, queued: 0, capacity: 3 }),
  }));
  await mobile.goto(url);
  await mobile.waitForFunction(() => document.querySelector('#paper').dataset.locked === 'false');
  const box = await mobile.locator('#paper').boundingBox();
  const mobileCameraBox = await mobile.locator('#bed-camera').boundingBox();
  assert(Math.abs(box.width / box.height - 215 / 175) < .01);
  assert(mobileCameraBox.y > box.y + box.height);
  const cdp = await mobile.context().newCDPSession(mobile);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: box.x + 50, y: box.y + 50 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: box.x + 90, y: box.y + 100 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  const mobileDraft = await mobile.evaluate(key => JSON.parse(localStorage.getItem(key)), key);
  assert.equal(mobileDraft.strokes.length, 1);
  assert(mobileDraft.strokes[0].length >= 2);
  assert(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await mobile.screenshot({ path: 'test-results/draw-mobile.png', fullPage: true });
  assert.deepEqual(errors, []);
  console.log('Browser checks passed: strokes, dots, undo, draft restore, retry identity, submit, ink limit, paper edge, and mobile touch.');
} finally {
  await browser.close();
}
