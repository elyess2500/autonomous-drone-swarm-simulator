"""Ownership and task persistence regressions; no communication-policy changes."""
import random

import numpy as np
import pytest

import config
from core.drone import IDLE, SCANNING, RETURNING, FAILED, CHARGING, LOST_COMM, STRANDED
from core.intelligence import Frontier
from core.map import Map, CELL_FREE, CELL_WIND
from core.swarm import Swarm


@pytest.fixture
def swarm(monkeypatch):
    py_state, np_state = random.getstate(), np.random.get_state()
    monkeypatch.setattr(config, "FAILURE_PROB_PER_FRAME", 0.0)
    with monkeypatch.context() as setup:
        setup.setattr(Swarm, "_initial_assignment", lambda self: None)
        game_map = Map(2026)
        game_map.grid[:] = CELL_FREE
        game_map.fog[:] = False
        game_map.reveal_area(config.BASE_COL, config.BASE_ROW, 4)
        result = Swarm(game_map, 3)
    for drone in result.drones:
        drone.battery.level = 100.0
        drone.comm.connected_ids = {-1}
    result.frontiers.refresh(game_map)
    yield result
    random.setstate(py_state)
    np.random.set_state(np_state)


def claim_frontier(swarm, drone=None):
    drone = drone or swarm.drones[0]
    f = swarm.frontiers.available()[0]
    drone.accept_frontier_task(f, [(12, 8), (13, 8)], swarm.drones, swarm.reservations)
    assert f.assigned_drone == drone.drone_id
    return drone, f


def test_forced_auction_does_not_replace_productive_work(swarm):
    drone, frontier = claim_frontier(swarm)
    before = list(drone.scan_queue)
    swarm.frontiers.frontiers.append(Frontier(9999, 8, 7, 40))
    swarm._negotiate_frontiers(force=True)
    assert drone.current_frontier_id == frontier.frontier_id
    assert drone.scan_queue == before


def test_frontier_refresh_preserves_live_identity_and_owner(swarm):
    drone, frontier = claim_frontier(swarm)
    swarm.game_map.fog[:] = True  # Opportunity disappears; live work still exists.
    swarm.frontiers.refresh(swarm.game_map)
    assert swarm.frontiers.assigned_to(drone.drone_id) is frontier
    assert frontier.frontier_id == drone.current_frontier_id


def test_sector_to_frontier_releases_sector_claim(swarm):
    drone = swarm.drones[0]
    sector = swarm.sectors[1]
    swarm._assign(drone, sector)
    assert sector.assigned_drone == drone.drone_id
    claim_frontier(swarm, drone)
    assert sector.assigned_drone is None
    assert drone.assigned_sector is None


def test_relay_is_not_given_sector_work(swarm):
    drone = swarm.drones[0]
    drone.relay_anchor_active = True
    drone.relay_anchor_cell = drone.cell
    drone.comm_role = "relay"
    swarm._assign_nearest_sector(drone)
    assert drone.state == IDLE
    assert drone.assigned_sector is None and not drone.scan_queue


@pytest.mark.parametrize("state", [RETURNING, FAILED, CHARGING, STRANDED])
def test_terminal_or_return_transition_releases_frontier(swarm, state):
    drone, frontier = claim_frontier(swarm)
    drone.set_state(state)
    assert frontier.assigned_drone is None
    assert drone.current_frontier_id is None
    assert not drone.scan_queue


def test_completion_is_counted_once_before_reassignment(swarm):
    drone, frontier = claim_frontier(swarm)
    drone.scan_queue.clear()
    drone._tick_scanning(1, swarm.drones, swarm.reservations)
    assert swarm.frontiers_completed == 1
    assert frontier.assigned_drone is None
    assert drone.current_frontier_id is None
    drone._tick_scanning(2, swarm.drones, swarm.reservations)
    assert swarm.frontiers_completed == 1


def test_offline_autonomy_keeps_task_until_recovery_cancels(swarm):
    drone, frontier = claim_frontier(swarm)
    drone.set_state(LOST_COMM)
    assert frontier.assigned_drone == drone.drone_id
    drone._switch_lost_comm_recovery(swarm.drones, swarm.reservations, True)
    assert frontier.assigned_drone is None
    assert not drone.scan_queue


def test_stall_recovery_releases_task_for_reassignment(swarm):
    drone, frontier = claim_frontier(swarm)
    drone.path = [(12,8)]
    drone.waypoint_idx = 0
    for frame in range(config.STUCK_REASSIGN_FRAMES + 1):
        drone._tick_stuck_recovery(frame, swarm.drones, swarm.reservations)
    assert drone.state == IDLE and drone.needs_frontier_reassign
    assert frontier.assigned_drone is None


def test_live_task_cannot_be_claimed_by_two_drones(swarm):
    drone, frontier = claim_frontier(swarm)
    second = swarm.drones[1]
    with pytest.raises(ValueError, match="owned"):
        second.accept_frontier_task(frontier,[(12,8)],swarm.drones,swarm.reservations)
    assert frontier.assigned_drone == drone.drone_id


def test_wind_motion_is_not_mistaken_for_a_stall(swarm):
    drone, _ = claim_frontier(swarm)
    swarm.game_map.grid[:] = CELL_WIND
    drone.px, drone.py = swarm.game_map.cell_to_pixel(10,10)
    drone.path = [(60,10)]
    drone.waypoint_idx = 0
    for frame in range(config.STUCK_WARN_FRAMES + 3):
        drone._move_along_path()
        drone._tick_stuck_recovery(frame, swarm.drones, swarm.reservations)
    assert drone._stuck_frames < 3
    assert drone.state == SCANNING


def test_watchdog_preserves_progress_between_waypoints(swarm):
    drone, frontier = claim_frontier(swarm)
    drone.path.clear()  # The previous waypoint was just consumed.
    drone._stuck_frames = 0
    swarm._last_coverage = swarm.game_map.exploration_pct()
    swarm._coverage_stall_frames = config.EXPLORATION_STALL_FRAMES - 1
    swarm._watch_coverage_stall()
    assert drone.current_frontier_id == frontier.frontier_id
    assert drone.scan_queue == [(12, 8), (13, 8)]


def test_invalid_claim_is_atomic(swarm):
    drone, frontier = claim_frontier(swarm)
    before = list(drone.scan_queue)
    with pytest.raises(ValueError):
        swarm._claim_assignment(drone, "frontier", -99)
    assert drone.current_frontier_id == frontier.frontier_id
    assert drone.scan_queue == before


def test_sector_completion_requires_observed_cells(swarm):
    drone = swarm.drones[0]
    sector = swarm.sectors[1]
    swarm._assign(drone, sector)
    drone.scan_queue.clear()
    drone._tick_scanning(1, swarm.drones)
    assert sector.assigned_drone is None and drone.assigned_sector is None
    assert not sector.completed
    swarm._assign(drone, sector)
    for col, row in sector.scan_cells:
        swarm.game_map.fog[row, col] = True
    drone.scan_queue.clear()
    drone._tick_scanning(2, swarm.drones)
    assert sector.completed and sector.assigned_drone is None
    assert drone.drone_id not in swarm.assignments


def test_relay_preemption_releases_exploration_and_honors_lease(swarm, monkeypatch):
    drone, frontier = claim_frontier(swarm)
    monkeypatch.setattr(swarm, "_relay_anchor_count", lambda: 1)
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: [drone.cell])
    swarm._maintain_relay_anchors(1)
    assert drone.relay_anchor_active
    assert frontier.assigned_drone is None and drone.current_frontier_id is None
    assert swarm.assignments[drone.drone_id] == ("relay", drone.drone_id)
    anchor, until = drone.relay_anchor_cell, drone.relay_anchor_until
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: [(22, 12)])
    swarm._maintain_relay_anchors(2)
    swarm._negotiate_frontiers(force=True)
    swarm._assign_nearest_sector(drone)
    assert (drone.relay_anchor_cell, drone.relay_anchor_until) == (anchor, until)
    assert drone.current_frontier_id is None and drone.assigned_sector is None
    drone.set_state(RETURNING)
    assert drone.drone_id not in swarm.assignments and not drone.relay_anchor_active


def test_productive_relay_is_not_retargeted_just_because_lease_elapsed(swarm, monkeypatch):
    drone = swarm.drones[0]
    monkeypatch.setattr(swarm, "_relay_anchor_count", lambda: 1)
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: [drone.cell])
    swarm._maintain_relay_anchors(1)
    anchor = drone.relay_anchor_cell
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: [(22, 12)])
    swarm._maintain_relay_anchors(drone.relay_anchor_until + 1)
    assert drone.relay_anchor_cell == anchor


def test_mesh_detour_preserves_contract_and_remaining_work(swarm, monkeypatch):
    drone, frontier = claim_frontier(swarm)
    remaining = [(12 + i, 8) for i in range(12)]
    drone.scan_queue = list(remaining)
    drone.last_comm_safe_cell = (8, 8)
    monkeypatch.setattr(swarm, "_assign_relay_roles", lambda frame: None)
    swarm.last_comm_snapshot = {"connected": 2, "total": 3, "weak": [drone.drone_id]}
    swarm._comm_repair_timer = config.COMM_MESH_REPAIR_INTERVAL - 1
    swarm._repair_comm_mesh(20)
    assert drone.scan_queue == [(8, 8)] + remaining
    assert drone.current_frontier_id == frontier.frontier_id
    assert frontier.assigned_drone == drone.drone_id


def test_held_outer_relay_does_not_displace_inner_anchor(swarm, monkeypatch):
    drone = swarm.drones[0]
    swarm._claim_assignment(drone, "relay", drone.drone_id)
    drone.comm_role = "relay"
    drone.relay_anchor_active = True
    drone.relay_anchor_cell = (25, 3)
    drone.relay_anchor_until = 100
    monkeypatch.setattr(swarm, "_relay_anchor_count", lambda: 2)
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: [(13, 3), (25, 3)])
    swarm._assign_relay_roles(1)
    assert {d.relay_anchor_cell for d in swarm.drones if d.relay_anchor_active} == {(13, 3), (25, 3)}


def test_offline_completion_counted_before_recovery(swarm, monkeypatch):
    drone, frontier = claim_frontier(swarm)
    drone.set_state(LOST_COMM)
    drone.scan_queue = [drone.cell]
    drone.px, drone.py = swarm.game_map.cell_to_pixel(*drone.cell)
    monkeypatch.setattr(drone, "_can_continue_offline_task", lambda: True)
    drone._tick_offline_autonomous(1, swarm.drones)
    assert swarm.frontiers_completed == 1
    drone._switch_lost_comm_recovery(swarm.drones, force_base=True)
    assert swarm.frontiers_completed == 1 and frontier.assigned_drone is None


def assert_ownership(swarm):
    assert len(set(swarm.assignments.values())) == len(swarm.assignments)
    assert swarm.offline_assignments <= swarm.assignments.keys()
    assert len(swarm.offline_assignments) <= config.COMM_MAX_OFFLINE_EXPLORERS
    for drone in swarm.drones:
        expected = swarm.assignments.get(drone.drone_id)
        projections = []
        if drone.current_frontier_id is not None:
            projections.append(("frontier", drone.current_frontier_id))
            assert swarm.frontiers.assigned_to(drone.drone_id).frontier_id == drone.current_frontier_id
        if drone.assigned_sector is not None:
            projections.append(("sector", drone.assigned_sector))
            assert swarm._get_sector(drone.assigned_sector).assigned_drone == drone.drone_id
        if drone.relay_anchor_active:
            projections.append(("relay", drone.drone_id))
        assert projections == ([] if expected is None else [expected])
    for frontier in swarm.frontiers.frontiers:
        if frontier.assigned_drone is not None:
            assert swarm.assignments[frontier.assigned_drone] == ("frontier", frontier.frontier_id)
    for sector in swarm.sectors:
        if sector.assigned_drone is not None:
            assert swarm.assignments[sector.assigned_drone] == ("sector", sector.idx)


def test_ownership_survives_update_refresh_failure_and_reassignment(swarm):
    swarm._initial_assignment()
    for frame in range(1, 401):
        if frame == 100:
            swarm.drones[0].set_state(FAILED)
        swarm.update(frame, "Clear")
        assert_ownership(swarm)


def test_offline_capacity_is_held_for_live_tasks_across_auctions(swarm, monkeypatch):
    monkeypatch.setattr(config, "COMM_MAX_OFFLINE_EXPLORERS", 1)
    swarm.frontiers.frontiers = [Frontier(100+i, 40, 8+i*8, 100) for i in range(3)]
    for drone in swarm.drones:
        monkeypatch.setattr(drone, "evaluate_frontier_bid", lambda frontier, peers: 1000)
    monkeypatch.setattr(swarm, "_frontier_work_cells", lambda frontier, drone: [frontier.cell])
    first = swarm.drones[0]
    frontier = swarm.frontiers.frontiers[0]
    first.accept_frontier_task(frontier, [frontier.cell], swarm.drones)
    swarm._negotiate_frontiers(force=True)
    assert sum(d.current_frontier_id is not None for d in swarm.drones) == 1
    # Sector fallback must honor the same live capacity.
    swarm._assign(swarm.drones[1], swarm.sectors[-1])
    assert swarm.drones[1].assigned_sector is None
    first.set_state(RETURNING)
    swarm._negotiate_frontiers(force=True)
    assert sum(d.current_frontier_id is not None for d in swarm.drones) == 1


@pytest.mark.parametrize("targets", [[(40, 3)], []])
def test_new_relay_claim_is_within_the_existing_connected_chain(swarm, monkeypatch, targets):
    for drone in swarm.drones:
        drone.px, drone.py = swarm.game_map.cell_to_pixel(40, 3)
    monkeypatch.setattr(swarm, "_relay_anchor_count", lambda: 1)
    monkeypatch.setattr(swarm, "_relay_anchor_targets", lambda: targets)
    swarm._assign_relay_roles(1)
    relay = next(d for d in swarm.drones if d.relay_anchor_active)
    safe_range = config.DRONE_COMM_RANGE / config.CELL_SIZE * config.COMM_RELAY_SAFE_RANGE
    import math
    assert math.dist(relay.relay_anchor_cell, (config.BASE_COL, config.BASE_ROW)) <= safe_range
