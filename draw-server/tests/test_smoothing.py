import math
import pytest
from smoothing import smooth_stroke, segment_distance


def length(points):
    return sum(math.dist(a,b) for a,b in zip(points,points[1:]))


def test_dots_lines_and_endpoints():
    assert smooth_stroke([(1,2)]*4)==[(1,2)]
    assert smooth_stroke([(0,0),(1,0),(2,0)])==[(0,0),(2,0)]
    points=[(0,0),(5,0),(10,2),(15,5)]
    out=smooth_stroke(points)
    assert out[0]==points[0] and out[-1]==points[-1]
    assert length(out)<=length(points)


def test_square_and_reversal_keep_corners():
    square=[(0,0),(10,0),(10,10),(0,10),(0,0)]
    assert smooth_stroke(square)==square
    assert smooth_stroke([(0,0),(10,0),(0,0)])==[(0,0),(10,0),(0,0)]


def test_dense_pointer_jitter_is_removed():
    points=[(i/100, 0.025*math.sin(i)) for i in range(2001)]
    out=smooth_stroke(points)
    assert len(out)==2
    assert out[0]==points[0] and out[-1]==points[-1]
    assert length(out)<length(points)*0.7


def test_closed_circle_has_no_open_seam_and_small_error():
    points=[(30*math.cos(i*math.tau/96),30*math.sin(i*math.tau/96)) for i in range(96)]
    points.append(points[0])
    out=smooth_stroke(points)
    assert out[0]==out[-1]
    assert max(abs(math.hypot(*p)-30) for p in out)<0.04
    assert length(out)<=length(points)
    # Curve rounding improves direction continuity at original segment joins.
    def max_turn(path):
        turns=[]
        for a,b,c in zip(path,path[1:],path[2:]):
            u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
            turns.append(abs(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])))
        return max(turns)
    assert max_turn(out)<max_turn(points)*0.3


@pytest.mark.parametrize('points',[
    [(0,0),(10,0),(20,3),(30,10)],
    [(0,0),(1,.2),(2,0),(3,.2),(4,0)],
    [(0,0),(0,10),(1,20),(10,30)],
])
def test_small_deviation_no_overshoot_or_length_increase(points):
    out=smooth_stroke(points)
    for p in out:
        assert all(min(q[k] for q in points)<=p[k]<=max(q[k] for q in points) for k in (0,1))
        assert min(segment_distance(p,a,b) for a,b in zip(points,points[1:]))<=0.31
    assert length(out)<=length(points)+1e-9
