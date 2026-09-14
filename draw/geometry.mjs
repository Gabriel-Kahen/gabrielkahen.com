export const DRAWING_VERSION = 2;
export const PAPER = Object.freeze({ width: 200, height: 200 });
const LEGACY_PAPER = Object.freeze({ width: 215.9, height: 279.4 });
export const INK_LIMIT = 1219.2;
export const MAX_STROKES = 200;
export const MAX_POINTS = 20000;
export const PEN_WIDTH = 0.4;

export const distance = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

export function strokeLength(stroke) {
  return stroke.reduce((length, point, i) => length + (i ? distance(stroke[i - 1], point) : 0), 0);
}

export const drawingLength = strokes => strokes.reduce((sum, stroke) => sum + strokeLength(stroke), 0);

// Clip a segment at the first paper edge it meets, without sliding along edges.
export function clipToPaper(from, to) {
  let t = 1;
  for (let axis = 0; axis < 2; axis++) {
    const bound = axis === 0 ? PAPER.width : PAPER.height;
    const delta = to[axis] - from[axis];
    if (to[axis] < 0) t = Math.min(t, -from[axis] / delta);
    if (to[axis] > bound) t = Math.min(t, (bound - from[axis]) / delta);
  }
  return [
    Math.max(0, Math.min(PAPER.width, from[0] + (to[0] - from[0]) * t)),
    Math.max(0, Math.min(PAPER.height, from[1] + (to[1] - from[1]) * t)),
  ];
}

// Each output segment is part of the original pen path; no smoothing or raster scan.
export function spendInk(from, to, remaining) {
  const length = distance(from, to);
  if (!length || remaining <= 0) return { point: from, used: 0, exhausted: remaining <= 0 };
  const used = Math.min(length, remaining);
  const ratio = used / length;
  return {
    point: ratio === 1 ? to : [from[0] + (to[0] - from[0]) * ratio, from[1] + (to[1] - from[1]) * ratio],
    used,
    exhausted: used >= remaining,
  };
}

export function validDraft(value, version = DRAWING_VERSION) {
  const bounds = version === 1 ? LEGACY_PAPER : PAPER;
  if (![1, DRAWING_VERSION].includes(version) || !value || value.version !== version || !Array.isArray(value.strokes) || value.strokes.length > MAX_STROKES) return false;
  let points = 0;
  for (const stroke of value.strokes) {
    if (!Array.isArray(stroke) || !stroke.length || (points += stroke.length) > MAX_POINTS) return false;
    for (const p of stroke) {
      if (!Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite) || p[0] < 0 || p[0] > bounds.width || p[1] < 0 || p[1] > bounds.height) return false;
    }
  }
  return drawingLength(value.strokes) <= INK_LIMIT + 1e-7;
}
