"""Step 9: uninstrumented update timing and optional, separate renderer timing.

The default core mode imports no main/UI module and sets no SDL driver. Legacy
mode exists only to measure the frozen Step 8 factory with identical probes.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import config
from core.experiment import ExperimentConfig
from core.replay import capture_frame, capture_world


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def inspect(mission):
    frame = capture_frame(mission)
    knowledge = dict(fog=frame['fog'],found=frame['found'],
        drones=[{k:d[k] for k in ('id','known_map','pending_map','local_survivors',
                                 'pending_survivors','pending_survivor_info')} for d in frame['drones']])
    rng = dict(streams=[(key,stream.getstate()) for key,stream in
                       sorted(mission.experiment._streams.items(),key=lambda item:repr(item[0]))],
               agents=[(d.drone_id,d.ai_rng.getstate()) for d in mission.swarm.drones])
    return dict(state_hash=digest(dict(frame=frame,world=capture_world(mission),rng=rng)),
                knowledge_hash=digest(knowledge), rng_hash=digest(rng),
                experiment_identity=mission.experiment.identity,
                accounting=mission.swarm.accounting.snapshot(),
                metrics=asdict(mission.analytics.sample(mission)), summary=mission.summary(),
                outcome=mission.outcome,completion_reason=mission.completion_reason)


def latencies(samples):
    import numpy as np
    return dict(samples=len(samples),mean_ms=float(np.mean(samples)),
                p50_ms=float(np.percentile(samples,50)),p95_ms=float(np.percentile(samples,95)),
                p99_ms=float(np.percentile(samples,99)),max_ms=max(samples))


def factory(name):
    if name == 'legacy':
        from main import make_simulation
    else:
        from core.simulation import make_simulation
    return make_simulation


def run(seed,ticks,entry='core'):
    m = factory(entry)(seed,experiment_config=ExperimentConfig.capture())[2]
    samples=[]
    for _ in range(ticks):
        start=time.perf_counter();m.update();samples.append((time.perf_counter()-start)*1000)
    return dict(seed=seed,ticks=ticks,entry=entry,update=latencies(samples),**inspect(m))


def presentation(seed,ticks,mode,fps):
    """Display-backed composition at equal ticks; no FPS sleep in this probe."""
    config.TARGET_FPS=fps
    if mode == 'headless':
        return dict(mode=mode,fps=fps,**run(seed,ticks))
    import pygame
    import random
    import numpy as np
    from main import make_simulation  # Exercise the application's compatibility factory.
    from ui.presentation import Camera, Particle, render_simulation_frame
    from ui.dashboard import Dashboard
    from ui.minimap import Minimap
    pygame.display.init();pygame.font.init()
    screen=pygame.display.set_mode((config.SCREEN_WIDTH,config.SCREEN_HEIGHT),pygame.HIDDEN)
    driver=pygame.display.get_driver()
    surface=pygame.Surface((config.MAP_PIXEL_W,config.MAP_PIXEL_H))
    camera=Camera();dashboard=Dashboard();minimap=Minimap()
    m=make_simulation(seed,experiment_config=ExperimentConfig.capture())[2]
    if mode=='overlays_off':
        dashboard.draw=lambda *a,**kw:None
        minimap.draw=lambda *a,**kw:None
    flags={key:mode!='overlays_off' for key in ('show_heatmap','show_frontiers','show_reservations',
                                            'show_decisions','show_comm','show_sensor','show_trail')}
    updates=[];draws=[];flips=[]
    try:
        for tick in range(ticks):
            start=time.perf_counter();m.update();updates.append((time.perf_counter()-start)*1000)
            if mode=='reduced' and tick%7:continue
            if mode=='noisy':
                for _ in range(97):random.random()
                np.random.random(31)
            before=inspect(m)
            particles=[Particle(50,50) for _ in range(3)]
            start=time.perf_counter()
            camera.update(m.swarm.drones)
            render_simulation_frame(screen,surface,camera,m.game_map,m.swarm,m,
                                    dashboard,minimap,particles,flags,fps,tick,seed,False)
            draws.append((time.perf_counter()-start)*1000)
            start=time.perf_counter();pygame.display.flip();flips.append((time.perf_counter()-start)*1000)
            assert inspect(m)==before,'Renderer changed authoritative simulation state'
        return dict(seed=seed,ticks=ticks,mode=mode,fps=fps,display_driver=driver,update=latencies(updates),
                    rendering=latencies(draws),display_flip=latencies(flips),**inspect(m))
    finally:
        pygame.display.quit()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',type=int,nargs='+',default=[2026,2027,2031])
    p.add_argument('--ticks',type=int,default=3600)
    p.add_argument('--entry',choices=['core','legacy'],default='core')
    p.add_argument('--matrix',action='store_true')
    args=p.parse_args()
    config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=.003 if args.matrix else 0.
    if args.matrix:config.WEATHER_CHANGE_INTERVAL=30
    result=dict(methodology='step9-uninstrumented-update-v1',results=[])
    with tempfile.TemporaryDirectory(prefix='adss-step9-') as tmp:
        config.METRICS_LOG_DIR=tmp
        for seed in args.seeds:
            if args.matrix:
                for mode,fps in [('headless',60),('normal',60),('normal',30),('normal',144),
                                 ('reduced',60),('overlays_off',60),('noisy',60)]:
                    result['results'].append(presentation(seed,args.ticks,mode,fps))
            else:result['results'].append(run(seed,args.ticks,args.entry))
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.with_suffix('.partial.json').write_text(json.dumps(result,indent=2))
            print('completed seed',seed,flush=True)
        if args.entry=='core' and not args.matrix:
            assert 'main' not in sys.modules and not any(k=='ui' or k.startswith('ui.') for k in sys.modules)
            import pygame
            assert not pygame.get_init() and not pygame.display.get_init() and not pygame.font.get_init()
            result['no_graphical_initialization']=True
    args.output.write_text(json.dumps(result,indent=2)+'\n')
