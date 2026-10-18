"""Point-agent terrain contract: exact center arrival, no corner cutting.

Drone radius remains visual; finite-body and inter-agent coordination are not
part of this tranche. One-cell-wide corridors remain traversable.
"""
import math
import random

import numpy as np
import pytest

import config
from core.drone import Drone, SCANNING, RETURNING, CHARGING
from core.map import Map, CELL_FREE, CELL_OBSTACLE, CELL_WIND
from core.pathfinding import find_path, smooth_path, _line_of_sight
from core.geometry import segment_is_clear


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(config, "FAILURE_PROB_PER_FRAME", 0.0)
    py_state, np_state = random.getstate(), np.random.get_state()
    game_map = Map(3103)
    game_map.grid[:] = CELL_FREE
    yield game_map
    random.setstate(py_state)
    np.random.set_state(np_state)


def place(world, cell):
    drone = Drone(0, world)
    drone.px, drone.py = map(float, world.cell_to_pixel(*cell))
    drone.battery.level = 100.0
    drone.battery.stop_charging()
    return drone


def test_adjacent_target_finishes_at_center(world):
    drone = place(world, (10, 10))
    drone.set_state(SCANNING)
    drone.scan_queue = [(11, 10)]
    for frame in range(60):
        drone._tick_scanning(frame, [])
        if not drone.scan_queue:
            break
    assert not drone.scan_queue
    assert (drone.px, drone.py) == world.cell_to_pixel(11, 10)


@pytest.mark.parametrize("wind", [False, True])
def test_waypoint_arrival_is_exact_and_speed_bounded(world, wind):
    if wind:
        world.grid[:] = CELL_WIND
    drone = place(world, (10, 10))
    drone.path = [(10, 10), (14, 10)]
    expected_speed = config.DRONE_SPEED_WIND if wind else config.DRONE_SPEED
    distances = []
    for _ in range(150):
        before = (drone.px, drone.py)
        drone._move_along_path()
        distances.append(math.dist(before, (drone.px, drone.py)))
        if not drone.has_path():
            break
    assert not drone.has_path()
    assert (drone.px, drone.py) == world.cell_to_pixel(14, 10)
    assert max(distances) <= expected_speed + 1e-9
    assert sum(distances) == pytest.approx(4 * config.CELL_SIZE)


def test_planning_smoothing_and_execution_reject_blocked_corner(world):
    world.grid[:] = CELL_OBSTACLE
    world.grid[10, 10] = world.grid[11, 11] = CELL_FREE
    assert find_path(world, 10, 10, 11, 11) == []
    assert not _line_of_sight(world, (10, 10), (11, 11))
    drone = place(world, (10, 10))
    drone.path = [(11, 11)]  # Even an injected/stale invalid segment must not cross.
    for _ in range(30):
        drone._move_along_path()
    assert drone.cell == (10, 10)


def test_smoothing_preserves_safe_turn_and_corridor(world):
    world.grid[:] = CELL_OBSTACLE
    cells = [(c, 10) for c in range(10, 15)] + [(14, r) for r in range(11, 15)]
    for c, r in cells:
        world.grid[r, c] = CELL_FREE
    raw = find_path(world, 10, 10, 14, 14)
    path = smooth_path(world, raw)
    assert path and (14, 10) in path
    drone = place(world, (10, 10))
    drone.path = path
    for _ in range(200):
        drone._move_along_path()
        assert drone.cell in cells
        if not drone.has_path():
            break
    assert (drone.px, drone.py) == world.cell_to_pixel(14, 14)


def test_final_docking_remains_physical(world):
    drone = place(world, (config.BASE_COL + 4, config.BASE_ROW))
    drone.set_state(RETURNING)
    for frame in range(100):
        before = (drone.px, drone.py)
        was_in_zone = drone.can_charge_here()
        drone.update(frame, "Clear", [drone])
        if drone.state == CHARGING:
            assert was_in_zone
            assert drone.can_charge_here()
            break
        assert not drone.battery.charging
        assert math.dist(before, (drone.px, drone.py)) <= config.DRONE_SPEED + 1e-9
    assert drone.state == CHARGING


def test_segment_supercover_checks_edges_and_both_directions(world):
    world.grid[10, 11] = CELL_OBSTACLE
    for start, end in [((10.5, 10.5), (11.5, 11.5)),
                       ((10.5, 11.0), (12.5, 11.0)),
                       ((11.0, 10.5), (11.0, 12.5))]:
        assert not segment_is_clear(world, start, end)
        assert not segment_is_clear(world, end, start)
    assert segment_is_clear(world, (10.5, 12.5), (12.5, 12.5))


def test_final_approach_routes_around_obstacle(world):
    drone = place(world, (config.BASE_COL + 3, config.BASE_ROW + 2))
    world.grid[config.BASE_ROW + 1, config.BASE_COL + 2] = CELL_OBSTACLE
    drone.set_state(RETURNING)
    for frame in range(200):
        before = (drone.px / config.CELL_SIZE, drone.py / config.CELL_SIZE)
        drone.update(frame, "Clear", [drone])
        if drone.state == CHARGING:
            break  # Existing dock snap is permitted only inside its radius.
        after = (drone.px / config.CELL_SIZE, drone.py / config.CELL_SIZE)
        assert segment_is_clear(world, before, after)
    assert drone.state == CHARGING
