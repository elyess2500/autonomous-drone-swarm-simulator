"""Step 10 charge-unit policy and charging readiness regressions."""
import math
import pytest
import config
from core.map import Map, CELL_FREE, CELL_OBSTACLE, CELL_NOFLY, CELL_WIND
from core.drone import IDLE, SCANNING, CHARGING, RETURNING, STRANDED, LOST_COMM
from core.swarm import Swarm


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(config, 'FAILURE_PROB_PER_FRAME', 0.)
    monkeypatch.setattr(config, 'BASE_COL', 2)
    monkeypatch.setattr(config, 'BASE_ROW', 2)
    monkeypatch.setattr(Swarm, '_initial_assignment', lambda self: None)
    world = Map(2026)
    world.grid[:] = CELL_FREE
    swarm = Swarm(world, 1)
    d = swarm.drones[0]
    d.px, d.py = world.cell_to_pixel(4, 2)
    d.battery.level = 50.
    d.comm.connected_ids = {-1}
    return world, swarm, d


@pytest.mark.parametrize('blocked', [CELL_OBSTACLE, CELL_NOFLY])
def test_close_task_with_large_detour_is_not_affordable(rig, blocked):
    world, _, d = rig
    world.grid[:-1, 5] = blocked
    assert not d.can_accept_task(6, 2)


def test_disconnected_goal_is_not_an_energy_feasible_task(rig):
    world, _, d = rig
    world.grid[:, 5] = CELL_OBSTACLE
    assert not d.can_accept_task(6, 2)
    assert math.isinf(d.estimate_task_energy(6, 2))


def test_estimate_uses_existing_longer_executable_route(rig):
    _, _, d = rig
    d.path = [(4, 2), (4, 40), (6, 40), (6, 2)]
    d.target_cell = (6, 2)
    d.waypoint_idx = 0
    # Outbound travel alone: 78 cells at SCANNING drain, then reserve.
    lower = 78 * config.CELL_SIZE / config.DRONE_SPEED * config.BATTERY_SCAN_DRAIN
    assert d.estimate_task_energy(6, 2) >= lower + config.BATTERY_TASK_RESERVE


def test_ready_drone_without_available_work_does_not_recharge_cycle(rig):
    world, swarm, d = rig
    d.px, d.py = d.base_px
    d.battery.level = config.BATTERY_RELAUNCH_THRESH - .5
    d._dock()
    d._tick_charging()
    assert d.state == IDLE
    for sector in swarm.sectors:
        sector.completed = True
    for tick in range(1, 11):
        swarm._assign_nearest_sector(d)
        d.update(tick, 'Clear', [d])
    assert swarm.accounting.count('charging_started') == 1
    assert swarm.accounting.count('charging_completed') == 1
    assert swarm.accounting.count('relaunch') == 0
    assert d.state == IDLE


def test_direct_frontier_acceptance_rejects_inaccessible_work_before_claim(rig):
    from core.intelligence import Frontier
    world, swarm, d = rig
    world.grid[:, 5] = CELL_OBSTACLE
    f = Frontier(999, 6, 2, 40)
    swarm.frontiers.frontiers = [f]
    assert d.accept_frontier_task(f, [f.cell], [d]) is False
    assert d.drone_id not in swarm.assignments
    assert f.assigned_drone is None
    assert swarm.accounting.count('task_awarded') == 0


def test_relay_selection_does_not_claim_unreachable_anchor(rig, monkeypatch):
    world, swarm, d = rig
    world.grid[:, 5] = CELL_OBSTACLE
    monkeypatch.setattr(swarm, '_relay_anchor_count', lambda: 1)
    monkeypatch.setattr(swarm, '_relay_anchor_targets', lambda: [(6, 2)])
    monkeypatch.setattr(swarm, '_connected_relay_target', lambda cell: cell)
    swarm._assign_relay_roles(1)
    assert d.relay_anchor_cell != (6, 2)


@pytest.mark.parametrize('wind,storm', [(False,False),(True,False),(False,True),(True,True)])
def test_hand_calculated_route_charge_matches_execution_rate(rig, monkeypatch, wind, storm):
    from core.energy import route_energy
    from core.battery import Battery
    world, _, d = rig
    monkeypatch.setattr(config, 'DRONE_SPEED', 2.)
    monkeypatch.setattr(config, 'DRONE_SPEED_WIND', 1.)
    if wind: world.grid[:] = CELL_WIND
    speed = 1. if wind else 2.
    ticks = 1 + math.ceil(2*config.CELL_SIZE/speed)
    rate = config.BATTERY_SCAN_DRAIN + (config.STORM_EXTRA_DRAIN if storm else 0.)
    rate += config.BATTERY_MOVE_DRAIN*.15 if wind else 0.
    need = route_energy(world, (d.px,d.py), [(4,2),(6,2)], SCANNING, 'Stormy' if storm else 'Clear')
    assert need == pytest.approx(ticks*rate)
    battery = Battery(100)
    for _ in range(ticks):battery.update(SCANNING,storm,wind)
    assert battery.consumed == pytest.approx(need)


def test_outbound_affordable_but_round_trip_reserve_boundary(rig, monkeypatch):
    _, _, d = rig
    monkeypatch.setattr(config, 'BATTERY_TASK_RESERVE', 40.)
    estimate = d.energy.estimate((35,2))
    d.battery.level = estimate.total - .0001
    assert d.battery.level > estimate.outbound
    assert not d.can_accept_task(35,2)
    d.battery.level = estimate.total
    assert d.can_accept_task(35,2)
    assert estimate.total == pytest.approx((estimate.outbound+estimate.returning+estimate.work)*config.BATTERY_PATH_INEFFICIENCY+40.)


def test_no_return_route_even_when_work_leg_exists(rig):
    world, _, d = rig
    world.grid[:,5] = CELL_OBSTACLE
    d.px,d.py=world.cell_to_pixel(6,2)
    assert not d.can_accept_task(7,2)
    assert math.isinf(d.estimate_return_energy())


def test_energy_queries_are_pure_and_route_reuse_invalidates_on_terrain_edit(rig):
    world, swarm, d = rig
    before = (d.energy.snapshot(),swarm.accounting.snapshot(),d.ai_rng.getstate())
    d.estimate_task_energy(7,2);d.estimate_return_energy()
    assert (d.energy.snapshot(),swarm.accounting.snapshot(),d.ai_rng.getstate()) == before
    assert d.can_accept_task(7,2)
    searches=d.energy.searches
    assert d.can_accept_task(7,2) and d.energy.searches==searches
    world.grid[:,5]=CELL_OBSTACLE
    assert not d.can_accept_task(7,2) and d.energy.searches>searches


def test_long_replan_triggers_return_without_false_completion(rig, monkeypatch):
    world, swarm, d = rig
    from core.intelligence import Frontier
    f=Frontier(998,7,2,30);swarm.frontiers.frontiers=[f]
    d.battery.level=40.
    assert d.accept_frontier_task(f,[f.cell],[d])
    world.grid[:]=CELL_WIND
    d.path=[(4,2),(4,40),(50,40),(50,2),(7,2)];d.waypoint_idx=0
    d.update(1,'Stormy',[d])
    assert d.state==RETURNING
    assert d.drone_id not in swarm.assignments and f.assigned_drone is None
    assert swarm.accounting.count('energy_return')==1
    assert swarm.accounting.count('task_completed')==0


def test_collision_wait_drains_existing_scanning_rate_and_retains_task(rig):
    world, swarm, d=rig
    from core.intelligence import Frontier
    f=Frontier(997,10,2,30);swarm.frontiers.frontiers=[f]
    assert d.accept_frontier_task(f,[f.cell],[d])
    class Gate:
        frame=1
        def try_move(self,*args):return False
    start=(d.px,d.py);charge=d.battery.level
    d.update(1,'Clear',[d],Gate())
    assert d.battery.level==pytest.approx(charge-config.BATTERY_SCAN_DRAIN)
    assert (d.px,d.py)==start and f.assigned_drone==d.drone_id


def test_low_battery_useful_work_returns_and_offline_recovery_uses_reserve(rig):
    world, _, d=rig
    d.px,d.py=world.cell_to_pixel(15,2)
    d.scan_queue=[(16,2)];d.set_state(SCANNING)
    d.battery.level=config.BATTERY_LOW_THRESH-.01
    d.update(1,'Clear',[d])
    assert d.state==RETURNING and not d.scan_queue
    d.set_state(LOST_COMM);d.scan_queue=[(16,2)]
    assert not d._can_continue_offline_task()
    d._tick_lost_comm(2,[d])
    assert d.lost_comm_recovery_target==d.base_target_cell


def test_ready_wait_then_real_departure_counts_one_relaunch(rig):
    _, swarm, d=rig
    d.px,d.py=d.base_px;d.battery.level=84.5
    d._dock();d._tick_charging()
    for tick in range(1,10):d.update(tick,'Clear',[d])
    assert d.state==IDLE and d.battery.level>=config.BATTERY_RELAUNCH_THRESH
    d.scan_queue=[(10,2)];d.set_state(SCANNING)
    for tick in range(10,13):d.update(tick,'Clear',[d])
    assert swarm.accounting.count('charging_started')==1
    assert swarm.accounting.count('charging_completed')==1
    assert swarm.accounting.count('relaunch')==1
    assert not d.battery.charging and not d._ready_at_base


def test_impossible_external_depletion_still_strands(rig):
    world, swarm, d=rig
    d.px,d.py=world.cell_to_pixel(30,2);d.battery.level=.001
    d.set_state(RETURNING)
    d.update(1,'Clear',[d]);d.update(2,'Clear',[d])
    assert d.state==STRANDED and swarm.accounting.count('stranded')==1


def test_emergency_charge_retains_docking_and_readiness_contract(rig, monkeypatch):
    _, swarm, d=rig
    d.px,d.py=d.base_px;d.battery.level=0;d._dock()
    monkeypatch.setattr(swarm,'_negotiate_frontiers',lambda **kw:None)
    monkeypatch.setattr(swarm,'_assign_nearest_sector',lambda drone:None)
    swarm._emergency_recover_swarm()
    assert d.state==IDLE and d._ready_at_base and d.battery.recharged>0
    assert swarm.accounting.count('charging_completed')==1
    assert swarm.accounting.count('relaunch')==0


def test_sector_energy_filter_uses_work_cell_not_blocked_centroid(rig):
    world, swarm, d=rig
    sector=swarm.sectors[0]
    sector.scan_cells=[(7,2),(8,2)]
    swarm.sectors=[sector]
    c,r=sector.centre;world.grid[r,c]=CELL_OBSTACLE
    swarm._assign_nearest_sector(d)
    assert d.assigned_sector==sector.idx


def test_windy_detour_that_previously_stranded_is_rejected(rig):
    from core.intelligence import Frontier
    world, swarm, d=rig
    world.grid[:]=CELL_WIND;world.grid[:-1,5]=CELL_OBSTACLE
    d.battery.level=60.
    f=Frontier(999,6,2,30);swarm.frontiers.frontiers=[f]
    assert d.accept_frontier_task(f,[f.cell],[d]) is False
    for tick in range(1,6001):d.update(tick,'Clear',[d])
    assert d.state==IDLE and d.is_at_base()
    assert swarm.accounting.count('stranded')==0


def test_active_collision_backoff_is_part_of_predicted_route(rig):
    _, _, d=rig
    d.path=[(10,2)];d.waypoint_idx=0;d.target_cell=(10,2)
    direct=d.energy.estimate((10,2)).outbound
    d._yield_target=(4,8)
    assert d.energy.estimate((10,2)).outbound>direct


def test_sector_checks_personalized_first_work_cell_before_ownership(rig, monkeypatch):
    world, swarm, d=rig
    world.fog[:]=False
    world.grid[:,5]=CELL_OBSTACLE
    sector=swarm.sectors[0];sector.scan_cells=[(4,2),(6,2)]
    monkeypatch.setattr(swarm,'_personalize_scan_queue',lambda drone,cells:list(reversed(cells)))
    swarm._assign(d,sector)
    assert sector.assigned_drone is None and d.assigned_sector is None
    assert swarm.accounting.count('task_awarded')==0


def test_actual_planned_leg_rechecked_before_claim_and_old_path_preserved(rig,monkeypatch):
    from core.intelligence import Frontier
    world,swarm,d=rig
    world.grid[:]=CELL_WIND
    old=[(4,2),(7,2)];d.path=old;d.target_cell=(7,2)
    def detour(*args,**kw):
        d.path=[(4,2),(4,45),(60,45),(60,2),(7,2)]
        d.waypoint_idx=0;d.target_cell=(7,2)
    monkeypatch.setattr(d,'plan_path_to',detour)
    f=Frontier(996,7,2,30);swarm.frontiers.frontiers=[f]
    assert d.accept_frontier_task(f,[f.cell],[d]) is False
    assert d.path is old and d.target_cell==(7,2)
    assert f.assigned_drone is None


def test_low_guard_and_configured_reserve_are_distinct(rig,monkeypatch):
    _,_,d=rig
    d.battery.level=config.BATTERY_LOW_THRESH
    assert d.estimate_task_energy(6,2)<d.battery.level
    assert not d.can_accept_task(6,2)
    d.battery.level+=.001
    assert d.can_accept_task(6,2)
    monkeypatch.setattr(config,'BATTERY_TASK_RESERVE',80.)
    assert not d.can_accept_task(6,2)


def test_mixed_wind_forecast_bounds_unimpeded_execution(rig):
    from core.energy import route_energy
    from core.geometry import motion_step
    from core.battery import Battery
    world,_,d=rig
    world.grid[:,7:9]=CELL_WIND
    position=(d.px,d.py);target=world.cell_to_pixel(10,2)
    estimate=route_energy(world,position,[(10,2)],SCANNING)
    actual=0.
    for _ in range(1000):
        cell=(math.floor(position[0]/config.CELL_SIZE),math.floor(position[1]/config.CELL_SIZE))
        actual+=Battery.drain_per_tick(SCANNING,in_wind=world.is_wind(*cell))
        position,done=motion_step(world,position,target)
        if done:break
    assert done and actual<=estimate


def test_energy_snapshot_metrics_replay_and_legacy_extension_compatibility(monkeypatch,tmp_path):
    import copy
    from dataclasses import asdict
    from core.simulation import make_simulation
    from core.replay import load,validate
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    m=make_simulation(2026)[2]
    for _ in range(12):m.update()
    before=asdict(m.analytics.sample(m))
    assert before['energy_checks']==sum(d.energy.checks for d in m.swarm.drones)
    assert before['energy_route_searches']==sum(d.energy.searches for d in m.swarm.drones)
    snapshot=m.swarm.drones[0].energy.snapshot();snapshot['last']={}
    assert asdict(m.analytics.sample(m))==before
    data=load(m.export_replay(str(tmp_path/'energy.json')))
    assert data['frames'][-1]['metrics']==before
    old=copy.deepcopy(data)
    for frame in old['frames']:
        for drone in frame['drones']:drone.pop('energy')
        for key in ('energy_checks','energy_route_searches','energy_infeasible_checks','energy_returns'):
            frame['metrics'].pop(key)
    validate(old)
    data['frames'][-1]['drones'][0]['energy']['checks']+=1
    with pytest.raises(ValueError,match='energy metric disagreement'):validate(data)
