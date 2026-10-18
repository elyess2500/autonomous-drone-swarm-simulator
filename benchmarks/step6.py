"""Presentation-independence probe; mission metrics reuse the Step 5 probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import numpy as np
import pygame
import config
from main import make_simulation, render_simulation_frame, Camera, Particle
from ui.dashboard import Dashboard
from ui.minimap import Minimap
from benchmarks.step5 import measure as communication_measure
from core.mission import Mission


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state(mission):
    m, s = mission.game_map, mission.swarm
    drones = [dict(id=d.drone_id, position=[d.px,d.py], state=d.state, battery=d.battery.level,
                   path=d.path, waypoint=d.waypoint_idx, queue=d.scan_queue,
                   frontier=d.current_frontier_id, sector=d.assigned_sector,
                   connected=d.comm.is_connected, contact_age=d.comm.frames_since_contact,
                   lost_age=d.lost_comm_frames, stuck=d._stuck_frames,
                   scan_timer=d._scan_timer, failure_timer=d._fail_timer) for d in s.drones]
    knowledge = dict(fog=m.fog.tolist(), found=sorted(m.mission_found),
                     local=[dict(cells=sorted(d.map_known),pending=sorted(d.offline_known_cells),
                                 survivors=d.mission_found, pending_survivors=sorted(d.offline_survivor_found))
                            for d in s.drones])
    behavioral = dict(tick=mission.frame, drones=drones, grid=m.grid.tolist(), heatmap=m.heatmap.tolist(),
                      weather=mission.weather.current, weather_timer=mission.weather._timer,
                      assignments=s.assignments, awards=s.frontiers_assigned, completions=s.frontiers_completed,
                      cancellations=s.task_cancellations, collision=s.reservations.counters,
                      relaxation=s.comm_risk_relaxation, knowledge=knowledge)
    experiment = getattr(mission, 'experiment', None)
    return dict(state_hash=digest(behavioral), knowledge_hash=digest(knowledge),
                experiment_hash=experiment.identity if experiment else None,
                coverage=m.exploration_pct(), survivors=len(m.mission_found),
                elapsed_seconds=mission.stats.elapsed_seconds(), ticks=mission.frame,
                weather=mission.weather.current, states=s.drone_state_counts())


class Presenter:
    def __init__(self, mode):
        self.mode = mode
        pygame.font.init()
        self.screen = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
        self.surface = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
        self.camera = Camera()
        self.dashboard, self.minimap = Dashboard(), Minimap()
        if mode == 'overlays_off':
            self.dashboard.draw = lambda *args, **kwargs: None
            self.minimap.draw = lambda *args, **kwargs: None

    def draw(self, mission, tick):
        if self.mode == 'headless':
            return
        if self.mode == 'noisy':
            for _ in range(97): random.random()
            np.random.random(31)
        if self.mode == 'reduced' and tick % 7:
            return
        if self.mode == 'delayed' and tick % 13 == 0:
            time.sleep(.002)
        enabled = self.mode != 'overlays_off'
        flags = {k: enabled for k in ('show_heatmap','show_frontiers','show_reservations',
                                     'show_decisions','show_comm','show_sensor','show_trail')}
        particles = [Particle(50,50) for _ in range(3)]
        render_simulation_frame(self.screen,self.surface,self.camera,mission.game_map,mission.swarm,
                                mission,self.dashboard,self.minimap,particles,flags,
                                config.TARGET_FPS,tick,mission.seed,False)


def presentation_run(seed, ticks, mode='headless', fps=60):
    old_fps = config.TARGET_FPS
    config.TARGET_FPS = fps
    try:
        _, _, mission, _ = make_simulation(seed)
        presenter = Presenter(mode)
        for tick in range(ticks):
            mission.update()
            presenter.draw(mission,tick)
        return dict(mode=mode,fps=fps,**state(mission))
    finally:
        config.TARGET_FPS = old_fps


def measure(seed, ticks):
    """Same contact/delivery/latency probes, with final experiment metadata."""
    original = Mission.update
    last = None
    def capture(mission):
        nonlocal last
        last = mission
        return original(mission)
    Mission.update = capture
    try:
        result = communication_measure(seed,ticks)
        experiment = getattr(last,'experiment',None)
        result['experiment_hash'] = experiment.identity if experiment else None
        result['experiment_config'] = json.loads(experiment.canonical_json) if experiment else None
        result['step6_state_hash'] = state(last)['state_hash']
        result['simulation_seconds'] = last.clock.seconds if hasattr(last,'clock') else None
        return result
    finally:
        Mission.update = original


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--matrix',action='store_true')
    parser.add_argument('--ticks',type=int,default=3600)
    parser.add_argument('--seeds',type=int,nargs='+',default=[2026,2027,2031])
    args=parser.parse_args()
    config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=.003 if args.matrix else 0.0
    if args.matrix: config.WEATHER_CHANGE_INTERVAL=30
    args.output.parent.mkdir(parents=True,exist_ok=True)
    payload=dict(methodology='step6-presentation-v1' if args.matrix else 'step5-physical-observation-v1',results=[])
    with tempfile.TemporaryDirectory(prefix='adss-step6-') as runtime:
        config.METRICS_LOG_DIR=runtime
        for seed in args.seeds:
            if args.matrix:
                for mode,fps in [('headless',60),('normal',60),('normal',30),('normal',144),
                                 ('reduced',60),('overlays_off',60),('noisy',60),('delayed',60)]:
                    payload['results'].append(dict(seed=seed,**presentation_run(seed,args.ticks,mode,fps)))
            else:
                payload['results'].append(measure(seed,args.ticks))
            args.output.with_suffix('.partial.json').write_text(json.dumps(payload,indent=2)+'\n')
            print(f'completed seed={seed}',flush=True)
    args.output.write_text(json.dumps(payload,indent=2)+'\n')
