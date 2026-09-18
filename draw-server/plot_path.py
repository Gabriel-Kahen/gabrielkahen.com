"""Validated website vectors mapped into the currently calibrated pen square."""
import json
import math
from drawing import validate_drawing, PAGE_DIMENSIONS
from smoothing import smooth_stroke

CONTACT_Z = -3.5
LIFT_Z = 0.0
PARK = (-3.0,-10.0,LIFT_Z)
BOUNDS = ((-173.,-33.),(-180.,-40.),(CONTACT_Z,LIFT_Z))
TRAVEL_BOUNDS = ((-173.,-3.),(-180.,-10.),(LIFT_Z,LIFT_Z))
STEPS = (80,80,400)
DRAW_FEED = 720
TRAVEL_FEED = 1200
Z_FEED = 30


def counts(point):
    return tuple(round(v*s) for v,s in zip(point,STEPS))


def checked(point, *, travel=False):
    bounds = TRAVEL_BOUNDS if travel else BOUNDS
    if len(point)!=3 or not all(math.isfinite(v) and lo<=v<=hi for v,(lo,hi) in zip(point,bounds)):
        raise ValueError('Path outside calibrated bounds')
    return tuple(c/s for c,s in zip(counts(point),STEPS))


def strokes_for(job):
    source = json.loads(job['vector_json'])
    _,strokes,_,_ = validate_drawing({**source,'submission_id':job['submission_id']})
    width,height = PAGE_DIMENSIONS[source['version']]
    scale = min(140/width,140/height)
    left = -103-width*scale/2
    top = -110+height*scale/2
    result=[]
    for stroke in strokes:
        path=[]
        mapped = [(left+x*scale,top-y*scale) for x,y in stroke]
        for x,y in smooth_stroke(mapped):
            target=checked((x,y,CONTACT_Z))
            if not path or target!=path[-1]:
                path.append(target)
        result.append(path)
    return result
