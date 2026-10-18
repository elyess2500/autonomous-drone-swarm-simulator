"""Step 6 clock, random ownership and experiment-boundary regressions."""
import random
import time
import numpy as np
import pytest
import config
from main import make_simulation
from core.map import Map
from benchmarks.step6 import presentation_run, state


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    py_state, np_state = random.getstate(), np.random.get_state()
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',.01)
    monkeypatch.setattr(config,'WEATHER_CHANGE_INTERVAL',3)
    monkeypatch.setattr(config,'QUICK_DEMO_MODE',False)
    yield
    random.setstate(py_state); np.random.set_state(np_state)


@pytest.mark.parametrize('mode,fps',[('normal',60),('normal',30),('normal',144),
                                   ('reduced',60),('overlays_off',60),('noisy',60),('delayed',60)])
def test_presentation_does_not_change_simulation(mode,fps):
    before=presentation_run(2026,65)
    after=presentation_run(2026,65,mode,fps)
    assert after['state_hash']==before['state_hash']
    assert after['knowledge_hash']==before['knowledge_hash']


def test_world_creation_does_not_reseed_global_randomness():
    py=random.getstate(); np_state=np.random.get_state()
    Map(2026)
    assert random.getstate()==py
    assert np.array_equal(np.random.get_state()[1],np_state[1])


def test_mission_time_is_fixed_ticks_and_freezes_without_updates(monkeypatch):
    _,_,m,_=make_simulation(2026)
    monkeypatch.setattr(time,'time',lambda:1e12)
    for _ in range(6):m.update()
    assert m.stats.elapsed_seconds()==pytest.approx(.1)
    before=state(m)
    time.sleep(.005)
    assert state(m)==before


def test_fps_does_not_control_behavioral_seconds(monkeypatch):
    def relaxation(fps):
        monkeypatch.setattr(config,'TARGET_FPS',fps)
        _,s,_,_=make_simulation(2026)
        s._coverage_stall_frames=1000
        for frame in range(1,121):s._update_exploration_balance(frame)
        return s.comm_risk_relaxation
    assert relaxation(30)==relaxation(60)


def test_global_mutation_cannot_change_existing_mission(monkeypatch):
    _,_,a,_=make_simulation(2026)
    _,_,b,_=make_simulation(2026)
    for _ in range(20):a.update()
    monkeypatch.setattr(config,'DRONE_SPEED',100.)
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',1.)
    monkeypatch.setattr(config,'DRONE_COMM_RANGE',1.)
    for _ in range(20):b.update()
    assert state(a)['state_hash']==state(b)['state_hash']


def test_experiment_identity_and_canonical_roundtrip(monkeypatch):
    _,_,m,_=make_simulation(2026)
    experiment=m.experiment
    canonical=experiment.config.canonical_json
    assert type(experiment.config).from_json(canonical).canonical_json==canonical
    monkeypatch.setattr(config,'TARGET_FPS',11)
    assert make_simulation(2026)[2].experiment.identity==experiment.identity
    monkeypatch.setattr(config,'DRONE_SPEED',2.)
    assert make_simulation(2026)[2].experiment.identity!=experiment.identity


def test_different_seeds_generate_different_worlds():
    assert not np.array_equal(Map(2026).grid,Map(2027).grid)


def test_configuration_is_immutable_and_reconstructs_after_global_changes(monkeypatch):
    from core.experiment import ExperimentConfig
    _,_,a,_=make_simulation(2026)
    snapshot=a.experiment.config
    with pytest.raises(TypeError):snapshot.settings['DRONE_SPEED']=100
    with pytest.raises(TypeError):snapshot.settings['WEATHER_TYPES'][0]='Other'
    monkeypatch.setattr(config,'NUM_DRONES',2)
    monkeypatch.setattr(config,'DRONE_SPEED',10.)
    monkeypatch.setattr(config,'WEATHER_CHANGE_INTERVAL',1000)
    _,_,b,_=make_simulation(2026,experiment_config=ExperimentConfig.from_json(snapshot.canonical_json))
    for _ in range(30):
        a.update();b.update()
    assert state(a)==state(b)


def test_interleaved_experiments_and_exception_restore_configuration(monkeypatch):
    from core.experiment import settings as scoped
    _,_,a,_=make_simulation(2026)
    monkeypatch.setattr(config,'DRONE_SPEED',3.)
    _,_,b,_=make_simulation(2031)
    _,_,reference,_=make_simulation(2026,experiment_config=a.experiment.config)
    for _ in range(30):
        a.update();b.update();reference.update()
    assert state(a)==state(reference)
    with pytest.raises(RuntimeError):
        with a.experiment.activate():
            assert scoped.DRONE_SPEED==a.experiment.config.settings['DRONE_SPEED']
            raise RuntimeError('test unwind')
    assert scoped.DRONE_SPEED==3.


@pytest.mark.parametrize('domain',['world','initialization','environment','failure'])
def test_named_stream_extra_draws_do_not_consume_other_domains(domain):
    from core.experiment import Experiment
    a,b=Experiment(2026),Experiment(2026)
    for _ in range(99):a.stream(domain).random()
    for other in ('world','initialization','environment','failure'):
        if other!=domain:
            assert [a.stream(other).random() for _ in range(8)]==[b.stream(other).random() for _ in range(8)]


def test_weather_and_per_agent_failures_own_their_streams():
    from core.experiment import Experiment
    from core.mission import Weather
    a,b=Experiment(2026),Experiment(2026)
    wa,wb=Weather(a.stream('environment')),Weather(b.stream('environment'))
    observed=[]
    for tick in range(36):
        a.stream('failure',0).random()
        random.random()
        wa.update(tick);wb.update(tick)
        assert wa.current==wb.current
        observed.append(wa.current)
    assert len(set(observed))>1
    assert a.stream('failure',1).getstate()==b.stream('failure',1).getstate()


def test_failures_enabled_repeat_despite_presentation_draws(monkeypatch):
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',.08)
    _,_,a,_=make_simulation(2026);_,_,b,_=make_simulation(2026)
    history=[]
    for _ in range(50):
        a.update()
        for _ in range(100):random.random()
        b.update()
        assert state(a)==state(b)
        history.extend(d.state for d in a.swarm.drones)
    assert 'failed' in history


def test_planner_tie_breaking_ignores_presentation_and_weather_draws():
    from core.pathfinding import find_path
    m,swarm,mission,_=make_simulation(2026)
    goal=next(c for c in m._reachable_from_base() if c[0]>15)
    args=dict(ai_seed=swarm.drones[0].ai_seed,randomness=.35)
    before=find_path(m,config.BASE_COL,config.BASE_ROW,*goal,**args)
    for _ in range(99):
        random.random();mission.weather.rng.random()
    assert find_path(m,config.BASE_COL,config.BASE_ROW,*goal,**args)==before


@pytest.mark.parametrize('fps',[15,144])
def test_tick_timers_battery_grace_recovery_and_reservations(monkeypatch,fps):
    from core.battery import Battery
    from core.communication import CommNode
    monkeypatch.setattr(config,'TARGET_FPS',fps)
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',0.)
    _,s,m,_=make_simulation(2026)
    d=s.drones[0]
    d._trigger_failure()
    with m.experiment.activate():
        node=CommNode(99);battery=Battery(50.)
        for _ in range(config.SIGNAL_LOSS_FRAMES-1):node.tick_disconnected()
        assert not node.is_lost
        node.tick_disconnected();assert node.is_lost
        for _ in range(10):battery.update('moving')
        assert battery.level==pytest.approx(50-10*config.BATTERY_MOVE_DRAIN)
        battery.start_charging()
        for _ in range(10):battery.update('charging')
        assert battery.level==pytest.approx(50-10*config.BATTERY_MOVE_DRAIN+10*config.BATTERY_CHARGE_RATE)
        for _ in range(config.FAILURE_RECOVERY_FRAMES-1):d._tick_failed()
        assert d.state=='failed'
        d._tick_failed();assert d.state=='returning'
    for _ in range(3):m.update()
    assert m.frame==s.frame_count==s.reservations.frame==3
    assert m.clock.seconds==.05


def test_completed_time_stays_frozen_even_at_zero_ticks():
    _,_,m,_=make_simulation(2026)
    m.stats.complete()
    m.update()
    assert m.stats.elapsed_seconds()==0.


def test_configuration_serialization_order_and_seed_identity():
    import json
    from core.experiment import Experiment,ExperimentConfig
    a=Experiment(2026)
    value=json.loads(a.config.canonical_json)
    value['settings']=dict(reversed(list(value['settings'].items())))
    b=Experiment(2026,ExperimentConfig.from_json(json.dumps(value)))
    assert a.identity==b.identity
    assert a.identity!=Experiment(2027,a.config).identity


def test_paused_rendering_does_not_advance_any_behavioral_state():
    from benchmarks.step6 import Presenter
    _,_,m,_=make_simulation(2026)
    m.update();before=state(m)
    presenter=Presenter('noisy')
    for tick in range(10):presenter.draw(m,tick)
    assert state(m)==before


@pytest.mark.parametrize('fps',[15,144])
def test_stall_warning_is_measured_in_ticks(monkeypatch,fps):
    monkeypatch.setattr(config,'TARGET_FPS',fps)
    _,s,m,_=make_simulation(2026)
    d=s.drones[0];d.state='scanning';d.scan_queue=[(20,20)]
    d._collision_waiting=False;d._yield_target=None
    with m.experiment.activate():
        for tick in range(config.STUCK_WARN_FRAMES):d._tick_stuck_recovery(tick,s.drones)
        assert d._stuck_frames==config.STUCK_WARN_FRAMES-1
        d._tick_stuck_recovery(config.STUCK_WARN_FRAMES,s.drones)
        assert d.decision=='slow progress; watching congestion'
