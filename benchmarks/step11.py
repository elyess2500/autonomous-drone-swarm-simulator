"""Step 11: clean update timing, per-tick differential traces, sampled profiling.

Profiling is separate: first 120 updates of each 600-update block (720/3600).
Trace/inspection/serialization happen outside the update timer and profiler.
"""
import argparse
from collections import Counter, OrderedDict
import cProfile
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import pstats
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from core.simulation import make_simulation
from core.replay import capture_frame, capture_world, make_payload
from benchmarks.step9 import inspect, latencies


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def first_difference(a, b, path='$'):
    if type(a) is not type(b):
        return dict(path=path, before=a, after=b)
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return dict(path=path+'.'+str(key), before=a.get(key), after=b.get(key))
            found=first_difference(a[key], b[key], path+'.'+str(key))
            if found:return found
    elif isinstance(a, list):
        if len(a)!=len(b):return dict(path=path+'.length',before=len(a),after=len(b))
        for i,(x,y) in enumerate(zip(a,b)):
            found=first_difference(x,y,f'{path}[{i}]')
            if found:return found
    elif a != b:
        return dict(path=path,before=a,after=b)
    return None


def projection(m):
    frame=capture_frame(m)
    rng=dict(streams=[(str(k),v.getstate()) for k,v in sorted(m.experiment._streams.items(),key=lambda p:repr(p[0]))],
             agents=[(d.drone_id,d.ai_rng.getstate()) for d in m.swarm.drones])
    groups={f'drone_{d["id"]}':d for d in frame.pop('drones')}
    groups.update(frame=frame,world=capture_world(m),rng=rng,summary=m.summary(),
                  experiment=m.experiment.identity)
    # Additional state hidden from the playback projection but relevant to flight.
    groups['private']=[dict(battery=vars(d.battery),comm=vars(d.comm),
        timers={k:v for k,v in vars(d).items() if isinstance(v,(str,int,float,bool,type(None)))})
        for d in m.swarm.drones]
    # Normalize sets in communication internals without consuming/mutating them.
    groups['private']=[{**g,'comm':{k:sorted(v) if isinstance(v,set) else v for k,v in g['comm'].items()}}
                       for g in groups['private']]
    groups['private']=copy.deepcopy(groups['private'])
    def detached(value):
        if isinstance(value,dict):
            return [[detached(k),detached(v)] for k,v in sorted(value.items(),key=lambda p:repr(p[0]))]
        if isinstance(value,set):return [detached(v) for v in sorted(value,key=repr)]
        if isinstance(value,(list,tuple)):return [detached(v) for v in value]
        return value
    groups['reservations']={k:detached(v) for k,v in vars(m.swarm.reservations).items()
                            if k not in ('_drones','priority_key')}
    return groups


class Probe:
    """Expensive diagnostic sampling only; never enabled in clean timing runs."""
    def __init__(self):
        import core.energy as e
        self.active=False;self.counts=Counter();self.callers={};self.seen=OrderedDict()
        self.originals=(e.EnergyPolicy.estimate,e.EnergyPolicy.route,e.route_energy)
        self.module=e
        original_estimate,original_route,original_cost=self.originals
        def estimate(policy,*args,**kwargs):
            if not self.active:return original_estimate(policy,*args,**kwargs)
            caller=sys._getframe(1).f_code.co_name+' <- '+sys._getframe(2).f_code.co_name
            stats=self.callers.setdefault(caller,dict(calls=0,seconds=0.,searches=0))
            searches=policy.searches;t=time.perf_counter()
            result=original_estimate(policy,*args,**kwargs)
            stats['calls']+=1;stats['seconds']+=time.perf_counter()-t
            stats['searches']+=policy.searches-searches
            return result
        def route(policy,start,end,record):
            if not self.active:return original_route(policy,start,end,record)
            self.counts['route_calls']+=1
            key=(start,end,policy.drone.ai_seed,tuple(sorted(policy.drone.direction_bias.items())),
                 policy.drone._smooth_max_segment,e.config.AI_RANDOMNESS)
            same=policy.terrain==policy.drone.game_map.grid.tobytes()
            hit=same and key in policy.routes
            self.counts['route_hits' if hit else 'route_misses']+=1
            if not same and record:self.counts['route_invalidations']+=1
            if not hit and not record:self.counts['pure_query_route_searches']+=1
            return original_route(policy,start,end,record)
        def cost(world,start,path,activity,weather='Clear'):
            if not self.active:return original_cost(world,start,path,activity,weather)
            key=(id(world),tuple(start),tuple(path),activity,weather)
            self.counts['cost_calls']+=1
            if key in self.seen:self.counts['cost_repeated_inputs']+=1
            result=original_cost(world,start,path,activity,weather)
            if key in self.seen and self.seen[key]==result:self.counts['cost_repeated_results']+=1
            self.seen[key]=result
            if len(self.seen)>4096:self.seen.popitem(last=False)
            return result
        e.EnergyPolicy.estimate=estimate;e.EnergyPolicy.route=route;e.route_energy=cost

    def close(self):
        e=self.module;e.EnergyPolicy.estimate,e.EnergyPolicy.route,e.route_energy=self.originals


def profile_stats(profiler):
    stats=pstats.Stats(profiler)
    rows=[]
    for (file,line,name),(primitive,calls,self_time,total,callers) in stats.stats.items():
        rows.append(dict(function=f'{Path(file).name}:{line}:{name}',calls=calls,
            self_seconds=self_time,cumulative_seconds=total,
            callers={f'{Path(k[0]).name}:{k[1]}:{k[2]}':v for k,v in callers.items()}))
    return dict(total_calls=stats.total_calls,total_self_seconds=stats.total_tt,
        cumulative=sorted(rows,key=lambda r:r['cumulative_seconds'],reverse=True),
        self_time=sorted(rows,key=lambda r:r['self_seconds'],reverse=True))


def run(seed,ticks,out,mode,reference=None,dump_tick=None):
    mission=make_simulation(seed)[2]
    profiler=cProfile.Profile() if mode=='profile' else None
    probe=Probe() if profiler else None
    samples=[];trace=[];checkpoints={};sampled=0
    expected=json.loads(reference.read_text()) if reference else None
    try:
        for tick in range(ticks+1):
            if tick:
                enabled=bool(profiler and (tick-1)%600<120)
                if probe:probe.active=enabled
                if enabled:profiler.enable();sampled+=1
                t=time.perf_counter();mission.update();samples.append((time.perf_counter()-t)*1000)
                if enabled:profiler.disable()
                if probe:probe.active=False
            if mode!='profile':
                state=projection(mission);hashes={k:digest(v) for k,v in state.items()}
                trace.append(hashes)
                if expected and hashes!=expected[tick]:
                    (out/f'divergence_{seed}_{tick}.json').write_text(canonical(state),encoding='utf-8')
                    raise AssertionError(f'FIRST divergence tick {tick}: {first_difference(expected[tick],hashes)}; rerun baseline with --dump-tick {tick} for field comparison')
                if tick%300==0:checkpoints[str(tick)]=state
                if dump_tick==tick:
                    (out/f'dump_{seed}_{tick}.json').write_text(canonical(state),encoding='utf-8');return
        result=dict(seed=seed,ticks=mission.frame,mode=mode,update=latencies(samples),authoritative=inspect(mission))
        if profiler:
            profiler.dump_stats(str(out/f'profile_{seed}.prof'))
            result.update(profile=profile_stats(profiler),profiled_ticks=sampled,
                          probe=dict(counts=dict(probe.counts),callers=probe.callers))
        else:
            (out/f'trace_{seed}.json').write_text(canonical(trace),encoding='utf-8')
            (out/f'checkpoints_{seed}.json').write_text(canonical(checkpoints),encoding='utf-8')
            result['replay_hash']=digest(make_payload(mission,mission.get_replay(),capture_world(mission)))
            result['csv_hash']=hashlib.sha256(Path(mission.metrics_logger.path).read_bytes()).hexdigest()
        (out/f'{mode}_{seed}.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(f'completed {mode} seed={seed} ticks={mission.frame}',flush=True)
    finally:
        if probe:probe.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['clean','profile'],default='clean')
    p.add_argument('--seeds',type=int,nargs='+',default=[2026,2027,2031])
    p.add_argument('--ticks',type=int,default=3600)
    p.add_argument('--drones',type=int,default=8)
    p.add_argument('--reference',type=Path)
    p.add_argument('--dump-tick',type=int)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    # Orchestration barrier: keep profiling/tests separate from clean timing.
    if args.mode=='clean' and (args.output.parent/'TIMING_HOLD').exists():
        print('Waiting for timing barrier release',flush=True)
        while (args.output.parent/'TIMING_HOLD').exists():time.sleep(1)
    config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=0.;config.NUM_DRONES=args.drones
    with tempfile.TemporaryDirectory(prefix='adss-step11-') as tmp:
        config.METRICS_LOG_DIR=tmp
        for seed in args.seeds:
            run(seed,args.ticks,args.output,args.mode,
                args.reference/f'trace_{seed}.json' if args.reference else None,args.dump_tick)
