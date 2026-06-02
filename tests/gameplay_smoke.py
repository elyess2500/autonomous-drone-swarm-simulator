"""
Gameplay reliability smoke test.

Runs a seeded normal-mode mission and verifies the core loop does not stall:
- coverage increases
- at least one survivor is found without demo difficulty
- no drone remains stuck at 0% RTB forever
- at least one recharge/relaunch cycle succeeds
- controlled offline exploration does not become a full communication collapse
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config

config.QUICK_DEMO_MODE = False
config.FAILURE_PROB_PER_FRAME = 0.0
config.AUTONOMOUS_OFFLINE_MODE = True

from main import make_simulation
from core.drone import CHARGING, IDLE, SCANNING, RETURNING, STRANDED, LOST_COMM


def _set_cell_position(drone, col, row):
    px, py = drone.game_map.cell_to_pixel(col, row)
    drone.px = float(px)
    drone.py = float(py)
    drone.vx = 0.0
    drone.vy = 0.0


def _far_passable_cell(game_map):
    reachable = game_map._reachable_from_base()
    for row in range(game_map.rows - 2, 8, -1):
        for col in range(game_map.cols - 2, 8, -1):
            if (col, row) in reachable and game_map.is_passable(col, row):
                return col, row
    raise AssertionError("No far reachable test cell found")


def _offline_test_cell(game_map):
    reachable = game_map._reachable_from_base()
    bx, by = game_map.cell_to_pixel(config.BASE_COL, config.BASE_ROW)
    min_px = config.DRONE_COMM_RANGE + config.CELL_SIZE * 3
    for row in range(8, game_map.rows - 2):
        for col in range(8, game_map.cols - 2):
            px, py = game_map.cell_to_pixel(col, row)
            if (col, row) in reachable and game_map.is_passable(col, row):
                if ((px - bx) ** 2 + (py - by) ** 2) ** 0.5 > min_px:
                    return col, row
    raise AssertionError("No offline reachable test cell found")


def _nearby_scan_cells(game_map, col, row, limit=8):
    reachable = game_map._reachable_from_base()
    cells = []
    for radius in range(0, 4):
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                nc, nr = col + dc, row + dr
                if (nc, nr) in reachable and game_map.is_passable(nc, nr):
                    if (nc, nr) not in cells:
                        cells.append((nc, nr))
                if len(cells) >= limit:
                    return cells
    return cells or [(col, row)]


def _connect_drone_to_base(drone, mission):
    bx, by = drone.base_px
    drone.px = bx
    drone.py = by
    mission.update()


def _run_forced_lost_comm_recovery():
    game_map, swarm, mission, _ = make_simulation(seed=2027)
    drone = swarm.drones[-1]
    _set_cell_position(drone, *_far_passable_cell(game_map))
    drone.battery.level = 100.0
    drone.battery.stop_charging()
    drone.scan_queue = [drone.cell]
    drone.path.clear()
    drone.set_state(SCANNING)
    drone.comm.frames_since_contact = config.SIGNAL_LOSS_FRAMES

    max_lost_streak = 0
    lost_streak = 0
    last_recovery_label = "-"
    recovered = False
    max_frames = config.SIGNAL_LOSS_FRAMES + config.LOST_COMM_TIMEOUT_FRAMES + 1200
    for _ in range(max_frames):
        mission.update()
        if drone.lost_comm_recovery_label != "-":
            last_recovery_label = drone.lost_comm_recovery_label
        if drone.state == LOST_COMM:
            lost_streak += 1
            max_lost_streak = max(max_lost_streak, lost_streak)
        else:
            lost_streak = 0
        if drone.comm.is_connected and drone.state != LOST_COMM:
            recovered = True
            break
        if drone.state in (RETURNING, CHARGING, IDLE) and not drone.comm.is_lost:
            recovered = True
            break

    return {
        "recovered": recovered,
        "max_lost_streak": max_lost_streak,
        "final_state": drone.state,
        "frames_since_contact": drone.comm.frames_since_contact,
        "recovery_label": last_recovery_label,
    }


def _run_offline_autonomy_sync():
    game_map, swarm, mission, _ = make_simulation(seed=2031)
    drone = swarm.drones[-1]
    col, row = _offline_test_cell(game_map)
    _set_cell_position(drone, col, row)
    drone.battery.level = 100.0
    drone.battery.stop_charging()
    drone.scan_queue = _nearby_scan_cells(game_map, col, row)
    drone.path.clear()
    drone.set_state(SCANNING)
    drone.comm.frames_since_contact = config.SIGNAL_LOSS_FRAMES

    for _ in range(config.DRONE_SCAN_INTERVAL * 5):
        mission.update()
        if drone.offline_scan_progress and drone.offline_known_cells:
            break

    offline_cells = set(drone.offline_known_cells)
    unsynced_cells = [
        cell for cell in offline_cells
        if not game_map.fog[cell[1], cell[0]]
    ]
    was_offline_autonomous = any(
        item["queue_remaining"] >= 0 for item in drone.offline_scan_progress
    )

    _connect_drone_to_base(drone, mission)
    synced_cells_visible = all(game_map.fog[row, col] for col, row in offline_cells)

    return {
        "was_offline_autonomous": was_offline_autonomous,
        "offline_cells": len(offline_cells),
        "unsynced_before_reconnect": len(unsynced_cells),
        "pending_after_sync": len(drone.offline_known_cells),
        "synced_cells_visible": synced_cells_visible,
        "comm_mode": drone.comm_mode_label(),
        "field_charging_violation": drone.battery.charging and not drone.can_charge_here(),
    }


def _run_offline_survivor_sync():
    game_map, swarm, mission, _ = make_simulation(seed=2032)
    drone = swarm.drones[-1]
    candidates = []
    bx, by = drone.base_px
    for idx, mz in enumerate(game_map.mission_zones):
        px, py = game_map.cell_to_pixel(mz.col, mz.row)
        dist = ((px - bx) ** 2 + (py - by) ** 2) ** 0.5
        if dist > config.DRONE_COMM_RANGE + config.CELL_SIZE:
            candidates.append((dist, idx, mz))
    if not candidates:
        raise AssertionError("No mission zone suitable for offline survivor test")
    _, survivor_idx, survivor = max(candidates, key=lambda item: item[0])

    _set_cell_position(drone, survivor.col, survivor.row)
    drone.battery.level = 100.0
    drone.battery.stop_charging()
    drone.scan_queue = [(survivor.col, survivor.row)]
    drone.path.clear()
    drone.set_state(SCANNING)
    drone.comm.frames_since_contact = config.SIGNAL_LOSS_FRAMES
    game_map.mission_found.discard(survivor_idx)

    for _ in range(config.DRONE_SCAN_INTERVAL * 3):
        mission.update()
        if survivor_idx in drone.offline_survivor_found:
            break

    detected_offline = survivor_idx in drone.offline_survivor_found
    global_before_sync = survivor_idx in game_map.mission_found
    _connect_drone_to_base(drone, mission)
    global_after_sync = survivor_idx in game_map.mission_found

    return {
        "survivor_idx": survivor_idx,
        "detected_offline": detected_offline,
        "global_before_sync": global_before_sync,
        "global_after_sync": global_after_sync,
        "synced_survivors": drone.offline_synced_survivors,
        "field_charging_violation": drone.battery.charging and not drone.can_charge_here(),
    }


def test_gameplay_smoke():
    game_map, swarm, mission, seed = make_simulation(seed=2026)
    initial_coverage = game_map.exploration_pct()
    max_frames = config.TARGET_FPS * 5 * 60
    minimum_run_frames = config.TARGET_FPS * 3 * 60
    target_coverage_gain = 0.16
    lost_streaks = {drone.drone_id: 0 for drone in swarm.drones}
    max_lost_streaks = {drone.drone_id: 0 for drone in swarm.drones}
    connected_counts = []
    connected_ratios = []
    majority_connected_frames = 0
    full_collapse_frames = 0
    for frame in range(1, max_frames + 1):
        mission.update()
        connected_count = sum(1 for drone in swarm.drones if drone.comm.is_connected)
        connected_counts.append(connected_count)
        connected_ratios.append(connected_count / max(1, len(swarm.drones)))
        if connected_count >= len(swarm.drones) // 2 + 1:
            majority_connected_frames += 1
        if connected_count == 0:
            full_collapse_frames += 1
        for drone in swarm.drones:
            if drone.state == LOST_COMM:
                lost_streaks[drone.drone_id] += 1
                max_lost_streaks[drone.drone_id] = max(
                    max_lost_streaks[drone.drone_id],
                    lost_streaks[drone.drone_id],
                )
            else:
                lost_streaks[drone.drone_id] = 0
        if (game_map.exploration_pct() >= initial_coverage + target_coverage_gain and
                len(game_map.mission_found) >= 1 and
                frame >= minimum_run_frames):
            break

    recharge_drone = swarm.drones[0]
    bx, by = recharge_drone.base_px
    recharge_drone.px = bx
    recharge_drone.py = by
    recharge_drone._dock()
    recharge_drone.battery.level = 0.0
    saw_relaunch = False
    for frame in range(1, 500):
        recharge_drone.update(frame, "Clear", swarm.drones, swarm.reservations)
        if recharge_drone.state == IDLE and recharge_drone.battery.level >= config.BATTERY_RELAUNCH_THRESH:
            saw_relaunch = True
            break

    final_coverage = game_map.exploration_pct()
    stuck_zero_rtb = [
        drone.drone_id for drone in swarm.drones
        if drone.state == RETURNING and drone.battery.is_empty()
    ]
    stranded = [drone.drone_id for drone in swarm.drones if drone.state == STRANDED]
    final_lost = [drone.drone_id for drone in swarm.drones if drone.state == LOST_COMM]
    min_connected = min(connected_counts) if connected_counts else 0
    avg_connected_ratio = sum(connected_ratios) / max(1, len(connected_ratios))
    majority_connected_ratio = majority_connected_frames / max(1, len(connected_counts))
    majority_threshold = len(swarm.drones) // 2 + 1
    comm_debug = swarm.comm_debug_metrics()
    forced_lost_comm = _run_forced_lost_comm_recovery()
    offline_autonomy = _run_offline_autonomy_sync()
    offline_survivor = _run_offline_survivor_sync()

    print(f"seed={seed}")
    print(f"frames={mission.frame}")
    print(f"coverage_start={initial_coverage:.4f}")
    print(f"coverage_end={final_coverage:.4f}")
    print(f"survivors_found={len(game_map.mission_found)}/{len(game_map.mission_zones)}")
    print(f"survivor_detection_bonus={config.SURVIVOR_DETECTION_BONUS}")
    print(f"scan_radius={config.DRONE_SENSOR_RADIUS}")
    print(f"relaunch_succeeded={saw_relaunch}")
    print(f"stuck_zero_rtb={stuck_zero_rtb}")
    print(f"stranded={stranded}")
    print(f"final_lost_comm={final_lost}")
    print(f"max_lost_comm_streaks={max_lost_streaks}")
    print(f"connectivity_min_connected={min_connected}/{len(swarm.drones)}")
    print(f"connectivity_avg_ratio={avg_connected_ratio:.3f}")
    print(f"connectivity_majority_ratio={majority_connected_ratio:.3f}")
    print(f"connectivity_full_collapse_frames={full_collapse_frames}")
    print(f"swarm_comm_repairs={swarm.comm_repair_events}")
    print(f"swarm_full_collapse_events={swarm.full_comm_collapse_events}")
    print(f"relay_drones={comm_debug['relay_drones']}")
    print(f"explorer_drones={comm_debug['explorer_drones']}")
    print(f"avg_frontier_distance={comm_debug['avg_frontier_distance']:.2f}")
    print(f"coverage_growth_per_min={comm_debug['coverage_growth_per_min'] * 100:.2f}%")
    print(f"comm_risk_relaxation={comm_debug['comm_risk_relaxation']:.2f}")
    print(f"offline_risk_assignments={comm_debug['offline_risk_assignments']}")
    print(f"forced_lost_comm={forced_lost_comm}")
    print(f"offline_autonomy={offline_autonomy}")
    print(f"offline_survivor={offline_survivor}")
    print(f"emergency_recoveries={swarm.emergency_recoveries}")

    assert final_coverage >= initial_coverage + target_coverage_gain, "Coverage did not reach the expansion threshold"
    assert len(game_map.mission_found) >= 1, "No survivor was found in normal mode"
    assert not stuck_zero_rtb, "A 0% RTB drone remained in return-to-base"
    assert not stranded, "A drone became stranded during the seeded normal-mode smoke test"
    assert len(final_lost) <= config.COMM_MAX_OFFLINE_EXPLORERS, "Too many drones ended in temporary lost_comm"
    assert majority_connected_ratio >= 0.70, "Swarm did not maintain majority connectivity often enough"
    assert full_collapse_frames == 0, "Full communication collapse occurred"
    assert swarm.full_comm_collapse_events == 0, "Swarm recorded full communication collapse"
    assert avg_connected_ratio >= config.COMM_MIN_CONNECTED_RATIO, "Average connectivity ratio was too low"
    assert max(max_lost_streaks.values()) <= config.LOST_COMM_TIMEOUT_FRAMES + 900, (
        "A drone remained in lost_comm for too long during normal smoke"
    )
    assert forced_lost_comm["recovered"], "Forced lost_comm scenario did not recover"
    assert forced_lost_comm["max_lost_streak"] <= config.LOST_COMM_TIMEOUT_FRAMES + 900, (
        "Forced lost_comm lasted too long"
    )
    assert offline_autonomy["was_offline_autonomous"], "Offline drone did not continue limited exploration"
    assert offline_autonomy["offline_cells"] > 0, "Offline drone did not store local map discoveries"
    assert offline_autonomy["unsynced_before_reconnect"] > 0, "Offline discoveries leaked into global map before sync"
    assert offline_autonomy["pending_after_sync"] == 0, "Offline map discoveries did not clear after sync"
    assert offline_autonomy["synced_cells_visible"], "Offline map discoveries did not sync into global fog"
    assert not offline_autonomy["field_charging_violation"], "Offline drone charged outside the docking zone"
    assert offline_survivor["detected_offline"], "Offline survivor detection was not stored locally"
    assert not offline_survivor["global_before_sync"], "Offline survivor leaked into global mission before sync"
    assert offline_survivor["global_after_sync"], "Offline survivor did not sync after reconnection"
    assert offline_survivor["synced_survivors"] >= 1, "Offline survivor sync count did not increment"
    assert not offline_survivor["field_charging_violation"], "Offline survivor test charged outside docking zone"
    assert saw_relaunch, "No recharge/relaunch cycle completed"


if __name__ == "__main__":
    test_gameplay_smoke()
