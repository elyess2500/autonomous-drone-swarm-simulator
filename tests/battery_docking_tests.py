"""
Battery/docking regression tests.

These tests prove that charging is tied to the physical base docking zone:
- 0% away from base strands instead of recharging
- 0% at base can recharge
- RTB drones do not charge until they reach the docking zone
- direct dock calls cannot teleport or auto-charge field drones
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config

config.FAILURE_PROB_PER_FRAME = 0.0
config.QUICK_DEMO_MODE = False

from main import make_simulation
from core.drone import CHARGING, IDLE, RETURNING, STRANDED
from core.map import CELL_FREE


def _set_cell_position(drone, col, row):
    px, py = drone.game_map.cell_to_pixel(col, row)
    drone.px = float(px)
    drone.py = float(py)
    drone.vx = 0.0
    drone.vy = 0.0


def _far_passable_cell(game_map):
    for row in range(game_map.rows - 2, 8, -1):
        for col in range(game_map.cols - 2, 8, -1):
            if game_map.is_passable(col, row):
                return col, row
    raise AssertionError("No far passable test cell found")


def _base_adjacent_cell(game_map):
    col = config.BASE_COL + 4
    row = config.BASE_ROW
    game_map.grid[row, col] = CELL_FREE
    return col, row


def test_zero_battery_away_from_base_strands():
    game_map, swarm, _, _ = make_simulation(seed=3101)
    drone = swarm.drones[0]
    _set_cell_position(drone, *_far_passable_cell(game_map))
    start_pos = (drone.px, drone.py)
    drone.battery.level = 0.0
    drone.battery.stop_charging()
    drone.set_state(RETURNING)

    drone.update(1, "Clear", swarm.drones, swarm.reservations)

    assert drone.state == STRANDED
    assert not drone.battery.charging
    assert drone.battery.level == 0.0
    assert not drone.can_charge_here()
    assert (drone.px, drone.py) == start_pos


def test_zero_battery_at_base_recharges():
    _, swarm, _, _ = make_simulation(seed=3102)
    drone = swarm.drones[0]
    _set_cell_position(drone, config.BASE_COL, config.BASE_ROW)
    drone.battery.level = 0.0
    drone.battery.stop_charging()
    drone.set_state(RETURNING)

    drone.update(1, "Clear", swarm.drones, swarm.reservations)
    assert drone.state == CHARGING
    assert drone.battery.charging
    assert drone.can_charge_here()

    drone.update(2, "Clear", swarm.drones, swarm.reservations)
    assert drone.battery.level > 0.0


def test_rtb_drone_must_reach_base_before_charging():
    game_map, swarm, _, _ = make_simulation(seed=3103)
    drone = swarm.drones[0]
    _set_cell_position(drone, *_base_adjacent_cell(game_map))
    drone.battery.level = 100.0
    drone.battery.stop_charging()
    drone.set_state(RETURNING)
    drone.path.clear()
    drone.plan_path_to_base(swarm.drones, swarm.reservations)

    charged_away = False
    reached_charging = False
    for frame in range(1, 600):
        drone.update(frame, "Clear", swarm.drones, swarm.reservations)
        if drone.state == CHARGING:
            reached_charging = True
            charged_away = not drone.can_charge_here()
            break
        assert not drone.battery.charging
        assert not (drone.state == CHARGING and not drone.can_charge_here())

    assert reached_charging
    assert not charged_away
    assert drone.can_charge_here()


def test_direct_dock_call_cannot_teleport_or_field_charge():
    game_map, swarm, _, _ = make_simulation(seed=3104)
    drone = swarm.drones[0]
    _set_cell_position(drone, *_far_passable_cell(game_map))
    start_pos = (drone.px, drone.py)
    drone.battery.level = 0.0
    drone.battery.stop_charging()
    drone.set_state(RETURNING)

    docked = drone._dock()

    assert docked is False
    assert drone.state == STRANDED
    assert not drone.battery.charging
    assert (drone.px, drone.py) == start_pos
    assert not drone.can_charge_here()


def main():
    tests = [
        test_zero_battery_away_from_base_strands,
        test_zero_battery_at_base_recharges,
        test_rtb_drone_must_reach_base_before_charging,
        test_direct_dock_call_cannot_teleport_or_field_charge,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("battery_docking_tests=PASS")


if __name__ == "__main__":
    main()
