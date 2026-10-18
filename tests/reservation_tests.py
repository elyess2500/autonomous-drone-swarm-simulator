"""Step 4 point-trajectory contract; the shared docking zone is exempt.

The drive helper also runs on the Phase 1 implementation to demonstrate actual
unsafe motion, not just the absence of a new API.
"""
import math
import random

import numpy as np
import pytest

import config
from benchmarks.step4 import field_contact
from core.drone import Drone, SCANNING, FAILED, STRANDED, CHARGING, RETURNING, IDLE
from core.intelligence import ReservationTable
from core.map import Map, CELL_FREE, CELL_OBSTACLE, CELL_WIND
from core.pathfinding import find_path_result
from core.geometry import trajectories_contact


@pytest.fixture
def world(monkeypatch):
    py, np_state = random.getstate(), np.random.get_state()
    monkeypatch.setattr(config, 'FAILURE_PROB_PER_FRAME', 0.0)
    game_map = Map(2026)
    game_map.grid[:] = CELL_FREE
    yield game_map
    random.setstate(py)
    np.random.set_state(np_state)


def drone(world, idx, start, goal=None, state=SCANNING):
    d = Drone(idx, world)
    d.px, d.py = world.cell_to_pixel(*start)
    d.battery.level = 100
    d.comm.connected_ids = {-1}
    d.set_state(state)
    if goal is not None:
        d.path = [goal]
        d.scan_queue = [goal]
        d.target_cell = goal
    return d


def drive(drones, table, frame=1):
    before = {d.drone_id: (d.px,d.py) for d in drones}
    if hasattr(table, 'begin_tick'):
        table.begin_tick(frame, drones)
    else:
        table.rebuild(drones)
    key = getattr(table, 'priority_key', lambda d:d.drone_id)
    for d in sorted(drones, key=key):
        if d.state not in (IDLE, FAILED, STRANDED, CHARGING):
            d._move_along_path()
    for i, a in enumerate(drones):
        for b in drones[i+1:]:
            assert not field_contact(before[a.drone_id], (a.px,a.py),
                                     before[b.drone_id], (b.px,b.py), a.base_px), 'field point contact'


def test_all_cell_time_owners_remain_visible_to_each_other():
    table = ReservationTable()
    table.reserve_path(0,(10,10),[(11,10)])
    table.reserve_path(1,(10,10),[(11,10)])
    tick = min(table.cells[(11,10)])
    assert table.cell_penalty(0,(11,10),tick) > 0
    assert table.cell_penalty(1,(11,10),tick) > 0


def test_smoothed_intermediate_cells_are_reserved(world):
    d = drone(world,0,(10,10),(14,10))
    table = ReservationTable()
    table.rebuild([d])
    assert (11,10) in table.cells and (12,10) in table.cells


@pytest.mark.parametrize('state',[IDLE, FAILED, STRANDED, CHARGING])
def test_stationary_and_inactive_occupancy(world,state):
    d = drone(world,0,(10,10),state=state)
    table = ReservationTable()
    table.rebuild([d])
    assert set(table.cells[d.cell]) == set(range(config.RESERVATION_HORIZON+1))


def test_failure_transition_already_clears_path_in_phase1(world):
    d = drone(world,0,(10,10),(14,10))
    d.set_state(FAILED)
    assert not d.path


def test_inactive_trajectory_stays_put_even_if_stale_path_is_injected(world):
    d = drone(world,0,(10,10),state=FAILED)
    d.path = [(14,10)]
    table = ReservationTable()
    table.rebuild([d])
    assert all(p == (d.px,d.py) for p in table.trajectories[0].values())


@pytest.mark.parametrize('wind',[False,True])
def test_forecast_matches_each_executed_tick_and_arrival(world,wind):
    if wind:
        world.grid[:] = CELL_WIND
    d = drone(world,0,(10,10),(11,10))
    table = ReservationTable()
    table.rebuild([d])
    predicted = table.trajectories[0]
    speed = config.DRONE_SPEED_WIND if wind else config.DRONE_SPEED
    arrival = math.ceil(config.CELL_SIZE/speed)
    assert predicted[arrival] == world.cell_to_pixel(11,10)
    assert predicted[arrival-1] != predicted[arrival]
    for frame in range(1,arrival+1):
        d._move_along_path()
        assert (d.px,d.py) == predicted[frame]


def test_astar_never_queries_reservations_with_accumulated_cost(world):
    class TimedProbe:
        def spatial_penalty(self, owner, cell):
            return 0.0
        def cell_penalty(self, *args):
            pytest.fail('static A* used accumulated cost as reservation time')
        def edge_penalty(self, *args):
            pytest.fail('static A* used accumulated cost as reservation time')
    assert find_path_result(world,10,10,12,10,drone_id=0,
                            reservation_table=TimedProbe()).status == 'found'


@pytest.mark.parametrize('reverse',[False,True])
def test_same_center_arrival_priority_is_deterministic(world,monkeypatch,reverse):
    monkeypatch.setattr(config,'DRONE_SPEED',float(config.CELL_SIZE))
    a,b = drone(world,0,(10,10),(11,10)),drone(world,1,(12,10),(11,10))
    table = ReservationTable()
    table.priority_key = (lambda d:-d.drone_id) if reverse else (lambda d:d.drone_id)
    drive([b,a],table)
    winner = b if reverse else a
    assert (winner.px,winner.py) == world.cell_to_pixel(11,10)
    assert table.counters['waits'] == 1


def test_head_on_swap_waits_instead_of_swapping(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',float(config.CELL_SIZE))
    a,b = drone(world,0,(10,10),(11,10)),drone(world,1,(11,10),(10,10))
    drive([a,b],ReservationTable())
    assert a.cell == (10,10) and b.cell == (11,10)


def test_crossing_diagonals_are_checked_between_tick_boundaries(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',config.CELL_SIZE*math.sqrt(2))
    a,b = drone(world,0,(10,10),(11,11)),drone(world,1,(11,10),(10,11))
    drive([a,b],ReservationTable())


@pytest.mark.parametrize('state',[IDLE,FAILED,STRANDED,CHARGING])
def test_mover_cannot_cross_stationary_or_inactive_center(world,monkeypatch,state):
    monkeypatch.setattr(config,'DRONE_SPEED',config.CELL_SIZE*3.0)
    a,b = drone(world,0,(10,10),(13,10)),drone(world,1,(11,10),state=state)
    drive([a,b],ReservationTable())
    assert a.cell == (10,10)


def test_mixed_wind_speeds_are_checked_at_the_same_fraction_of_tick(world):
    a,b = drone(world,0,(10,10),(12,10)),drone(world,1,(11,10),(9,10))
    a.px = 11*config.CELL_SIZE-.7
    b.px = 11*config.CELL_SIZE+.7
    world.grid[10,10] = CELL_WIND
    drive([a,b],ReservationTable())


def test_single_drone_crosses_narrow_corridor(world):
    world.grid[:] = CELL_OBSTACLE
    world.grid[10,8:17] = CELL_FREE
    d = drone(world,0,(9,10),(15,10))
    table = ReservationTable()
    for frame in range(100):
        drive([d],table,frame)
    assert d._at_cell_center(15,10)


def test_opposing_corridor_traffic_waits_and_recovery_is_bounded(world):
    world.grid[:] = CELL_OBSTACLE
    world.grid[10,10:13] = CELL_FREE
    a,b = drone(world,0,(10,10),(12,10)),drone(world,1,(12,10),(10,10))
    table = ReservationTable()
    table.wait_limit = 3
    table.max_recoveries = 2
    for frame in range(120):
        drive([a,b],table,frame)
    assert 0 < table.counters['recoveries'] <= 4
    assert table.counters['waits'] > 0


def test_shared_base_allows_co_location_and_physical_docking(world):
    a = drone(world,0,(config.BASE_COL-1,config.BASE_ROW),(config.BASE_COL,config.BASE_ROW),RETURNING)
    b = drone(world,1,(config.BASE_COL,config.BASE_ROW),state=CHARGING)
    table = ReservationTable()
    for frame in range(20):
        drive([a,b],table,frame)
    assert a._dock() and b.can_charge_here()
    assert a.state == CHARGING


def test_multiple_simultaneous_conflicts_are_resolved(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',config.CELL_SIZE*1.0)
    ds = [drone(world,i,start,(11,11)) for i,start in enumerate([(10,11),(12,11),(11,10)])]
    drive(ds,ReservationTable())
    assert sum(d._at_cell_center(11,11) for d in ds) == 1


def test_repeated_execution_and_list_permutation_match(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',config.CELL_SIZE*1.0)
    states = []
    for reverse in (False,True):
        ds = [drone(world,0,(10,10),(11,10)),drone(world,1,(12,10),(11,10))]
        table = ReservationTable()
        for frame in range(5):
            drive(list(reversed(ds)) if reverse else ds,table,frame)
        states.append([(d.px,d.py,d.waypoint_idx) for d in ds])
    assert states[0] == states[1]


def test_coincident_departures_separate_before_leaving_shared_base(world):
    start = (config.BASE_COL, config.BASE_ROW)
    goal = (config.BASE_COL+6, config.BASE_ROW)
    a,b = drone(world,0,start,goal), drone(world,1,start,goal)
    table = ReservationTable()
    for frame in range(60):
        drive([a,b],table,frame)
    assert a._at_cell_center(*goal)
    assert table.counters['waits'] > 0


def test_crossing_geometry_at_different_times_is_allowed():
    # Both pass through (147,147), at t=.5 versus t=.25.
    assert not trajectories_contact((140,147),(154,147),(147,140),(147,168),(49,49))


def test_nearly_coincident_departure_cannot_hide_contact_inside_base():
    base = (49.0,49.0)
    a0,a1 = (78.9,49.0),(79.9,49.0)
    b0,b1 = (78.9+1e-9,49.0),(79.9+2e-9,49.0)
    assert trajectories_contact(a0,a1,b0,b1,base)


def test_absolute_epoch_and_high_speed_swept_cells(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',config.CELL_SIZE*4.0)
    d = drone(world,0,(10,10),(14,10))
    table = ReservationTable()
    table.rebuild([d],start_tick=700)
    assert set(table.trajectories[0]) == set(range(700,725))
    for col in range(10,15):
        assert table.cells[(col,10)][701] == {0}
    assert table.trajectories[0][701] == world.cell_to_pixel(14,10)


def test_bounded_sidestep_keeps_task_and_waypoint_until_replanning(world):
    a = drone(world,0,(11,10),state=FAILED)
    b = drone(world,1,(10,10),(12,10))
    b.current_frontier_id = 123
    table = ReservationTable()
    table.wait_limit = 2
    for frame in range(80):
        drive([a,b],table,frame)
    assert table.counters['recoveries'] == 1
    assert b.current_frontier_id == 123 and b.scan_queue == [(12,10)]
    assert b.target_cell == (12,10)
    assert b.cell[1] != 10


def test_collision_wait_does_not_trigger_stall_task_cancellation(world):
    d = drone(world,0,(10,10),(11,10))
    d._collision_waiting = True
    d.current_frontier_id = 123
    d._stuck_frames = config.STUCK_REASSIGN_FRAMES
    d._tick_stuck_recovery(1000,[d])
    assert d.current_frontier_id == 123 and d.scan_queue == [(11,10)]


def test_state_change_clears_obsolete_collision_detour(world):
    d = drone(world,0,(10,10),(11,10))
    d._yield_target = (10,11)
    d.set_state(RETURNING)
    assert d._yield_target is None


def test_duplicate_legacy_owner_requires_explicit_rebuild():
    table = ReservationTable()
    table.reserve_path(0,(10,10),[(11,10)])
    with pytest.raises(ValueError,match='owner'):
        table.reserve_path(0,(10,10),[(10,11)])


def test_reroute_start_waypoint_does_not_reset_backoff_budget(world):
    d = drone(world,0,(10,10),(12,10))
    table = ReservationTable()
    table._attempts[0] = table.max_recoveries
    table.waypoint_progress(d)
    assert table._attempts[0] == table.max_recoveries


def test_returning_forecast_matches_final_approach_and_dock(world):
    d = drone(world,0,(config.BASE_COL,config.BASE_ROW),
              (config.BASE_COL,config.BASE_ROW),RETURNING)
    d.px += config.BASE_DOCKING_RADIUS_PX + 1
    table = ReservationTable()
    table.rebuild([d],start_tick=40)
    for tick in (41,42):
        d._tick_returning([d])
        assert (d.px,d.py) == table.trajectories[0][tick]
    assert d.state == CHARGING


def test_returning_drone_can_yield_around_blocked_docking_entrance(world):
    base = (config.BASE_COL,config.BASE_ROW)
    a,b = drone(world,0,base,state=FAILED),drone(world,1,base,base,RETURNING)
    a.px += config.BASE_DOCKING_RADIUS_PX+1
    b.px += config.BASE_DOCKING_RADIUS_PX+4
    table = ReservationTable()
    table.wait_limit = 2
    sidestepped = False
    for frame in range(60):
        before = (b.px,b.py)
        table.begin_tick(frame,[a,b])
        b._tick_returning([a,b],table)
        assert not field_contact(before,(b.px,b.py),(a.px,a.py),(a.px,a.py),b.base_px)
        sidestepped |= b.py != b.base_px[1]
    assert sidestepped
    assert b.state == CHARGING


def test_no_space_recovery_stops_after_attempt_budget(world,monkeypatch):
    monkeypatch.setattr(config,'DRONE_SPEED',float(config.CELL_SIZE))
    world.grid[:] = CELL_OBSTACLE
    world.grid[10,10:12] = CELL_FREE
    a,b = drone(world,0,(11,10),state=FAILED),drone(world,1,(10,10),(11,10))
    table = ReservationTable()
    table.wait_limit = 2
    for frame in range(60):
        drive([a,b],table,frame)
    assert table.counters['recovery_attempts'] == table.max_recoveries
    assert table.counters['recoveries'] == 0
    assert table.counters['deadlocks'] == 1
    assert b.scan_queue == [(11,10)]
