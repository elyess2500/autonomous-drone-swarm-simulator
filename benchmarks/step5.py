"""Step 5 communication probe layered on the unchanged Step 4 safety harness.

Sensor event counts use an independent range graph at observation time, not
LOST_COMM or cached CommNode flags. Timing includes sensor instrumentation;
post-update graph/event accounting and Step 4 safety probes are excluded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import config
from benchmarks.step4 import measure as step4_measure
from core.drone import Drone
from core.mission import Mission


def physical_ids(drones):
    eligible = [d for d in drones if d.state not in ('failed','stranded')]
    bx,by = ((config.BASE_COL+.5)*config.CELL_SIZE,(config.BASE_ROW+.5)*config.CELL_SIZE)
    radius2 = config.DRONE_COMM_RANGE**2
    reached = {d.drone_id for d in eligible if (d.px-bx)**2+(d.py-by)**2 <= radius2}
    pending = list(eligible)
    while True:
        expanded = {d.drone_id for d in pending if any(p.drone_id in reached and
                    (d.px-p.px)**2+(d.py-p.py)**2 <= radius2 for p in eligible)}
        if expanded <= reached:
            return reached
        reached |= expanded


def measure(seed,ticks):
    names = ('_scan_online','_scan_offline','_sync_offline_discoveries')
    originals = {name:getattr(Drone,name) for name in names}
    mission_update = Mission.update
    counts = dict(disconnected_sensor_events=0, disconnected_new_local_cells=0,
                  disconnected_survivor_observations=0, leaked_global_cells=0,
                  leaked_global_survivors=0, buffered_cell_additions=0,
                  buffered_survivor_additions=0, uploaded_new_cells=0,
                  uploaded_new_survivors=0, sync_attempts_with_pending_data=0,
                  duplicate_cell_uploads=0, duplicate_survivor_uploads=0,
                  partition_events=0,reconnect_events=0,lost_comm_transitions=0,
                  max_offline_ticks=0)
    drones = []; depth = set(); latency = []; connected_counts=[]
    prior = {}; durations = {}; last = None

    def instrument(name):
        original = originals[name]
        def observed(d,*args,**kwargs):
            if d.drone_id in depth:
                return original(d,*args,**kwargs)
            depth.add(d.drone_id)
            try:
                connected = d.drone_id in physical_ids(drones or [d])
                pending = set(d.offline_known_cells); survivors = set(d.offline_survivor_found)
                found_before = set(d.game_map.mission_found)
                if name == '_sync_offline_discoveries':
                    fog_before = {p for p in pending if d.game_map.fog[p[1],p[0]]}
                    result = original(d,*args,**kwargs)
                    if pending or survivors:
                        counts['sync_attempts_with_pending_data'] += 1
                        if connected:
                            counts['duplicate_cell_uploads'] += len(fog_before)
                            counts['duplicate_survivor_uploads'] += len(survivors & found_before)
                            counts['uploaded_new_cells'] += result[0]
                            counts['uploaded_new_survivors'] += result[1]
                        else:
                            counts['leaked_global_cells'] += result[0]
                            counts['leaked_global_survivors'] += result[1]
                    return result
                col,row = args[:2]
                cells = d.game_map.cells_in_radius(col,row,config.DRONE_SENSOR_RADIUS)
                unseen_global = {p for p in cells if not d.game_map.fog[p[1],p[0]]}
                unseen_local = cells-d.map_known
                observations = set(d.game_map.detect_mission_near(col,row,exclude_found=False))-set(d.mission_found)
                result = original(d,*args,**kwargs)
                if not connected:
                    counts['disconnected_sensor_events'] += 1
                    counts['disconnected_new_local_cells'] += len(unseen_local)
                    counts['disconnected_survivor_observations'] += len(observations)
                    counts['leaked_global_cells'] += sum(bool(d.game_map.fog[r,c]) for c,r in unseen_global)
                    counts['leaked_global_survivors'] += len(d.game_map.mission_found-found_before)
                counts['buffered_cell_additions'] += len(d.offline_known_cells-pending)
                counts['buffered_survivor_additions'] += len(d.offline_survivor_found-survivors)
                return result
            finally:
                depth.remove(d.drone_id)
        return observed

    def observed_update(mission):
        nonlocal drones,last,prior
        drones = mission.swarm.drones
        if not prior:
            reached = physical_ids(drones)
            prior = {d.drone_id:d.drone_id in reached for d in drones}
        states = {d.drone_id:d.state for d in drones}
        t = time.perf_counter(); mission_update(mission)
        latency.append((time.perf_counter()-t)*1000)
        reached = physical_ids(drones); connected_counts.append(len(reached))
        for d in drones:
            linked = d.drone_id in reached
            counts['partition_events'] += prior[d.drone_id] and not linked
            counts['reconnect_events'] += not prior[d.drone_id] and linked
            counts['lost_comm_transitions'] += d.state == 'lost_comm' and states[d.drone_id] != 'lost_comm'
            durations[d.drone_id] = 0 if linked else durations.get(d.drone_id,0)+1
            counts['max_offline_ticks'] = max(counts['max_offline_ticks'],durations[d.drone_id])
            prior[d.drone_id] = linked
        last = mission

    for name in names:setattr(Drone,name,instrument(name))
    Mission.update = observed_update
    try:
        result = step4_measure(seed,ticks)
        result.update(communication=counts,
                      physical_average_connectivity=float(np.mean(connected_counts))/len(drones),
                      physical_majority_fraction=sum(n>len(drones)//2 for n in connected_counts)/ticks,
                      physical_full_collapse_ticks=connected_counts.count(0),
                      mean_ms=float(np.mean(latency)),p50_ms=float(np.percentile(latency,50)),
                      p95_ms=float(np.percentile(latency,95)),p99_ms=float(np.percentile(latency,99)),
                      max_ms=max(latency))
        knowledge = dict(drones=[dict(id=d.drone_id,local=sorted(d.map_known),pending=sorted(d.offline_known_cells),
                      survivors=d.mission_found,pending_survivors=sorted(d.offline_survivor_found)) for d in drones],
                      found=sorted(last.game_map.mission_found),fog=last.game_map.fog.tolist())
        result['knowledge_hash'] = hashlib.sha256(json.dumps(knowledge,sort_keys=True).encode()).hexdigest()
        return result
    finally:
        Mission.update = mission_update
        for name,original in originals.items():setattr(Drone,name,original)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,nargs='+',default=[2026,2027,2031])
    parser.add_argument('--ticks',type=int,default=3600);args=parser.parse_args()
    config.FAILURE_PROB_PER_FRAME=0.0;config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    payload=dict(label=args.label,methodology='step5-physical-observation-v1',results=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='adss-step5-') as runtime:
        config.METRICS_LOG_DIR=runtime
        for seed in args.seeds:
            payload['results'].append(measure(seed,args.ticks))
            args.output.with_suffix('.partial.json').write_text(json.dumps(payload,indent=2)+'\n')
            print(f'completed seed={seed}',flush=True)
    args.output.write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2))
