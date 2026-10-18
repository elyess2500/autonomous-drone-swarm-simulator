"""Step 13 visual evidence and separate render timings; no policy changes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def capture(output, ticks=3600):
    import pygame
    import config
    from core.simulation import make_simulation
    from core.experiment import ExperimentConfig
    from core.replay import ReplayPlayer, capture_frame, capture_world, make_payload
    from benchmarks.step9 import inspect, latencies
    from ui.presentation import (Camera, render_simulation_frame, draw_menu_screen,
                                 draw_pause_screen, draw_settings_screen)
    from ui.dashboard import Dashboard
    from ui.minimap import Minimap
    from ui.replay_view import draw_replay
    output.mkdir(parents=True, exist_ok=True)
    pygame.display.init(); pygame.font.init()
    screen = pygame.display.set_mode((1400, 850), pygame.HIDDEN)
    surface = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
    camera = Camera(); dashboard = Dashboard(); mini = Minimap()
    flags = dict(show_heatmap=False, show_frontiers=False, show_reservations=False,
                 show_decisions=False, show_comm=True, show_sensor=False, show_trail=False)
    evidence = {}; timings = {}
    with tempfile.TemporaryDirectory() as tmp:
        config.QUICK_DEMO_MODE = False; config.FAILURE_PROB_PER_FRAME = 0.
        config.AUTONOMOUS_OFFLINE_MODE = True
        config.METRICS_LOG_DIR = tmp; config.REPLAY_EXPORT_DIR = tmp
        cfg = ExperimentConfig.capture()
        m = make_simulation(2026, experiment_config=cfg)[2]
        frames = [capture_frame(m)]
        def save(name):
            pygame.image.save(screen, str(output/(name+'.png')))
            evidence[name] = dict(tick=m.frame, state=inspect(m),
                states=[d.state for d in m.swarm.drones], found=sorted(m.game_map.mission_found))
        def draw():
            render_simulation_frame(screen, surface, camera, m.game_map, m.swarm, m,
                                    dashboard, mini, [], flags, 60, m.frame, 2026, False)
        draw_menu_screen(screen, 0, 0); save('01_menu')
        draw_settings_screen(screen, 0, flags, camera, 0); save('settings')
        for tick in range(1, ticks+1):
            m.update()
            if tick == 60: draw(); save('02_active')
            if tick == 180:
                dashboard.selected_id = 0
                flags['show_trail'] = True; draw(); save('03_paths'); flags['show_trail'] = False
            if tick == 360: draw(); save('04_communication')
            if m.game_map.mission_found and '05_survivor' not in evidence:draw(); save('05_survivor')
            if tick > 180 and any(d.state in ('returning','charging') for d in m.swarm.drones) and '06_energy' not in evidence:
                draw(); save('06_energy')
            if tick == 900:
                draw(); draw_pause_screen(screen, m, m.swarm, tick, False); save('07_paused')
                for key in flags: flags[key] = True
                draw(); save('09_overlays'); camera.set_zoom(1.8)
                for _ in range(30):camera.update(m.swarm.drones)
                draw(); save('10_dense'); camera.reset()
                flags.update({k:False for k in flags}); flags['show_comm'] = True
        frames.append(capture_frame(m))
        player = ReplayPlayer(make_payload(m, frames, capture_world(m))); player.seek(m.frame)
        draw_replay(screen, player); save('08_replay')
        for mode in ('normal','off','overlays','dense'):
            flags.update({k:mode in ('overlays','dense') for k in flags})
            flags['show_comm'] = mode != 'off'
            if mode == 'dense':
                camera.set_zoom(1.8)
                for _ in range(30):camera.update(m.swarm.drones)
            else:camera.reset()
            before = inspect(m); samples=[]
            for i in range(35):
                start=time.perf_counter(); draw(); elapsed=(time.perf_counter()-start)*1000
                if i >= 5:samples.append(elapsed)
            assert inspect(m) == before
            timings[mode] = latencies(samples)
        evidence['final'] = inspect(m)
        # Additional responsive/inspector QA at the same truthful final state.
        dashboard.selected_id=0;camera.reset()
        flags.update({k:False for k in flags});flags['show_comm']=True
        for size in ((1100,760),(1400,850),(1920,1080)):
            screen=pygame.display.set_mode(size,pygame.HIDDEN)
            draw();save(f'size_{size[0]}')
        if hasattr(dashboard,'selected_id'):
            from ui import console
            console.draw_help(screen);save('help')
    pygame.quit()
    (output/'capture.json').write_text(json.dumps(evidence, indent=2)+'\n')
    (output/'render_timings.json').write_text(json.dumps(timings, indent=2)+'\n')


def expanded_matrix(output, ticks=180):
    """Per-tick exact simulation projection; drawing and control state only vary."""
    import random
    import pygame
    import config
    from core.simulation import make_simulation
    from benchmarks.step11 import projection, digest
    from benchmarks.step9 import inspect
    from ui.presentation import Camera, render_simulation_frame
    from ui.console import SETTINGS
    from ui.dashboard import Dashboard
    from ui.minimap import Minimap
    config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=.003;config.WEATHER_CHANGE_INTERVAL=30
    pygame.display.init();pygame.font.init()
    cases=[('headless',(1400,850),60),('normal',(1400,850),60),('small',(1100,760),30),
           ('large',(1920,1080),144),('reduced',(1400,850),60),('off',(1400,850),60),
           ('noisy',(1400,850),60)]
    results=[];reference=None
    with tempfile.TemporaryDirectory() as tmp:
        config.METRICS_LOG_DIR=tmp;config.REPLAY_EXPORT_DIR=tmp
        for mode,size,fps in cases:
            config.TARGET_FPS=fps
            m=make_simulation(2026)[2];trace=[]
            camera=Camera();dashboard=Dashboard();mini=Minimap()
            flags={k:mode!='off' for _,k in SETTINGS}
            screen=pygame.display.set_mode(size,pygame.HIDDEN)
            surface=pygame.Surface((config.MAP_PIXEL_W,config.MAP_PIXEL_H))
            for tick in range(ticks):
                m.update();before=digest(projection(m));trace.append(before)
                if mode!='headless' and not (mode=='reduced' and tick%7):
                    dashboard.selected_id=tick%len(m.swarm.drones)
                    dashboard.detail_scroll=tick%12
                    camera.set_zoom(.75+(tick%15)/10);camera.pan(7,-3);camera.update(m.swarm.drones)
                    if mode=='noisy':
                        for _ in range(97):random.random()
                        dashboard.help_visible=tick%3==0
                    render_simulation_frame(screen,surface,camera,m.game_map,m.swarm,m,dashboard,mini,[],flags,fps,tick,2026,False)
                    assert digest(projection(m))==before,(mode,tick,'observer mutation')
                if reference is not None:assert trace[-1]==reference[tick],(mode,tick+1,'FIRST divergent tick')
            if reference is None:reference=trace
            results.append(dict(mode=mode,size=size,fps=fps,ticks=ticks,trace_hash=digest(trace),**inspect(m)))
            if mode!='headless':pygame.image.save(screen,str(output.parent/f'matrix_{mode}.png'))
    pygame.quit()
    output.write_text(json.dumps(dict(results=results),indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ticks', type=int, default=3600)
    parser.add_argument('--matrix', action='store_true')
    args = parser.parse_args()
    if args.matrix:expanded_matrix(args.output,args.ticks)
    else:capture(args.output, args.ticks)
