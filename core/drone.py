"""
core/drone.py - Individual autonomous drone with full state-machine behaviour.

State machine
─────────────
  IDLE       → waiting at base for assignment
  SCANNING   → actively exploring an assigned sector cell-by-cell
  RETURNING  → flying back to base (low battery or mission complete)
  CHARGING   → docked at base, recharging
  AVOIDING   → short detour around dynamic obstacle
  LOST_COMM  → out of radio range; continues last task autonomously
  FAILED     → hardware failure; stationary until recovered
"""

import math
import random
import numpy as np
import pygame

import config
from core.battery import Battery
from core.communication import CommNode
from core.pathfinding import find_path, smooth_path
from core.utils import pulse

# State identifiers
IDLE      = "idle"
SCANNING  = "scanning"
RETURNING = "returning"
CHARGING  = "charging"
AVOIDING  = "avoiding"
LOST_COMM = "lost_comm"
STRANDED  = "stranded"
FAILED    = "failed"

# State → display colour mapping
STATE_COLOR = {
    IDLE:      config.C_STATE_IDLE,
    SCANNING:  config.C_STATE_SCANNING,
    RETURNING: config.C_STATE_RETURNING,
    CHARGING:  config.C_STATE_CHARGING,
    AVOIDING:  config.C_STATE_AVOIDING,
    LOST_COMM: config.C_STATE_LOST,
    STRANDED:  config.C_STATE_STRANDED,
    FAILED:    config.C_STATE_FAILED,
}


class Drone:
    """
    A single autonomous drone agent.

    Parameters
    ----------
    drone_id : int
        Unique identifier (0-based index).
    game_map : Map
        Shared map reference.
    """

    _id_counter = 0

    def __init__(self, drone_id: int, game_map):
        from core.map import Map
        self.drone_id: int   = drone_id
        self.game_map        = game_map

        # ── World position (pixels) ──────────────
        base_px, base_py = game_map.cell_to_pixel(config.BASE_COL, config.BASE_ROW)
        # Slight random scatter around base so drones don't stack
        self.px: float = base_px + random.uniform(-8, 8)
        self.py: float = base_py + random.uniform(-8, 8)
        self.vx: float = 0.0
        self.vy: float = 0.0

        # ── State ────────────────────────────────
        self.state: str    = IDLE
        self.prev_state: str = IDLE

        # ── Battery & Comms ──────────────────────
        self.battery  = Battery(initial=random.uniform(70, 100))
        self.comm     = CommNode(drone_id)
        self.last_comm_safe_cell: tuple[int, int] = (config.BASE_COL, config.BASE_ROW)
        self.lost_comm_frames = 0
        self.lost_comm_reason = ""
        self.lost_comm_recovery_target: tuple[int, int] | None = None
        self.lost_comm_recovery_label = "-"
        self._lost_comm_retarget_timer = 0
        self.lost_comm_recoveries = 0
        self.offline_autonomous_active = False
        self.offline_rtb_no_comms = False
        self.offline_sync_flash_frames = 0
        self.offline_known_cells: set[tuple[int, int]] = set()
        self.offline_survivor_found: set[int] = set()
        self.offline_survivor_info: dict[int, dict] = {}
        self.offline_scan_progress: list[dict] = []
        self.offline_path_progress: list[dict] = []
        self.offline_synced_cells = 0
        self.offline_synced_survivors = 0
        self.comm_role = "explorer"
        self.relay_anchor_active = False
        self.relay_anchor_cell: tuple[int, int] | None = None
        self.relay_anchor_until = 0
        self.relay_reason = ""
        self.comm_risk_score = 0.0
        self.comm_path_risk_weight = config.COMM_PATH_RISK_WEIGHT

        # Reproducible per-drone navigation personality. These tiny biases
        # break A* ties and smoothing choices without making routes erratic.
        self.ai_seed = (getattr(game_map, "seed", 0) or 0) * 1009 + drone_id * 9176
        self.ai_rng = random.Random(self.ai_seed)
        self.direction_bias = self._build_direction_bias()
        self._smooth_max_segment = max(
            4,
            int(10 - config.AI_RANDOMNESS * 5 + self.ai_rng.randint(0, 3))
        )
        self.base_target_cell = self._choose_base_lane_cell()

        # ── Navigation ───────────────────────────
        self.path: list[tuple[int, int]] = []   # remaining waypoints (col, row)
        self.waypoint_idx = 0
        self.target_cell: tuple[int, int] | None = None   # current high-level goal
        self.current_frontier_id: int | None = None
        self.current_frontier_cell: tuple[int, int] | None = None
        self.decision: str = "booting"
        self.needs_frontier_reassign = False

        # ── Sector / mission assignment ──────────
        self.assigned_sector: int | None = None   # sector index
        self.scan_queue: list[tuple[int, int]] = []   # ordered cells to scan

        # ── Fog of war (local known cells as set) ─
        self.map_known: set[tuple[int, int]] = set()   # cells this drone has seen

        # ── Scan timer ───────────────────────────
        self._scan_timer = 0

        # ── Failure recovery ─────────────────────
        self._fail_timer = 0

        # ── Path re-route timer ──────────────────
        self._reroute_timer = 0
        self._stuck_frames = 0
        self._last_goal_distance: float | None = None
        self._last_stuck_alert_frame = -9999
        self.stuck_recoveries = 0
        self.completed_frontier_id: int | None = None

        # ── Trail for visualisation (last N positions) ─
        self.trail: list[tuple[float, float]] = []
        self._trail_max = 40

        # ── Misc ─────────────────────────────────
        self.alerts: list[str] = []   # short alert strings for the dashboard
        self.mission_found: list[int] = []

    # ──────────────────────────────────────────
    # Properties / helpers
    # ──────────────────────────────────────────

    @property
    def cell(self) -> tuple[int, int]:
        """Current grid cell."""
        return self.game_map.pixel_to_cell(int(self.px), int(self.py))

    @property
    def base_px(self) -> tuple[float, float]:
        bx, by = self.game_map.cell_to_pixel(config.BASE_COL, config.BASE_ROW)
        return float(bx), float(by)

    def distance_to_base(self) -> float:
        bx, by = self.base_px
        return math.hypot(self.px - bx, self.py - by)

    def distance_to_px(self, x: float, y: float) -> float:
        return math.hypot(self.px - x, self.py - y)

    def set_state(self, new_state: str):
        if self.state != new_state:
            self.prev_state = self.state
            self.state = new_state

    def is_in_docking_zone(self) -> bool:
        """True only inside the physical base zone where charging is allowed."""
        return self.distance_to_base() <= config.BASE_DOCKING_RADIUS_PX

    def is_at_base(self) -> bool:
        return self.is_in_docking_zone()

    def is_near_base_for_recovery(self) -> bool:
        return self.distance_to_base() <= config.BASE_DOCKING_RADIUS_PX + config.CELL_SIZE * 4

    def can_charge_here(self) -> bool:
        return self.is_in_docking_zone()

    def charging_status(self) -> str:
        if self.state == CHARGING:
            return "charge ok" if self.can_charge_here() else "charge blocked: not docked"
        if self.state == STRANDED:
            return "stranded: rescue required"
        if self.battery.is_empty() and not self.can_charge_here():
            return "0% away from dock"
        if not self.can_charge_here():
            return "not docked"
        return "docked"

    def comm_mode_label(self) -> str:
        if self.offline_sync_flash_frames > 0:
            return "SYNCING"
        if self.state == LOST_COMM and self.offline_rtb_no_comms:
            return "RTB NO COMMS"
        if self.state == LOST_COMM and self.offline_autonomous_active:
            return "OFFLINE AUTONOMOUS"
        if self.state == LOST_COMM:
            return "RTB NO COMMS"
        return "ONLINE"

    def cannot_relaunch_reason(self) -> str:
        if self.state == CHARGING and self.battery.level < config.BATTERY_RELAUNCH_THRESH:
            if not self.can_charge_here():
                return "charging blocked: not docked"
            return f"charging {self.battery.level:.0f}/{config.BATTERY_RELAUNCH_THRESH:.0f}"
        if self.state == RETURNING:
            return f"rtb dist {self.distance_to_base()/config.CELL_SIZE:.1f}c"
        if self.state == STRANDED:
            return "stranded; manual rescue required"
        if self.state == FAILED:
            return "failed"
        if self.battery.should_return():
            return "battery reserve"
        return "ready"

    def estimate_return_energy(self, col: int | None = None, row: int | None = None,
                               reserve: float = 0.0) -> float:
        """Estimate battery needed to fly from a cell back to the base dock."""
        if col is None or row is None:
            col, row = self.cell
        to_base_cells = math.hypot(col - config.BASE_COL, row - config.BASE_ROW)
        pixels = to_base_cells * config.CELL_SIZE
        frames = pixels / max(0.1, config.DRONE_SPEED)
        return frames * config.BATTERY_MOVE_DRAIN * config.BATTERY_PATH_INEFFICIENCY + reserve

    def has_safe_return_energy(self, col: int | None = None, row: int | None = None) -> bool:
        return self.battery.level >= self.estimate_return_energy(
            col, row, config.BATTERY_TASK_RESERVE
        )

    def estimate_task_energy(self, col: int, row: int) -> float:
        """Estimate battery needed to reach a cell, do useful work, and RTB."""
        dc, dr = self.cell
        to_target_cells = math.hypot(col - dc, row - dr)
        to_base_cells = math.hypot(col - config.BASE_COL, row - config.BASE_ROW)
        pixels = (to_target_cells + to_base_cells) * config.CELL_SIZE
        frames = pixels / max(0.1, config.DRONE_SPEED)
        travel = frames * config.BATTERY_MOVE_DRAIN * config.BATTERY_PATH_INEFFICIENCY
        scan_work = config.DRONE_SCAN_INTERVAL * config.BATTERY_SCAN_DRAIN * 4
        return travel + scan_work + config.BATTERY_TASK_RESERVE

    def can_accept_task(self, col: int, row: int) -> bool:
        if self.state in (FAILED, STRANDED, CHARGING, RETURNING):
            return False
        if self.battery.should_return():
            return False
        return self.battery.level >= self.estimate_task_energy(col, row)

    def task_energy_reason(self, col: int, row: int) -> str:
        need = self.estimate_task_energy(col, row)
        return f"need {need:.0f}, have {self.battery.level:.0f}"

    def _has_return_path_from(self, col: int, row: int) -> bool:
        bc, br = self.base_target_cell
        return bool(find_path(self.game_map, col, row, bc, br,
                              ai_seed=self.ai_seed,
                              drone_id=self.drone_id,
                              direction_bias=self.direction_bias,
                              randomness=config.AI_RANDOMNESS))

    def _can_continue_offline_task(self) -> bool:
        if not getattr(config, "AUTONOMOUS_OFFLINE_MODE", False):
            return False
        if self.battery.should_return() or not self.has_safe_return_energy():
            return False
        if not self.scan_queue:
            return False
        target_col, target_row = self.scan_queue[0]
        if not self.game_map.is_passable(target_col, target_row):
            return False
        if self.battery.level < self.estimate_task_energy(target_col, target_row):
            return False
        return self._has_return_path_from(target_col, target_row)

    def _is_offline_autonomous(self) -> bool:
        return self.state == LOST_COMM and self.offline_autonomous_active

    def _is_offline_disconnected(self) -> bool:
        return (getattr(config, "AUTONOMOUS_OFFLINE_MODE", False) and
                self.state == LOST_COMM)

    def _comm_anchor_cells(self, others=None) -> list[tuple[int, int]]:
        anchors = [(config.BASE_COL, config.BASE_ROW)]
        if not others:
            return anchors
        for peer in others:
            if peer.drone_id == self.drone_id or peer.state in (FAILED, STRANDED):
                continue
            if peer.relay_anchor_active or peer.comm.is_connected:
                anchors.append(peer.cell)
        return anchors

    # ──────────────────────────────────────────
    # Pathfinding helpers
    # ──────────────────────────────────────────

    def plan_path_to(self, col: int, row: int, others=None, reservation_table=None):
        """Compute A* path from current cell to (col, row)."""
        sc, sr = self.cell
        other_cells = [(d.cell) for d in others if d.drone_id != self.drone_id] if others else []
        other_paths = [
            d.path[d.waypoint_idx:]
            for d in others
            if d.drone_id != self.drone_id and d.has_path()
        ] if others else []
        raw = find_path(self.game_map, sc, sr, col, row,
                        other_drone_positions=other_cells,
                        other_drone_paths=other_paths,
                        ai_seed=self.ai_seed,
                        drone_id=self.drone_id,
                        direction_bias=self.direction_bias,
                        reservation_table=reservation_table,
                        comm_anchor_cells=self._comm_anchor_cells(others),
                        comm_range_cells=(config.DRONE_COMM_RANGE / config.CELL_SIZE) * config.COMM_RELAY_SAFE_RANGE,
                        comm_risk_weight=self.comm_path_risk_weight,
                        randomness=config.AI_RANDOMNESS)
        self.path = smooth_path(self.game_map, raw, self._smooth_max_segment)
        self.waypoint_idx = 0
        self.target_cell = (col, row)

    def plan_path_to_base(self, others=None, reservation_table=None):
        bc, br = self.base_target_cell
        self.plan_path_to(bc, br, others, reservation_table)

    def has_path(self) -> bool:
        return bool(self.path) and self.waypoint_idx < len(self.path)

    def current_waypoint_px(self) -> tuple[float, float] | None:
        if not self.has_path():
            return None
        wc, wr = self.path[self.waypoint_idx]
        wx, wy = self.game_map.cell_to_pixel(wc, wr)
        return float(wx), float(wy)

    def advance_waypoint(self):
        self.waypoint_idx += 1

    def _build_direction_bias(self) -> dict[tuple[int, int], float]:
        dirs = [(0, 1), (1, 0), (0, -1), (-1, 0),
                (1, 1), (1, -1), (-1, 1), (-1, -1)]
        preferred = self.ai_rng.choice(dirs)
        bias = {}
        for dx, dy in dirs:
            alignment = dx * preferred[0] + dy * preferred[1]
            bias[(dx, dy)] = -0.04 * config.AI_RANDOMNESS * alignment
        return bias

    def _choose_base_lane_cell(self) -> tuple[int, int]:
        offsets = [
            (0, 0), (1, 0), (0, 1), (-1, 0), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
            (2, 0), (0, 2), (-2, 0), (0, -2),
        ]
        start = self.drone_id % len(offsets)
        for i in range(len(offsets)):
            dc, dr = offsets[(start + i) % len(offsets)]
            col, row = config.BASE_COL + dc, config.BASE_ROW + dr
            if self.game_map.is_passable(col, row):
                return col, row
        return config.BASE_COL, config.BASE_ROW

    def evaluate_frontier_bid(self, frontier, all_drones: list) -> float | None:
        """Score a frontier using this drone's local cost/benefit model."""
        if not self.can_accept_task(frontier.col, frontier.row):
            self.decision = f"frontier too far; {self.task_energy_reason(frontier.col, frontier.row)}"
            return None

        dc, dr = self.cell
        dist = math.hypot(dc - frontier.col, dr - frontier.row)
        peer_pressure = 0.0
        for peer in all_drones:
            if peer.drone_id == self.drone_id or peer.current_frontier_cell is None:
                continue
            pc, pr = peer.current_frontier_cell
            peer_pressure += max(0.0, 8.0 - math.hypot(frontier.col - pc, frontier.row - pr))

        continuity = 6.0 if self.current_frontier_id == frontier.frontier_id else 0.0
        battery_margin = max(0.0, self.battery.level - config.BATTERY_LOW_THRESH)
        seed_noise = self.ai_rng.random() * config.AI_RANDOMNESS
        return (
            frontier.info_gain * 3.5
            - dist * 1.15
            - peer_pressure * 1.6
            + battery_margin * 0.08
            + continuity
            + seed_noise
        )

    def accept_frontier_task(self, frontier, work_cells: list[tuple[int, int]],
                             others: list, reservation_table=None):
        self.current_frontier_id = frontier.frontier_id
        self.current_frontier_cell = frontier.cell
        self.assigned_sector = None
        self.scan_queue = work_cells or [frontier.cell]
        self.needs_frontier_reassign = False
        self.path.clear()
        self.waypoint_idx = 0
        self.set_state(SCANNING)
        self.decision = f"accepted frontier {frontier.frontier_id} gain={frontier.info_gain}"
        first_col, first_row = self.scan_queue[0]
        self.plan_path_to(first_col, first_row, others, reservation_table)

    # ──────────────────────────────────────────
    # Main update tick
    # ──────────────────────────────────────────

    def update(self, frame: int, weather: str, all_drones: list, reservation_table=None):
        """Called once per simulation frame."""
        if self.offline_sync_flash_frames > 0:
            self.offline_sync_flash_frames -= 1

        if self.state == FAILED:
            self._tick_failed()
            return
        if self.state == STRANDED:
            self._tick_stranded()
            return

        if self.state == CHARGING and not self.can_charge_here():
            self.battery.stop_charging()
            if self.battery.is_empty():
                self._strand("charging denied away from docking zone")
            else:
                self._initiate_return(all_drones)
                self.decision = "charging denied; returning to dock"
            return

        in_storm = (weather == "Stormy")
        col, row = self.cell
        in_wind  = self.game_map.is_wind(col, row)

        if self.state == RETURNING and self.battery.is_empty():
            if self.can_charge_here():
                self._dock()
                return
            self._strand("battery depleted before reaching dock")
            return

        # ── Battery drain ────────────────────────
        if self.state != CHARGING:
            self.battery.update(self.state, in_storm=in_storm, in_wind=in_wind)

        if self.state != CHARGING and self.battery.is_empty():
            if self.can_charge_here():
                self._dock()
            else:
                self._strand("battery depleted away from docking zone")
            return

        # ── Alert checks ────────────────────────
        if self.battery.pop_low_alert():
            self.alerts.append(f"D{self.drone_id}: LOW BATTERY")
        if self.battery.pop_critical_alert():
            self.alerts.append(f"D{self.drone_id}: CRITICAL BATTERY!")

        # ── Communication ────────────────────────
        if self.comm.is_connected:
            self.last_comm_safe_cell = self.cell
        if self.comm.is_lost and self.state != CHARGING:
            if self.state != LOST_COMM:
                self._enter_lost_comm(all_drones, reservation_table)
        elif self.state == LOST_COMM and not self.comm.is_lost:
            self._recover_comm_link(all_drones)

        # ── Low battery: force return ────────────
        if (self.state not in (RETURNING, CHARGING, LOST_COMM) and
                (self.battery.should_return() or not self.has_safe_return_energy())):
            self._initiate_return(all_drones)

        # ── Random failure ──────────────────────
        if (self.state not in (FAILED, STRANDED, CHARGING) and
                random.random() < config.FAILURE_PROB_PER_FRAME):
            self._trigger_failure()
            return

        # ── State machine ────────────────────────
        if self.state == IDLE:
            self._tick_idle()
        elif self.state == SCANNING:
            self._tick_scanning(frame, all_drones, reservation_table)
        elif self.state == RETURNING:
            self._tick_returning(all_drones, reservation_table)
        elif self.state == CHARGING:
            self._tick_charging()
        elif self.state == STRANDED:
            self._tick_stranded()
        elif self.state == LOST_COMM:
            self._tick_lost_comm(frame, all_drones, reservation_table)
        elif self.state == AVOIDING:
            self._tick_avoiding(all_drones)

        # ── Reroute check ────────────────────────
        self._reroute_timer += 1
        if self._reroute_timer >= config.REROUTE_INTERVAL:
            self._reroute_timer = 0
            if self.has_path() and self.state not in (CHARGING, IDLE, FAILED, STRANDED):
                wc, wr = self.path[-1]
                self.plan_path_to(wc, wr, all_drones, reservation_table)

        self._tick_stuck_recovery(frame, all_drones, reservation_table)

        # ── Scan the area around current cell ────
        self._scan_timer += 1
        if self._scan_timer >= config.DRONE_SCAN_INTERVAL:
            self._scan_timer = 0
            c, r = self.cell
            if self._is_offline_disconnected():
                self._scan_offline(c, r)
            else:
                self._scan_online(c, r)

        # ── Trail update ─────────────────────────
        self.trail.append((self.px, self.py))
        if len(self.trail) > self._trail_max:
            self.trail.pop(0)

    # ──────────────────────────────────────────
    # State tick methods
    # ──────────────────────────────────────────

    def _tick_idle(self):
        """Wait for sector assignment from Swarm."""
        self._stop()

    def _tick_scanning(self, frame: int, others: list, reservation_table=None):
        """Move to the next scan target in the queue."""
        if not self.scan_queue:
            self.completed_frontier_id = self.current_frontier_id
            self.current_frontier_id = None
            self.current_frontier_cell = None
            self.needs_frontier_reassign = True
            self.set_state(IDLE)
            self.decision = "frontier complete; requesting new task"
            return

        target_col, target_row = self.scan_queue[0]

        if not self.can_accept_task(target_col, target_row):
            self.decision = f"task deferred; {self.task_energy_reason(target_col, target_row)}"
            self.scan_queue.clear()
            self.current_frontier_id = None
            self.current_frontier_cell = None
            self.needs_frontier_reassign = True
            self._initiate_return(others)
            return

        # If we have arrived at the target, pop it
        tc, tr = self.cell
        if tc == target_col and tr == target_row:
            self.scan_queue.pop(0)
            self.path.clear()
            self.decision = "scanned assigned frontier waypoint"
            return

        # Plan path if needed
        if not self.has_path():
            self.plan_path_to(target_col, target_row, others, reservation_table)

        self._move_along_path()

    def _tick_returning(self, others: list, reservation_table=None):
        """Navigate back to base."""
        if self.can_charge_here():
            self._dock()
            return
        if self.battery.is_empty():
            self._strand("battery depleted before reaching dock")
            return
        if self.distance_to_base() <= config.BASE_DOCKING_RADIUS_PX + config.PATH_WAYPOINT_DIST * 1.5:
            self.path.clear()
            self.target_cell = (config.BASE_COL, config.BASE_ROW)
            self.decision = "final docking approach"
            self._move_toward_base_center()
            return
        if not self.has_path():
            self.plan_path_to_base(others, reservation_table)
        self._move_along_path()

    def _tick_charging(self):
        """Charge at base; transition to IDLE when full."""
        if not self.can_charge_here():
            self.battery.stop_charging()
            if self.battery.is_empty():
                self._strand("charging denied away from docking zone")
            else:
                self.set_state(RETURNING)
                self.decision = "charging denied; returning to dock"
            return
        self._stop()
        self.battery.start_charging()
        self.battery.update("charging")
        if self.battery.level >= config.BATTERY_RELAUNCH_THRESH:
            self.battery.stop_charging()
            self.set_state(IDLE)
            self.path.clear()
            self.decision = "charged; ready for relaunch"

    def _tick_stranded(self):
        """Remain immobile until an explicit rescue moves the drone to base."""
        self._stop()
        self.battery.stop_charging()

    def _scan_online(self, col: int, row: int):
        self.game_map.scan_area(col, row, config.DRONE_SENSOR_RADIUS)
        cells = self.game_map.cells_in_radius(col, row, config.DRONE_SENSOR_RADIUS)
        self.map_known.update(cells)
        found = self.game_map.check_mission_discovery(col, row)
        for mz_idx in found:
            self.mission_found.append(mz_idx)
            self.alerts.append(f"D{self.drone_id}: SURVIVOR FOUND zone {mz_idx}!")

    def _append_offline_progress(self, collection: list[dict], item: dict):
        collection.append(item)
        limit = max(20, getattr(config, "OFFLINE_SCAN_PROGRESS_LIMIT", 200))
        if len(collection) > limit:
            del collection[:len(collection) - limit]

    def _scan_offline(self, col: int, row: int):
        cells = self.game_map.cells_in_radius(col, row, config.DRONE_SENSOR_RADIUS)
        self.map_known.update(cells)
        self.offline_known_cells.update(cells)
        self._append_offline_progress(self.offline_scan_progress, {
            "cell": (col, row),
            "cells": len(cells),
            "queue_remaining": len(self.scan_queue),
        })
        self._append_offline_progress(self.offline_path_progress, {
            "cell": self.cell,
            "target": self.target_cell,
            "waypoint_idx": self.waypoint_idx,
            "path_remaining": max(0, len(self.path) - self.waypoint_idx),
        })

        found = self.game_map.detect_mission_near(col, row)
        for mz_idx in found:
            if mz_idx in self.offline_survivor_found:
                continue
            mz = self.game_map.mission_zones[mz_idx]
            self.offline_survivor_found.add(mz_idx)
            self.offline_survivor_info[mz_idx] = {
                "idx": mz_idx,
                "cell": (mz.col, mz.row),
                "detected_from": (col, row),
            }
            self.mission_found.append(mz_idx)
            self.alerts.append(f"D{self.drone_id}: OFFLINE SURVIVOR DETECTED zone {mz_idx}")

    def _sync_offline_discoveries(self) -> tuple[int, int]:
        if not self.offline_known_cells and not self.offline_survivor_found:
            return 0, 0
        synced_cells = self.game_map.reveal_cells(self.offline_known_cells)
        synced_survivors = 0
        for mz_idx in sorted(self.offline_survivor_found):
            if mz_idx not in self.game_map.mission_found:
                self.game_map.mission_found.add(mz_idx)
                synced_survivors += 1
                self.alerts.append(f"D{self.drone_id}: SYNCED SURVIVOR zone {mz_idx}")
        self.offline_synced_cells += synced_cells
        self.offline_synced_survivors += synced_survivors
        self.offline_known_cells.clear()
        self.offline_survivor_found.clear()
        self.offline_survivor_info.clear()
        self.offline_sync_flash_frames = 90
        self.decision = f"syncing offline data cells={synced_cells} survivors={synced_survivors}"
        return synced_cells, synced_survivors

    def lost_comm_timeout_remaining(self) -> int:
        return max(0, config.LOST_COMM_TIMEOUT_FRAMES - self.lost_comm_frames)

    def lost_comm_debug_status(self) -> str:
        mode = self.comm_mode_label()
        if self.state == LOST_COMM:
            status = f"LOST {self.lost_comm_frames}/{config.LOST_COMM_TIMEOUT_FRAMES}"
        elif self.comm.frames_since_contact > 0:
            status = f"weak {self.comm.frames_since_contact}/{config.SIGNAL_LOSS_FRAMES}"
        else:
            status = "linked"
        target = self.lost_comm_recovery_label or "-"
        reason = self.lost_comm_reason or "radio linked"
        return f"D{self.drone_id}:{mode} {status} {reason} -> {target}"

    def _enter_lost_comm(self, others: list, reservation_table=None):
        self.set_state(LOST_COMM)
        self.lost_comm_frames = 0
        self._lost_comm_retarget_timer = config.LOST_COMM_RETARGET_INTERVAL
        self.lost_comm_reason = (
            f"no base/relay path {self.comm.frames_since_contact}/"
            f"{config.SIGNAL_LOSS_FRAMES}"
        )
        self.needs_frontier_reassign = False
        if self._can_continue_offline_task():
            self.offline_autonomous_active = True
            self.offline_rtb_no_comms = False
            self.lost_comm_recovery_target = self.scan_queue[0]
            self.lost_comm_recovery_label = "offline task"
            if not self.has_path():
                col, row = self.scan_queue[0]
                self.plan_path_to(col, row, others, reservation_table)
            self.decision = "offline autonomous exploration"
            self.alerts.append(f"D{self.drone_id}: OFFLINE AUTONOMOUS")
            return

        self._switch_lost_comm_recovery(
            others,
            reservation_table,
            self.battery.should_return() or not self.has_safe_return_energy(),
            "lost comm recovery",
        )

    def _recover_comm_link(self, others: list):
        synced_cells, synced_survivors = self._sync_offline_discoveries()
        self.lost_comm_recoveries += 1
        self.last_comm_safe_cell = self.cell
        self.lost_comm_reason = "radio link restored"
        self.lost_comm_recovery_target = None
        self.lost_comm_recovery_label = "-"
        self.lost_comm_frames = 0
        self._lost_comm_retarget_timer = 0
        self.offline_autonomous_active = False
        self.offline_rtb_no_comms = False
        self.path.clear()
        if self.battery.should_return() or not self.has_safe_return_energy():
            self._initiate_return(others)
            self.decision = "comm restored; returning on battery reserve"
        elif self.scan_queue:
            self.set_state(SCANNING)
            self.decision = (
                f"sync complete; resuming task ({synced_cells} cells, "
                f"{synced_survivors} survivors)"
            )
        else:
            self.set_state(IDLE)
            self.needs_frontier_reassign = True
            self.decision = (
                f"sync complete; requesting task ({synced_cells} cells, "
                f"{synced_survivors} survivors)"
            )

    def _switch_lost_comm_recovery(self, others: list, reservation_table=None,
                                   force_base: bool = False, reason: str = "lost comm recovery"):
        self.offline_autonomous_active = False
        self.offline_rtb_no_comms = True
        self._select_lost_comm_recovery_target(others, force_base)
        self._plan_lost_comm_recovery_path(others, reservation_table)
        self.decision = f"{reason} -> {self.lost_comm_recovery_label}"
        self.alerts.append(f"D{self.drone_id}: RTB NO COMMS - {self.lost_comm_recovery_label}")

    def _select_lost_comm_recovery_target(self, others: list, force_base: bool):
        if force_base:
            self.lost_comm_recovery_target = self.base_target_cell
            if self.battery.should_return() or not self.has_safe_return_energy():
                self.lost_comm_recovery_label = "base (battery)"
            else:
                self.lost_comm_recovery_label = "base (timeout)"
            return

        connected_peers = []
        for peer in others:
            if peer.drone_id == self.drone_id or peer.state in (FAILED, STRANDED):
                continue
            if peer.comm.is_connected and not peer.comm.is_lost:
                connected_peers.append((self.distance_to_px(peer.px, peer.py), peer))

        if connected_peers:
            _, peer = min(connected_peers, key=lambda item: item[0])
            self.lost_comm_recovery_target = peer.cell
            self.lost_comm_recovery_label = f"relay D{peer.drone_id}"
            return

        if self.last_comm_safe_cell is not None:
            self.lost_comm_recovery_target = self.last_comm_safe_cell
            self.lost_comm_recovery_label = "last safe comm"
            return

        self.lost_comm_recovery_target = self.base_target_cell
        self.lost_comm_recovery_label = "base"

    def _plan_lost_comm_recovery_path(self, others: list, reservation_table=None):
        if self.lost_comm_recovery_target is None:
            self.lost_comm_recovery_target = self.base_target_cell
            self.lost_comm_recovery_label = "base"
        col, row = self.lost_comm_recovery_target
        self.path.clear()
        self.plan_path_to(col, row, others, reservation_table)
        self.decision = f"lost comm recovery -> {self.lost_comm_recovery_label}"

    def _tick_offline_autonomous(self, frame: int, others: list, reservation_table=None):
        if not self._can_continue_offline_task():
            self._switch_lost_comm_recovery(
                others,
                reservation_table,
                True,
                "offline task unsafe",
            )
            return

        target_col, target_row = self.scan_queue[0]
        self.lost_comm_recovery_target = (target_col, target_row)
        self.lost_comm_recovery_label = "offline task"
        tc, tr = self.cell
        if tc == target_col and tr == target_row:
            self.scan_queue.pop(0)
            self.path.clear()
            self.decision = "offline scanned waypoint"
            return

        if not self.has_path():
            self.plan_path_to(target_col, target_row, others, reservation_table)

        self.decision = (
            f"offline autonomous scan q={len(self.scan_queue)} "
            f"rtb={self.estimate_return_energy(target_col, target_row):.0f}"
        )
        self._move_along_path()

    def _tick_lost_comm(self, frame: int, others: list, reservation_table=None):
        """Recover radio contact by moving toward a safe communication target."""
        if self.can_charge_here():
            self._dock()
            return

        self.lost_comm_frames += 1
        self._lost_comm_retarget_timer += 1
        force_base = (
            self.battery.should_return() or
            not self.has_safe_return_energy() or
            self.lost_comm_frames >= config.LOST_COMM_TIMEOUT_FRAMES
        )

        if self.offline_autonomous_active and not force_base:
            self._tick_offline_autonomous(frame, others, reservation_table)
            return

        if self.offline_autonomous_active and force_base:
            self._switch_lost_comm_recovery(
                others,
                reservation_table,
                True,
                "offline timeout/battery",
            )
            return

        if (self.lost_comm_recovery_target is None or
                self._lost_comm_retarget_timer >= config.LOST_COMM_RETARGET_INTERVAL or
                (force_base and self.lost_comm_recovery_target != self.base_target_cell)):
            self._lost_comm_retarget_timer = 0
            self._select_lost_comm_recovery_target(others, force_base)
            self._plan_lost_comm_recovery_path(others, reservation_table)

        if not self.has_path():
            self._select_lost_comm_recovery_target(others, True)
            self._plan_lost_comm_recovery_path(others, reservation_table)

        if (force_base or self.lost_comm_recovery_target == self.base_target_cell) and (
                self.distance_to_base() <= config.BASE_DOCKING_RADIUS_PX + config.PATH_WAYPOINT_DIST * 1.5):
            self.path.clear()
            self.target_cell = (config.BASE_COL, config.BASE_ROW)
            self.decision = "lost comm final docking approach"
            self._move_toward_base_center()
            return

        self._move_along_path()

    def _tick_avoiding(self, others: list):
        """Short detour; resume scanning once clear."""
        if self.has_path():
            self._move_along_path()
        else:
            self.set_state(SCANNING if self.scan_queue else RETURNING)

    def _tick_failed(self):
        """Count down failure timer and auto-recover."""
        self._stop()
        self._fail_timer += 1
        if self._fail_timer >= config.FAILURE_RECOVERY_FRAMES:
            self._fail_timer = 0
            self.set_state(RETURNING)
            self.alerts.append(f"D{self.drone_id}: RECOVERED — returning to base")

    # ──────────────────────────────────────────
    # Movement helpers
    # ──────────────────────────────────────────

    def _tick_stuck_recovery(self, frame: int, others: list, reservation_table=None):
        if self.state not in (SCANNING, RETURNING, LOST_COMM) or not self.has_path():
            self._stuck_frames = 0
            self._last_goal_distance = None
            return

        goal_col, goal_row = self.path[-1]
        gx, gy = self.game_map.cell_to_pixel(goal_col, goal_row)
        dist = math.hypot(self.px - gx, self.py - gy)
        if self._last_goal_distance is None or dist < self._last_goal_distance - config.STUCK_PROGRESS_EPS:
            self._stuck_frames = 0
            self._last_goal_distance = dist
            return

        self._stuck_frames += 1
        self._last_goal_distance = dist

        if self._stuck_frames == config.STUCK_WARN_FRAMES:
            self.decision = "slow progress; watching congestion"

        if self._stuck_frames == config.STUCK_REROUTE_FRAMES and self.target_cell is not None:
            target_col, target_row = self.target_cell
            self.path.clear()
            self.plan_path_to(target_col, target_row, others, reservation_table)
            self.decision = "stuck recovery reroute"
            self.stuck_recoveries += 1
            if frame - self._last_stuck_alert_frame > config.STUCK_REROUTE_FRAMES:
                self.alerts.append(f"D{self.drone_id}: rerouting around congestion")
                self._last_stuck_alert_frame = frame

        if self._stuck_frames >= config.STUCK_REASSIGN_FRAMES and self.state == SCANNING:
            self.scan_queue.clear()
            self.path.clear()
            self.current_frontier_id = None
            self.current_frontier_cell = None
            self.needs_frontier_reassign = True
            self.set_state(IDLE)
            self.decision = "stuck recovery requested new frontier"
            self.stuck_recoveries += 1
            self._stuck_frames = 0

    def _move_along_path(self):
        """Step toward the current waypoint."""
        wp = self.current_waypoint_px()
        if wp is None:
            self._stop()
            return

        wx, wy = wp
        dx = wx - self.px
        dy = wy - self.py
        dist = math.hypot(dx, dy)

        if dist < config.PATH_WAYPOINT_DIST:
            self.advance_waypoint()
            return

        # Speed selection
        col, row = self.cell
        speed = config.DRONE_SPEED_WIND if self.game_map.is_wind(col, row) else config.DRONE_SPEED

        nx = dx / dist * speed
        ny = dy / dist * speed
        self.vx, self.vy = nx, ny
        self.px += nx
        self.py += ny

    def _move_toward_base_center(self):
        """Final physical approach into the docking radius."""
        bx, by = self.base_px
        dx = bx - self.px
        dy = by - self.py
        dist = math.hypot(dx, dy)
        if dist <= 0.01:
            self._stop()
            return
        col, row = self.cell
        speed = config.DRONE_SPEED_WIND if self.game_map.is_wind(col, row) else config.DRONE_SPEED
        step = min(speed, dist)
        self.vx = dx / dist * step
        self.vy = dy / dist * step
        self.px += self.vx
        self.py += self.vy

    def _stop(self):
        self.vx = 0.0
        self.vy = 0.0

    def _dock(self):
        if not self.can_charge_here():
            self.battery.stop_charging()
            self.decision = f"charging denied; {self.distance_to_base()/config.CELL_SIZE:.1f}c from dock"
            if self.battery.is_empty():
                self._strand("0% away from docking zone")
            return False
        bx, by = self.base_px
        self.px, self.py = bx, by
        self.vx = self.vy = 0.0
        self.path.clear()
        self.current_frontier_id = None
        self.current_frontier_cell = None
        self.decision = "charging at base"
        self.battery.start_charging()
        self.set_state(CHARGING)
        return True

    def _initiate_return(self, others: list):
        if self.state == STRANDED:
            return
        if self.battery.is_empty():
            if self.can_charge_here():
                self._dock()
            else:
                self._strand("0% away from docking zone")
            return
        self.set_state(RETURNING)
        self.current_frontier_id = None
        self.current_frontier_cell = None
        self.decision = "battery/mission return to base"
        self.plan_path_to_base(others)

    def _strand(self, reason: str):
        was_stranded = self.state == STRANDED
        self.set_state(STRANDED)
        self._stop()
        self.battery.level = 0.0
        self.battery.stop_charging()
        self.path.clear()
        self.scan_queue.clear()
        self.current_frontier_id = None
        self.current_frontier_cell = None
        self.needs_frontier_reassign = False
        self.decision = reason
        if not was_stranded:
            self.alerts.append(f"D{self.drone_id}: STRANDED - {reason}")

    def _trigger_failure(self):
        self.set_state(FAILED)
        self._fail_timer = 0
        self._stop()
        self.battery.stop_charging()
        self.alerts.append(f"D{self.drone_id}: HARDWARE FAILURE!")

    # ──────────────────────────────────────────
    # Rendering
    # ──────────────────────────────────────────

    def draw(self, surf: pygame.Surface, show_sensor: bool = True,
             show_comm: bool = True, show_trail: bool = True, frame: int = 0):
        """Draw this drone onto a surface using map-relative pixel coords."""
        ix, iy = int(self.px), int(self.py)
        color  = STATE_COLOR.get(self.state, config.C_STATE_IDLE)

        speed = math.hypot(self.vx, self.vy)
        if self.state not in (FAILED, STRANDED, CHARGING) and speed > 0.05:
            glow_r = config.DRONE_RADIUS + 9 + int(3 * math.sin(frame * 0.18 + self.drone_id))
            glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*color, 45), (glow_r, glow_r), glow_r)
            surf.blit(glow, (ix - glow_r, iy - glow_r), special_flags=pygame.BLEND_ADD)

        # Trail
        if show_trail and len(self.trail) > 1:
            alpha_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            for i in range(1, len(self.trail)):
                a = int(185 * i / len(self.trail))
                tx0, ty0 = int(self.trail[i-1][0]), int(self.trail[i-1][1])
                tx1, ty1 = int(self.trail[i][0]),   int(self.trail[i][1])
                width = 2 if i > len(self.trail) * 0.7 else 1
                pygame.draw.line(alpha_surf, (*color, a), (tx0, ty0), (tx1, ty1), width)
            surf.blit(alpha_surf, (0, 0))

        # Planned path
        if self.has_path():
            pts = [self.game_map.cell_to_pixel(wc, wr)
                   for wc, wr in self.path[self.waypoint_idx:]]
            if len(pts) >= 2:
                pygame.draw.lines(surf, config.C_PATH, False, pts, 1)

        # Sensor range ring
        if show_sensor and self.state not in (CHARGING, FAILED, STRANDED):
            r_px = config.DRONE_SENSOR_RADIUS * config.CELL_SIZE
            pulse_t = (frame + self.drone_id * 11) % max(1, config.DRONE_SCAN_INTERVAL * 6)
            pulse_r = int(r_px * (0.35 + 0.65 * pulse_t / max(1, config.DRONE_SCAN_INTERVAL * 6)))
            s = pygame.Surface((r_px * 2 + 8, r_px * 2 + 8), pygame.SRCALPHA)
            center = (r_px + 4, r_px + 4)
            pygame.draw.circle(s, (*config.C_SENSOR_RING, 18), center, r_px)
            pygame.draw.circle(s, (*config.C_SENSOR_RING, 70), center, r_px, 1)
            pygame.draw.circle(s, (*config.C_SENSOR_RING, 110), center, pulse_r, 1)
            surf.blit(s, (ix - r_px - 4, iy - r_px - 4), special_flags=pygame.BLEND_ADD)

        # Drone body
        r = config.DRONE_RADIUS
        if self.state == FAILED:
            # Draw an X
            pygame.draw.line(surf, color, (ix - r, iy - r), (ix + r, iy + r), 2)
            pygame.draw.line(surf, color, (ix + r, iy - r), (ix - r, iy + r), 2)
        elif self.state == STRANDED:
            flash = pulse(frame, 45, 0.35, 1.0)
            warn = (int(255 * flash), 90, 20)
            pygame.draw.circle(surf, warn, (ix, iy), r + 3, 1)
            pygame.draw.circle(surf, color, (ix, iy), r)
            pygame.draw.line(surf, (255, 255, 255), (ix - r, iy), (ix + r, iy), 2)
        else:
            if self.battery.is_critical() and frame % 30 < 15:
                pygame.draw.circle(surf, config.C_UI_DANGER, (ix, iy), r + 5, 2)
            pygame.draw.circle(surf, color, (ix, iy), r)
            pygame.draw.circle(surf, (255, 255, 255), (ix, iy), r, 1)
            # Direction indicator (tiny line showing velocity)
            if speed > 0.1:
                ex = ix + int(self.vx / speed * (r + 4))
                ey = iy + int(self.vy / speed * (r + 4))
                pygame.draw.line(surf, (255, 255, 255), (ix, iy), (ex, ey), 1)

        # Drone ID label
        # (rendered by dashboard to avoid font imports here)

    def draw_comm_links(self, surf: pygame.Surface, all_drones: list, frame: int = 0):
        """Draw lines to directly connected peers."""
        for peer_id in self.comm.connected_ids:
            if isinstance(peer_id, int) and peer_id >= 0:
                for d in all_drones:
                    if d.drone_id == peer_id:
                        phase = (frame * 0.08 + self.drone_id * 0.7) % 1.0
                        alpha = 70 + int(45 * math.sin(frame * 0.12 + self.drone_id))
                        start = (int(self.px), int(self.py))
                        end = (int(d.px), int(d.py))
                        pygame.draw.line(surf, (*config.C_COMM_LINK, max(45, alpha)), start, end, 1)
                        px = int(start[0] + (end[0] - start[0]) * phase)
                        py = int(start[1] + (end[1] - start[1]) * phase)
                        pygame.draw.circle(surf, (*config.C_COMM_LINK, 150), (px, py), 2)
                        break

    def __repr__(self):
        return f"Drone(id={self.drone_id}, state={self.state}, bat={self.battery.level:.0f}%)"
