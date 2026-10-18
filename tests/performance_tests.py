"""Step 11 differential tooling and exact-result optimization contracts."""
import copy
import pytest
import config


def test_differential_finds_first_nested_field_and_event():
    from benchmarks.step11 import first_difference
    before={'events':[{'tick':7,'payload':{'margin':1.}}],'drone':{'px':4.}}
    after=copy.deepcopy(before);after['events'][0]['payload']['margin']=1.000000000000001
    diff=first_difference(before,after)
    assert diff['path']=='$.events[0].payload.margin'
    assert first_difference(before,copy.deepcopy(before)) is None


def test_checkpoint_projection_is_detached(monkeypatch,tmp_path):
    from benchmarks.step11 import projection
    from core.simulation import make_simulation
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    mission=make_simulation(2026)[2]
    state=projection(mission);saved=copy.deepcopy(state)
    mission.swarm.drones[0].battery.level=1.
    mission.swarm.drones[0].comm.connected_ids.clear()
    assert state==saved


@pytest.fixture
def energy_rig(monkeypatch):
    from core.map import Map, CELL_FREE
    from core.swarm import Swarm
    monkeypatch.setattr(config,'BASE_COL',2)
    monkeypatch.setattr(config,'BASE_ROW',2)
    monkeypatch.setattr(Swarm,'_initial_assignment',lambda self:None)
    world=Map(2026);world.grid[:]=CELL_FREE
    swarm=Swarm(world,1);drone=swarm.drones[0]
    drone.px,drone.py=world.cell_to_pixel(4,2)
    return world,swarm,drone


def test_repeated_cost_reuses_geometry_but_preserves_assessment(energy_rig,monkeypatch):
    import core.energy as energy
    _,swarm,d=energy_rig
    original=energy.route_energy;calls=[]
    def observed(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(energy,'route_energy',observed)
    first=d.energy.estimate((10,2),record=True)
    geometry_calls=len(calls);searches=d.energy.searches
    accounting=swarm.accounting.snapshot()
    second=d.energy.estimate((10,2),record=True)
    assert first==second
    assert d.energy.checks==2 and d.energy.searches==searches
    assert swarm.accounting.snapshot()==accounting
    assert len(calls)==geometry_calls


@pytest.mark.parametrize('change',[
    'position','route','activity','weather','obstacle','nofly','wind','bounds','dtype',
    'CELL_SIZE','DRONE_SPEED','DRONE_SPEED_WIND','BATTERY_IDLE_DRAIN',
    'BATTERY_MOVE_DRAIN','BATTERY_SCAN_DRAIN','STORM_EXTRA_DRAIN'])
def test_cost_cache_tracks_every_numeric_geometry_input(energy_rig,monkeypatch,change):
    import core.energy as energy
    from core.map import CELL_OBSTACLE,CELL_NOFLY,CELL_WIND
    world,_,d=energy_rig
    start=(d.px,d.py);path=((10,2),);activity='scanning';weather='Clear'
    original=energy.route_energy;calls=[]
    def observed(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(energy,'route_energy',observed)
    d.energy._route_cost(world,start,path,activity,weather,True)
    if change=='position':start=(start[0]+.25,start[1])
    elif change=='route':path=((9,2),(10,2))
    elif change=='activity':activity='returning'
    elif change=='weather':weather='Stormy'
    elif change in ('obstacle','nofly','wind'):
        world.grid[2,7]={'obstacle':CELL_OBSTACLE,'nofly':CELL_NOFLY,'wind':CELL_WIND}[change]
    elif change=='bounds':world.cols=8
    elif change=='dtype':world.grid=world.grid.astype('int16')
    else:monkeypatch.setattr(config,change,getattr(config,change)*1.2)
    expected=original(world,start,path,activity,weather)
    actual=d.energy._route_cost(world,start,path,activity,weather,True)
    assert actual==expected  # Exact floating result, not approximate equivalence.
    assert len(calls)==2
    assert d.energy._route_cost(world,start,path,activity,weather,True)==expected
    assert len(calls)==2


def test_cost_cache_pure_queries_do_not_mutate_it(energy_rig):
    import core.energy as energy
    from core.map import CELL_WIND
    world,_,d=energy_rig;args=(world,(d.px,d.py),((10,2),),'scanning','Clear')
    d.energy._route_cost(*args,False)
    assert not d.energy._cost_cache and d.energy._cost_context is None
    d.energy._route_cost(*args,True)
    old_context=d.energy._cost_context;old_cache=dict(d.energy._cost_cache)
    before=(d.energy.snapshot(),d.ai_rng.getstate())
    d.energy._route_cost(*args,False)
    world.grid[2,7]=CELL_WIND
    assert d.energy._route_cost(*args,False)==energy.route_energy(*args)
    assert d.energy._cost_context==old_context and dict(d.energy._cost_cache)==old_cache
    assert (d.energy.snapshot(),d.ai_rng.getstate())==before


def test_cost_reuse_preserves_battery_reserve_work_and_uncertainty_decisions(energy_rig,monkeypatch):
    import core.energy as energy
    _,swarm,d=energy_rig
    first=d.energy.estimate((10,2),record=True)
    original=energy.route_energy;calls=[]
    def observed(*args):calls.append(1);return original(*args)
    monkeypatch.setattr(energy,'route_energy',observed)
    first=d.energy.estimate((10,2),record=True);calls.clear()
    d.battery.level=first.total-1
    second=d.energy.estimate((10,2),record=True)
    assert second==first and d.energy.rejections==1
    assert d.energy.last['margin']==-1 and not d.energy.last['feasible']
    monkeypatch.setattr(config,'BATTERY_TASK_RESERVE',config.BATTERY_TASK_RESERVE+3)
    reserve=d.energy.estimate((10,2),record=True)
    from dataclasses import replace
    assert reserve==replace(first,reserve=first.reserve+3)
    monkeypatch.setattr(config,'BATTERY_PATH_INEFFICIENCY',2.)
    uncertain=d.energy.estimate((10,2),record=True)
    assert uncertain.uncertainty==(uncertain.outbound+uncertain.returning+uncertain.work)
    monkeypatch.setattr(config,'DRONE_SCAN_INTERVAL',config.DRONE_SCAN_INTERVAL+7)
    work=d.energy.estimate((10,2),record=True)
    assert work.work>uncertain.work and not calls
    assert d.energy.checks==6 and d.energy.rejections==4


def test_cost_cache_is_bounded_and_agent_local(energy_rig):
    from core.energy import EnergyPolicy
    world,_,d=energy_rig
    for i in range(1035):
        d.energy._route_cost(world,(d.px+i/10000,d.py),((10,2),),'scanning','Clear',True)
    assert len(d.energy._cost_cache)==1024
    other=EnergyPolicy(d)
    assert not other._cost_cache and other._cost_context is None


def test_nonstandard_geometry_bypasses_cost_cache(energy_rig,monkeypatch):
    import core.energy as energy
    world,_,d=energy_rig;args=(world,(d.px,d.py),((10,2),),'scanning','Clear')
    normal=d.energy._route_cost(*args,True)
    monkeypatch.setattr(world,'is_wind',lambda *cell:True)
    windy=d.energy._route_cost(*args,True)
    assert windy==energy.route_energy(*args) and windy!=normal
    monkeypatch.setattr(world,'is_passable',lambda *cell:False)
    assert d.energy._route_cost(*args,True)==float('inf')


def test_cost_cache_tracks_world_and_experiment_context(energy_rig,monkeypatch):
    from core.energy import route_energy
    from core.experiment import Experiment,ExperimentConfig
    from core.map import Map,CELL_WIND
    world,_,d=energy_rig;start=(d.px,d.py);path=((10,2),)
    first=Experiment(1,ExperimentConfig.capture())
    monkeypatch.setattr(config,'DRONE_SPEED',config.DRONE_SPEED*.5)
    second=Experiment(1,ExperimentConfig.capture())
    for experiment in [first,second,first]:
        with experiment.activate():
            assert d.energy._route_cost(world,start,path,'scanning','Clear',True)==route_energy(world,start,path,'scanning','Clear')
    another=Map(2027);another.grid[:]=CELL_WIND
    assert d.energy._route_cost(another,start,path,'scanning','Clear',True)==route_energy(another,start,path,'scanning','Clear')


def test_changed_executable_path_and_sidestep_preserve_reference_result(energy_rig):
    from core.energy import route_energy
    world,_,d=energy_rig
    d.path=[(4,2),(10,2)];d.waypoint_idx=0
    first=d.energy.estimate((10,2),record=True)
    d.path=[(4,2),(4,8),(10,8),(10,2)]
    second=d.energy.estimate((10,2),record=True)
    assert second.outbound==route_energy(world,(d.px,d.py),tuple(d.path),'scanning')
    assert second.outbound>first.outbound
    d._yield_target=(4,10)
    route=d.energy.execution_route((10,2),False)
    third=d.energy.estimate((10,2),record=True)
    assert third.outbound==route_energy(world,(d.px,d.py),route,'scanning')
