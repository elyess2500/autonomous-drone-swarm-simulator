"""Focused Step 4 safety probe; no production analytics changes.

python benchmarks/step4.py --label phase1 --output /path/to/results.json
Point contacts use synchronous swept centers; shared docking-zone contacts are
exempt. Proximity episodes use the existing visual near-miss threshold, separately.
"""
import argparse
import itertools
import json
import math
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import config
from benchmarks.tranche1 import run
from core.mission import Mission
from core.intelligence import ReservationTable


def closest(a0, a1, b0, b1):
    r = (a0[0]-b0[0], a0[1]-b0[1])
    v = (a1[0]-a0[0]-b1[0]+b0[0], a1[1]-a0[1]-b1[1]+b0[1])
    vv = v[0]*v[0]+v[1]*v[1]
    t = min(1.0, max(0.0, -(r[0]*v[0]+r[1]*v[1])/vv)) if vv else 0.0
    pa = tuple(x+(y-x)*t for x, y in zip(a0, a1))
    pb = tuple(x+(y-x)*t for x, y in zip(b0, b1))
    return math.dist(pa, pb), pa, pb


def docking_exempt(a0, a1, b0, b1, pa, pb, base):
    points = [pa, pb]
    velocity_delta = tuple(y-x-v+u for x,y,u,v in zip(a0,a1,b0,b1))
    if velocity_delta == (0.0, 0.0):
        points.extend((a0,a1,b0,b1))
    return all(math.dist(p,base) <= config.BASE_DOCKING_RADIUS_PX for p in points)


def field_contact(a0, a1, b0, b1, base):
    """Independent swept-center probe, including the whole tolerance interval."""
    distance, _, _ = closest(a0,a1,b0,b1)
    if distance > 1e-7:
        return False
    delta = [a-b for a,b in zip(a0,b0)]
    velocity = [v-u-y+x for u,v,x,y in zip(a0,a1,b0,b1)]
    speed_sq = sum(v*v for v in velocity)
    interval = [0.0,1.0]
    if speed_sq:
        at = -sum(r*v for r,v in zip(delta,velocity))/speed_sq
        residual = sum((r+at*v)**2 for r,v in zip(delta,velocity))
        margin = math.sqrt(max(0.0,1e-14-residual)/speed_sq)
        interval = [max(0.0,at-margin),min(1.0,at+margin)]
    for start,end in ((a0,a1),(b0,b1)):
        for at in interval:
            p = tuple(x+(y-x)*at for x,y in zip(start,end))
            if math.dist(p,base) > config.BASE_DOCKING_RADIUS_PX:
                return True
    return False


def measure(seed, ticks):
    original = Mission.update
    latency = []
    totals = dict(point_contact_pair_ticks=0, proximity_episodes=0,
                  majority_connected_ticks=0, full_collapse_ticks=0,
                  stranded_drone_ticks=0)
    active_near = set()
    last_swarm = None
    component_samples = {}
    originals = {}
    for method in ('rebuild', 'try_move'):
        if not hasattr(ReservationTable, method):
            continue
        originals[method] = getattr(ReservationTable, method)
        samples = component_samples[method] = []

        def measured(*args, _original=originals[method], _samples=samples, **kwargs):
            started = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                _samples.append((time.perf_counter()-started)*1000)

        setattr(ReservationTable, method, measured)

    def observed(mission):
        nonlocal active_near, last_swarm
        drones = mission.swarm.drones
        before = {d.drone_id: (d.px, d.py) for d in drones}
        started = time.perf_counter()
        original(mission)
        latency.append((time.perf_counter()-started)*1000)
        connected = sum(d.comm.is_connected for d in drones)
        totals['majority_connected_ticks'] += connected > len(drones)//2
        totals['full_collapse_ticks'] += connected == 0
        totals['stranded_drone_ticks'] += sum(d.state == 'stranded' for d in drones)
        near = set()
        for a, b in itertools.combinations(drones, 2):
            totals['point_contact_pair_ticks'] += field_contact(
                before[a.drone_id], (a.px,a.py), before[b.drone_id], (b.px,b.py), a.base_px)
            distance, pa, pb = closest(before[a.drone_id], (a.px,a.py),
                                       before[b.drone_id], (b.px,b.py))
            shared = docking_exempt(before[a.drone_id], (a.px,a.py),
                                    before[b.drone_id], (b.px,b.py), pa, pb, a.base_px)
            if shared:
                continue
            if distance <= config.CELL_SIZE*.85:
                near.add(tuple(sorted((a.drone_id,b.drone_id))))
        totals['proximity_episodes'] += len(near-active_near)
        active_near = near
        last_swarm = mission.swarm

    Mission.update = observed
    try:
        result = run(seed, ticks)
        result.update(totals)
        result.update(majority_connectivity=totals['majority_connected_ticks']/ticks,
                      mean_ms=float(np.mean(latency)), p50_ms=float(np.percentile(latency,50)),
                      p95_ms=float(np.percentile(latency,95)),
                      p99_ms=float(np.percentile(latency,99)), max_ms=max(latency))
        result['execution_counters'] = dict(getattr(last_swarm.reservations, 'counters', {}))
        result['component_timing'] = {
            name: dict(calls=len(samples), mean_ms=float(np.mean(samples)),
                       p50_ms=float(np.percentile(samples,50)),
                       p95_ms=float(np.percentile(samples,95)),
                       p99_ms=float(np.percentile(samples,99)), max_ms=max(samples),
                       total_ms=sum(samples), per_tick_ms=sum(samples)/ticks)
            for name,samples in component_samples.items() if samples}
        return result
    finally:
        Mission.update = original
        for method, implementation in originals.items():
            setattr(ReservationTable, method, implementation)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seeds', type=int, nargs='+', default=[2026,2027,2031])
    parser.add_argument('--ticks', type=int, default=3600)
    args = parser.parse_args()
    config.FAILURE_PROB_PER_FRAME = 0.0
    config.QUICK_DEMO_MODE = False
    config.AUTONOMOUS_OFFLINE_MODE = True
    with tempfile.TemporaryDirectory(prefix='adss-step4-') as runtime:
        config.METRICS_LOG_DIR = runtime
        results = []
        for seed in args.seeds:
            results.append(measure(seed,args.ticks))
            print(f'completed seed={seed} ticks={args.ticks}', flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.with_suffix('.partial.json').write_text(
                json.dumps(dict(label=args.label,results=results),indent=2)+'\n',encoding='utf-8')
    payload = dict(label=args.label, methodology='step4-contact-interval-v2-components',
                   failure_probability=0, results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2))
