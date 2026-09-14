import { PAPER, PEN_WIDTH, INK_LIMIT, MAX_STROKES, MAX_POINTS, distance, drawingLength, clipToPaper, spendInk, validDraft } from './geometry.mjs?v=48';

const $ = id => document.getElementById(id);
const paper = $('paper');
const layer = $('strokes');
const DRAFT_KEY = 'gabe.draw.draft.v1';
const NS = 'http://www.w3.org/2000/svg';
let strokes = [];
let submissionId = null;
let totalLength = 0;
let pointCount = 0;
let activePointer = null;
let activeShape = null;
let sending = false;
let submitted = false;

function status(message, error = false) {
  $('status').textContent = message;
  $('status').dataset.error = String(error);
}

function updateControls() {
  $('undo').disabled = sending || submitted || !strokes.length;
  $('submit').disabled = sending || submitted || !strokes.length || activePointer !== null;
  $('submit').hidden = submitted;
  $('another').hidden = !submitted;
  $('submit').textContent = sending ? 'Submitting…' : 'Submit drawing ↗';
  $('ink').textContent = `${(Math.max(0, INK_LIMIT - totalLength) / 25.4).toFixed(1)} in left`;
  paper.dataset.locked = String(sending || submitted);
}

function saveDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ version: 1, submission_id: submissionId, strokes, submitted }));
  } catch { /* Drawing still works when browser storage is unavailable. */ }
}

function drawStroke(stroke) {
  const dot = stroke.length === 1;
  const shape = document.createElementNS(NS, dot ? 'circle' : 'polyline');
  if (dot) {
    shape.setAttribute('cx', stroke[0][0]);
    shape.setAttribute('cy', stroke[0][1]);
    shape.setAttribute('r', PEN_WIDTH / 2);
    shape.setAttribute('fill', '#000');
    shape.setAttribute('stroke', 'none');
  } else shape.setAttribute('points', stroke.map(p => p.join(',')).join(' '));
  layer.append(shape);
  return shape;
}

function newId() { return crypto.randomUUID(); }

function position(event) {
  const rect = paper.getBoundingClientRect();
  return [(event.clientX - rect.left) / rect.width * PAPER.width, (event.clientY - rect.top) / rect.height * PAPER.height];
}

function inside(point) {
  return point[0] >= 0 && point[0] <= PAPER.width && point[1] >= 0 && point[1] <= PAPER.height;
}

function endStroke() {
  if (activePointer === null) return;
  const pointer = activePointer;
  activePointer = null;
  activeShape = null;
  if (paper.hasPointerCapture(pointer)) paper.releasePointerCapture(pointer);
  // Recompute from the exact submitted vertices to avoid accumulated rounding drift.
  totalLength = drawingLength(strokes);
  updateControls();
  saveDraft();
}

function appendPoint(event) {
  if (event.pointerId !== activePointer) return;
  const stroke = strokes.at(-1);
  const from = stroke.at(-1);
  const raw = position(event);
  const endpoint = clipToPaper(from, raw);
  if (distance(from, endpoint) > 0) {
    if (pointCount >= MAX_POINTS) {
      status('This drawing has reached its detail limit. You can undo a stroke or submit.');
      endStroke();
      return;
    }
    const segment = spendInk(from, endpoint, INK_LIMIT - totalLength);
    if (segment.used > 0) {
      stroke.push(segment.point);
      pointCount++;
      totalLength += segment.used;
      if (stroke.length === 2) {
        activeShape.remove();
        activeShape = drawStroke(stroke);
      } else {
        const vertex = paper.createSVGPoint();
        [vertex.x, vertex.y] = segment.point;
        activeShape.points.appendItem(vertex);
      }
    }
    if (segment.exhausted) {
      status('All 48 inches used. Undo a stroke to keep drawing, or submit.');
      endStroke();
      return;
    }
    updateControls();
  }
  if (!inside(raw)) endStroke();
}

paper.addEventListener('pointerdown', event => {
  if (sending || submitted || activePointer !== null || !event.isPrimary || event.button !== 0) return;
  event.preventDefault();
  if (INK_LIMIT - totalLength < 1e-7) return status('All 48 inches used. Undo a stroke to keep drawing, or submit.');
  if (strokes.length >= MAX_STROKES) return status('200 strokes is the limit. You can undo a stroke or submit.');
  if (pointCount >= MAX_POINTS) return status('This drawing has reached its detail limit. You can undo a stroke or submit.');
  const point = position(event);
  if (!inside(point)) return;
  submissionId = newId();
  strokes.push([point]);
  pointCount++;
  activePointer = event.pointerId;
  activeShape = drawStroke(strokes.at(-1));
  paper.setPointerCapture(event.pointerId);
  status('Each line is saved in the order you draw it.');
  updateControls();
});

paper.addEventListener('pointermove', event => {
  if (event.pointerId !== activePointer) return;
  event.preventDefault();
  for (const sample of event.getCoalescedEvents?.() || []) appendPoint(sample);
  appendPoint(event);
});
paper.addEventListener('pointerup', event => {
  if (event.pointerId !== activePointer) return;
  appendPoint(event);
  endStroke();
});
paper.addEventListener('pointercancel', event => { if (event.pointerId === activePointer) endStroke(); });
paper.addEventListener('lostpointercapture', event => { if (event.pointerId === activePointer) endStroke(); });
window.addEventListener('blur', endStroke);
document.addEventListener('visibilitychange', () => { if (document.hidden) endStroke(); });

function undo() {
  if (sending || submitted || !strokes.length) return;
  endStroke();
  pointCount -= strokes.pop().length;
  layer.lastElementChild.remove();
  totalLength = drawingLength(strokes);
  submissionId = newId();
  status('');
  updateControls();
  saveDraft();
}
$('undo').addEventListener('click', undo);
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    undo();
  }
});

$('submit').addEventListener('click', async () => {
  if (sending || submitted || !strokes.length || activePointer !== null) return;
  sending = true;
  submissionId ||= newId();
  saveDraft();
  updateControls();
  status('Sending your drawing…');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(window.DRAW_CONFIG.apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: 1, submission_id: submissionId, strokes }),
      signal: controller.signal,
      credentials: 'omit',
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(response.status === 429
        ? 'A few too many drawings at once. Please wait a minute and try again.'
        : typeof data?.error === 'string' ? data.error.slice(0, 240) : 'The server could not save your drawing. Please try again.');
    }
    if (!data?.id && !data?.submission_id) throw new Error('The server did not confirm the save. Please try again.');
    submitted = true;
    status('Drawing submitted. Thanks for leaving a little ink.');
    saveDraft();
  } catch (error) {
    const message = error.name === 'AbortError'
      ? 'The connection timed out. Your drawing is still here; try submitting again.'
      : error instanceof TypeError
        ? 'Could not reach the drawing server. Your drawing is still here; please try again.'
        : error.message;
    status(message, true);
  } finally {
    clearTimeout(timeout);
    sending = false;
    updateControls();
    if (submitted) $('another').focus();
  }
});

$('another').addEventListener('click', () => {
  strokes = [];
  submissionId = null;
  totalLength = 0;
  pointCount = 0;
  submitted = false;
  layer.replaceChildren();
  status('A fresh sheet. Draw with your mouse, finger, or pen.');
  updateControls();
  saveDraft();
});

try {
  const draft = JSON.parse(localStorage.getItem(DRAFT_KEY));
  if (validDraft(draft)) {
    strokes = draft.strokes;
    submissionId = typeof draft.submission_id === 'string' && /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(draft.submission_id) ? draft.submission_id : null;
    submitted = draft.submitted === true && strokes.length > 0;
    totalLength = drawingLength(strokes);
    pointCount = strokes.reduce((count, stroke) => count + stroke.length, 0);
    strokes.forEach(drawStroke);
    if (strokes.length) status(submitted ? 'Your last drawing was submitted. Start another whenever you like.' : 'Your drawing is still here. Pick up where you left off.');
  }
} catch { /* Ignore unavailable storage or an invalid saved draft. */ }
updateControls();
