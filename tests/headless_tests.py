"""Step 9: cold-process dependency boundaries, not just dummy SDL rendering."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import pytest

ROOT = Path(__file__).resolve().parents[1]


def cold(code):
    env = dict(os.environ)
    for name in ('SDL_VIDEODRIVER','SDL_AUDIODRIVER'):
        env.pop(name, None)
    result = subprocess.run([sys.executable,'-c',textwrap.dedent(code)], cwd=ROOT,
                            env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_construction_entry_does_not_import_ui():
    cold('''
        import importlib.abc, importlib.util, sys, tempfile
        class NoUI(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, *args):
                if fullname == 'ui' or fullname.startswith('ui.'):
                    raise AssertionError('Simulation construction imported UI: '+fullname)
        sys.meta_path.insert(0,NoUI())
        # Legacy fallback demonstrates the concrete old dependency, not just a
        # missing new module. After extraction only the supported core path runs.
        if importlib.util.find_spec('core.simulation'):
            from core.simulation import make_simulation
        else:
            from main import make_simulation
        import config
        with tempfile.TemporaryDirectory() as tmp:
            config.METRICS_LOG_DIR = tmp
            m = make_simulation(2026)[2]
            m.update()
            assert m.frame == 1
            assert 'main' not in sys.modules
    ''')


def test_presentation_entry_is_independent_of_application():
    cold('''
        import importlib.abc, importlib.util, sys
        class NoApp(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, *args):
                if fullname == 'main':
                    raise AssertionError('Rendering imports application/controller')
        sys.meta_path.insert(0,NoApp())
        if importlib.util.find_spec('ui.presentation'):
            from ui.presentation import render_simulation_frame, Camera, Particle
        else:
            from main import render_simulation_frame, Camera, Particle
        assert 'main' not in sys.modules
    ''')


def test_existing_execution_does_not_need_graphical_initialization():
    cold('''
        import tempfile, importlib.util, pygame, config
        if importlib.util.find_spec('core.simulation'):
            from core.simulation import make_simulation
        else:
            from main import make_simulation
        def forbidden(*a,**kw): raise AssertionError('Graphical initialization requested')
        pygame.init = pygame.display.init = pygame.display.set_mode = forbidden
        pygame.font.init = pygame.mixer.init = pygame.time.Clock = forbidden
        pygame.Surface = forbidden
        with tempfile.TemporaryDirectory() as tmp:
            config.METRICS_LOG_DIR = tmp
            m = make_simulation(2026)[2]
            for _ in range(300): m.update()
            assert m.frame == 300 and m.game_map._tile_surface is None
            assert not pygame.get_init() and not pygame.display.get_init()
    ''')


def test_cold_engine_inspection_csv_replay_and_clean_termination():
    cold('''
        import importlib.abc, sys, tempfile, csv, json, random
        from pathlib import Path
        from dataclasses import asdict
        import numpy as np
        import pygame, config
        class NoApplication(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,*args):
                if fullname=='main' or fullname=='ui' or fullname.startswith('ui.'):
                    raise AssertionError('Headless engine required '+fullname)
        sys.meta_path.insert(0,NoApplication())
        def forbidden(*a,**kw):raise AssertionError('Graphical service requested')
        pygame.init=pygame.display.init=pygame.display.set_mode=forbidden
        pygame.font.init=pygame.mixer.init=pygame.time.Clock=pygame.Surface=forbidden
        pygame.event.get=pygame.key.get_pressed=pygame.mouse.get_pos=forbidden
        from core.simulation import make_simulation
        from core.experiment import ExperimentConfig
        from core.replay import load,ReplayPlayer
        py=random.getstate();np_state=np.random.get_state()
        with tempfile.TemporaryDirectory() as tmp:
            config.METRICS_LOG_DIR=tmp
            config.FAILURE_PROB_PER_FRAME=0.
            cfg=ExperimentConfig.capture()
            world,swarm,m,seed=make_simulation(2026,experiment_config=cfg)
            assert seed==2026 and m.experiment.config is cfg
            for _ in range(360):m.update()
            assert m.frame==360 and m.clock.seconds==6
            assert not pygame.get_init() and not pygame.display.get_init()
            assert not pygame.font.get_init() and pygame.mixer.get_init() is None
            assert pygame.display.get_surface() is None and world._tile_surface is None
            assert m.outcome=='running'
            metrics=asdict(m.analytics.sample(m)); accounting=swarm.accounting.snapshot()
            assert metrics==asdict(m.metrics)==m.summary()['metrics']
            assert accounting['event_hash']==metrics['event_hash']
            assert asdict(m.analytics.sample(m))==metrics
            with open(m.metrics_logger.path,newline='') as stream:
                rows=list(csv.DictReader(stream))
            assert len(rows)==6 and rows[-1]['frame']=='360'
            path=m.export_replay(str(Path(tmp)/'run.json'))
            player=ReplayPlayer(load(path))
            player.seek(360)
            assert player.current['accounting']==accounting
            assert player.current['metrics']==metrics
            assert m.frame==360
            del player,m,swarm,world
            for artifact in Path(tmp).iterdir():artifact.unlink()
        assert py==random.getstate()
        assert np_state[0]==np.random.get_state()[0]
        assert np.array_equal(np_state[1],np.random.get_state()[1])
        assert np_state[2:]==np.random.get_state()[2:]
        assert 'main' not in sys.modules and not any(k.startswith('ui.') for k in sys.modules)
    ''')


def test_sequential_headless_seeds_and_config_context_do_not_leak():
    cold('''
        import tempfile,json,pygame,config
        from core.simulation import make_simulation
        from core.experiment import ExperimentConfig,settings
        from benchmarks.step9 import inspect
        with tempfile.TemporaryDirectory() as tmp:
            config.METRICS_LOG_DIR=tmp;config.REPLAY_EXPORT_DIR=tmp
            config.FAILURE_PROB_PER_FRAME=0.
            cfg=ExperimentConfig.capture()
            results={}
            for seed in (2026,2027,2031,2026):
                m=make_simulation(seed,experiment_config=cfg)[2]
                assert m.frame==0 and m.completed_tick is None and m.outcome=='running'
                assert not m.replay_playback_active and len(m.get_replay())==1
                for _ in range(300):m.update()
                result=inspect(m)
                if seed in results:assert result==results[seed]
                else:results[seed]=result
                # Poison only the finished instance; next construction must reset.
                m.game_map.mission_found=set(range(len(m.game_map.mission_zones)))
                m.update();assert m.outcome=='success'
                m.swarm.accounting.emit('test_isolation')
                m.load_replay(m.export_replay())
            assert len({r['experiment_identity'] for r in results.values()})==3
            assert len({r['state_hash'] for r in results.values()})==3
            config.DRONE_SPEED+=1
            changed=ExperimentConfig.capture()
            a=make_simulation(2026,experiment_config=cfg)[2]
            b=make_simulation(2026,experiment_config=changed)[2]
            for _ in range(12):a.update();b.update()
            assert a.experiment.identity!=b.experiment.identity
            assert settings.DRONE_SPEED==config.DRONE_SPEED
            with a.experiment.activate():assert settings.DRONE_SPEED==cfg.settings['DRONE_SPEED']
            assert settings.DRONE_SPEED==config.DRONE_SPEED
            fresh=make_simulation(2026,experiment_config=cfg)[2]
            for _ in range(12):fresh.update()
            assert inspect(a)==inspect(fresh)
        assert not pygame.get_init() and not pygame.display.get_init()
    ''')


def test_factory_compatibility_aliases_and_snapshot_inspection(monkeypatch,tmp_path):
    import config
    import main
    from core.simulation import make_simulation
    from ui import presentation
    from benchmarks.step9 import inspect
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    assert main.make_simulation is make_simulation
    assert main.render_simulation_frame is presentation.render_simulation_frame
    assert main.Camera is presentation.Camera and main.Particle is presentation.Particle
    a=make_simulation(2026)[2];b=main.make_simulation(2026)[2]
    for _ in range(12):a.update();b.update()
    assert inspect(a)==inspect(b)
    before=inspect(a)
    view=a.summary();view['metrics']['task_awards']=-1
    accounting=a.swarm.accounting.snapshot();accounting['counts'].clear()
    assert inspect(a)==before


@pytest.mark.parametrize('mode,fps',[('normal',60),('normal',30),('normal',144),
                                    ('reduced',60),('overlays_off',60),('noisy',60)])
def test_display_rendering_is_observer_and_matches_headless(monkeypatch,tmp_path,mode,fps):
    import config
    from benchmarks.step9 import presentation
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    monkeypatch.setattr(config,'TARGET_FPS',60)
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',.003)
    monkeypatch.setattr(config,'WEATHER_CHANGE_INTERVAL',3)
    a=presentation(2026,18,'headless',60)
    b=presentation(2026,18,mode,fps)
    for key in ('state_hash','knowledge_hash','rng_hash','experiment_identity','accounting',
                'metrics','outcome','completion_reason','summary'):
        assert a[key]==b[key],key


def test_detached_replay_renderer_needs_no_live_simulation(monkeypatch,tmp_path):
    import pygame
    import config
    from core.simulation import make_simulation
    from core.replay import load,ReplayPlayer
    from ui.replay_view import draw_replay
    from benchmarks.step9 import inspect
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    m=make_simulation(2026)[2]
    for _ in range(12):m.update()
    player=ReplayPlayer(load(m.export_replay(str(tmp_path/'replay.json'))))
    before=inspect(m)
    pygame.font.init()
    screen=pygame.Surface((config.SCREEN_WIDTH,config.SCREEN_HEIGHT))
    snapshot=player.current
    draw_replay(screen,player)
    assert player.current==snapshot and player.tick==0
    assert inspect(m)==before
    del m
    player.seek(12)
    draw_replay(screen,player)
    assert player.current['frame']==12


def test_application_start_pause_resume_and_quit_preserve_engine(monkeypatch,tmp_path):
    """Exercise the real controller loop with deterministic scripted input."""
    import pygame
    import config
    import main
    from core.utils import _font_cache
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    monkeypatch.setattr(config,'RANDOM_SEED',2026)
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',0.)
    original_factory=main.make_simulation
    missions=[]
    def capture(*args,**kwargs):
        result=original_factory(*args,**kwargs)
        missions.append(result[2])
        return result
    monkeypatch.setattr(main,'make_simulation',capture)
    set_mode=pygame.display.set_mode
    monkeypatch.setattr(pygame.display,'set_mode',lambda size,*a,**kw:set_mode(size,pygame.HIDDEN))
    class Clock:
        def tick(self,*a):pass
        def get_fps(self):return 60
    monkeypatch.setattr(pygame.time,'Clock',Clock)
    frames=[]
    commands=iter([pygame.K_1,None,pygame.K_p,None,pygame.K_p,None,'quit'])
    def events():
        frames.append(missions[-1].frame if missions else None)
        command=next(commands)
        if command=='quit':return [pygame.event.Event(pygame.QUIT)]
        return [] if command is None else [pygame.event.Event(pygame.KEYDOWN,key=command)]
    monkeypatch.setattr(pygame.event,'get',events)
    # Clear presentation-only font handles across the real app's pygame.quit().
    _font_cache.clear()
    try:
        with pytest.raises(SystemExit) as stopped:
            main.run_app()
        assert stopped.value.code==0
        assert len(missions)==2  # Existing boot mission, then Start Mission.
        assert missions[0].frame==0
        assert frames[2]==frames[3]==frames[4],frames  # Paused ticks freeze.
        assert frames[5]>frames[4] and frames[6]>frames[5],frames
        assert missions[-1].seed==2026
    finally:
        _font_cache.clear()
