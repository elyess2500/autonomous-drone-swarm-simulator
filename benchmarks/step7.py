"""Detached playback matrix and save/load costs; forward metrics use step6.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import pygame
import config
from main import make_simulation
from core.replay import canonical,load
from ui.replay_view import draw_replay
from benchmarks.step6 import state,digest


def run(directory,ticks=180):
    config.FAILURE_PROB_PER_FRAME=0.
    config.QUICK_DEMO_MODE=False
    config.METRICS_LOG_DIR=str(directory/'logs')
    source=make_simulation(2026)[2]
    for _ in range(ticks):source.update()
    path=directory/'matrix.json'
    started=time.perf_counter();source.export_replay(str(path));save_ms=(time.perf_counter()-started)*1000
    started=time.perf_counter();payload=load(path);load_ms=(time.perf_counter()-started)*1000
    results=[];pygame.font.init();screen=pygame.Surface((1400,850))
    for seed,fps,frequency in [(2026,60,0),(999,60,0),(999,60,1),(999,30,1),(999,144,1),(999,60,7)]:
        config.TARGET_FPS=fps
        target=make_simulation(seed)[2];live=state(target)
        started=time.perf_counter();target.load_replay(str(path));player_ms=(time.perf_counter()-started)*1000
        p=target.replay_player;timeline=[];advance_ms=[]
        for tick in range(ticks+10):
            started=time.perf_counter();target.update();advance_ms.append((time.perf_counter()-started)*1000)
            if frequency and tick%frequency==0:draw_replay(screen,p)
            timeline.append([p.tick,digest(p.current)])
        assert state(target)==live
        result=dict(initial_seed=seed,fps=fps,render_every=frequency,
                    live_unchanged=True,playhead=p.tick,snapshot_tick=p.current['frame'],status=p.status,
                    world_hash=digest(p.world),state_hash=digest(p.current),timeline_hash=digest(timeline),
                    knowledge_hash=digest({k:p.current[k] for k in ('fog','heatmap','found')}),
                    experiment_hash=p.identity,player_load_ms=player_ms,
                    mean_advance_ms=sum(advance_ms)/len(advance_ms))
        results.append(result)
    draw_replay(screen,p);pygame.image.save(screen,str(directory/'replay_view.png'))
    return dict(methodology='step7-playback-v2',ticks=ticks,frames=len(payload['frames']),
                file_bytes=path.stat().st_size,save_ms=save_ms,load_validate_ms=load_ms,results=results)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='adss-replay-') as temporary:
        payload=run(Path(temporary))
        import shutil
        shutil.copy2(Path(temporary)/'replay_view.png',args.output.with_suffix('.png'))
    args.output.write_text(json.dumps(payload,indent=2)+'\n')
