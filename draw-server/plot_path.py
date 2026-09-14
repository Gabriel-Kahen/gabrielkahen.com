"""Validated website vectors mapped into the currently calibrated pen square."""
import json
import math
from drawing import validate_drawing, PAGE_DIMENSIONS

CONTACT_Z = -2.5
LIFT_Z = 0.0
PARK = (55.0,50.0,0.0)
BOUNDS = ((-85.,55.),(-80.,60.),(-2.5,0.))
STEPS = (80,80,400)


def counts(point):
    return tuple(round(v*s) for v,s in zip(point,STEPS))


def checked(point):
    if len(point)!=3 or not all(math.isfinite(v) and lo<=v<=hi for v,(lo,hi) in zip(point,BOUNDS)):
        raise ValueError('Path outside calibrated bounds')
    return tuple(c/s for c,s in zip(counts(point),STEPS))


def strokes_for(job):
    source = json.loads(job['vector_json'])
    _,strokes,_,_ = validate_drawing({**source,'submission_id':job['submission_id']})
    width,height = PAGE_DIMENSIONS[source['version']]
    scale = min(140/width,140/height)
    left = -15-width*scale/2
    top = -10+height*scale/2
    result=[]
    for stroke in strokes:
        path=[]
        for x,y in stroke:
            target=checked((left+x*scale,top-y*scale,CONTACT_Z))
            if not path or target!=path[-1]:
                path.append(target)
        result.append(path)
    return result
