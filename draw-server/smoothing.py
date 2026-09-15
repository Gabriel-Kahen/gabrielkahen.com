"""Small, bounded geometric smoothing in physical millimeters."""
import math

SIMPLIFY_MM = 0.06
ROUND_MM = 0.5
CURVE_STEP_MM = 0.2


def segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length2 = dx*dx + dy*dy
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length2)) if length2 else 0.
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def simplify(points):
    # Iterative RDP avoids recursion limits on dense pointer samples.
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    while pending:
        first, last = pending.pop()
        if last-first < 2:
            continue
        distance, index = max((segment_distance(points[i], points[first], points[last]), i)
                              for i in range(first+1, last))
        if distance > SIMPLIFY_MM:
            keep.add(index)
            pending.extend(((first, index), (index, last)))
    return [points[i] for i in sorted(keep)]


def smooth_stroke(points):
    """Keep dots, open endpoints and sharp corners; never leave the input hull."""
    clean = []
    for point in points:
        point = tuple(point)
        if not clean or point != clean[-1]:
            clean.append(point)
    if len(clean) < 3:
        return clean
    closed = clean[0] == clean[-1]
    points = simplify(clean)
    if closed:
        points = points[:-1]
    if len(points) < 3:
        return clean if closed else points
    corners = []
    for i, p in enumerate(points):
        a, b = points[i-1], points[(i+1) % len(points)]
        incoming, outgoing = math.dist(a, p), math.dist(p, b)
        trim = 0.
        if incoming and outgoing and (closed or 0 < i < len(points)-1):
            cosine = sum((p[k]-a[k])*(b[k]-p[k]) for k in (0, 1))/(incoming*outgoing)
            # Preserve turns of 60 degrees or more, including square corners.
            if cosine > 0.5:
                trim = min(ROUND_MM, incoming/4, outgoing/4)
        before = tuple(p[k]+(a[k]-p[k])*trim/incoming for k in (0, 1)) if trim else p
        after = tuple(p[k]+(b[k]-p[k])*trim/outgoing for k in (0, 1)) if trim else p
        corners.append((before, p, after, trim))
    result = []
    for before, p, after, trim in corners:
        result.append(before)
        if trim:
            steps = max(2, math.ceil(2*trim/CURVE_STEP_MM))
            for step in range(1, steps+1):
                t = step/steps
                result.append(tuple((1-t)**2*before[k]+2*t*(1-t)*p[k]+t*t*after[k] for k in (0, 1)))
    if closed:
        result.append(result[0])
    return result
