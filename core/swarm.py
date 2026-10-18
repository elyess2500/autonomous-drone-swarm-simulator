"""
core/swarm.py - Swarm intelligence coordinator.

Responsibilities
----------------
- Divide the map into sectors
- Assign drones to sectors intelligently
- Generate ordered scan queues for each sector
- Rebalance assignments when drones fail or return
- Track overall mission progress
"""

import math
import random
import numpy as np
from core.experiment import TICK_HZ, settings as config
from core.map import Map, CELL_OBSTACLE, CELL_NOFLY
from core.drone import Drone, IDLE, SCANNING, RETURNING, CHARGING, FAILED, STRANDED, LOST_COMM
from core.intelligence import FrontierMap, ReservationTable


class Sector:
    """
    A rectangular sub-region of the map.

    Attributes
    ----------
    idx : int
        Unique index.
    col_start, row_start : int
        Top-left grid cell (inclusive).
    col_end, row_end : int
        Bottom-right grid cell (exclusive).
    assigned_drone : int | None
        drone_id currently responsible for this sector.
    completed : bool
        True when all scannable cells have been covered.
    scan_cells : list[(col,row)]
        Ordered list of cells to scan (skips obstacles/no-fly).
    """

    def __init__(self, idx: int, col_start: int, row_start: int,
                 col_end: int, row_end: int):
        self.idx         = idx
        self.col_start   = col_start
        self.row_start   = row_start
        self.col_end     = col_end
        self.row_end     = row_end
        self.assigned_drone: int | None = None
        self.completed   = False
        self.scan_cells: list[tuple[int, int]] = []

    @property
    def centre(self) -> tuple[int, int]:
        return (
            (self.col_start + self.col_end) // 2,
            (self.row_start + self.row_end) // 2,
        )

    def build_scan_queue(self, game_map: Map):
        """
        Generate a boustrophedon (lawnmower) scan path covering all passable
        cells in the sector.
        """
        cells = []
        for r in range(self.row_start, self.row_end):
            row_cells = []
            for c in range(self.col_start, self.col_end):
                if game_map.is_passable(c, r):
                    row_cells.append((c, r))
            # Alternate direction each row for efficiency
            if r % 2 == 1:
                row_cells.reverse()
            cells.extend(row_cells)
        self.scan_cells = cells

    def is_fully_scanned(self, game_map: Map) -> bool:
        """Return True if all cells in sector are revealed."""
        for c, r in self.scan_cells:
            if not game_map.fog[r, c]:
                return False
        self.completed = True
        return True

    def __repr__(self):
        return (f"Sector({self.idx}, "
                f"cols={self.col_start}-{self.col_end}, "
                f"rows={self.row_start}-{self.row_end}, "
                f"drone={self.assigned_drone})")


class Swarm:
    """
    Top-level swarm controller.

    Call `update(frame)` each simulation frame.
    """

    def __init__(self, game_map: Map, num_drones: int = config.NUM_DRONES):
        from core.accounting import Accounting
        self.accounting = Accounting()
        self.game_map  = game_map
        self.drones: list[Drone] = []
        self.sectors: list[Sector] = []
        self._rebalance_timer = 0
        self._frontier_timer = 0
        self._negotiation_timer = 0
        self.alerts: list[str] = []   # accumulated alerts for dashboard
        self.frame_count = 0
        self.frontiers = FrontierMap()
        self.reservations = ReservationTable()
        self.negotiation_log: list[str] = []
        self.frontiers_assigned = 0
        self.frontiers_completed = 0
        # Authoritative live contract per drone; object fields are projections.
        self.assignments: dict[int, tuple[str, int]] = {}
        self.offline_assignments: set[int] = set()
        self.task_cancellations: dict[str, int] = {}
        self._last_coverage = 0.0
        self._coverage_stall_frames = 0
        self.coverage_stall_recoveries = 0
        self.emergency_recoveries = 0
        self.emergency_recovery_active = False
        self.comm_repair_events = 0
        self.full_comm_collapse_events = 0
        self.min_connected_count = num_drones
        self.last_comm_snapshot: dict = {}
        self._comm_repair_timer = 0
        self.comm_risk_relaxation = 0.0
        self.coverage_growth_per_min = 0.0
        self.average_frontier_distance = 0.0
        self.relay_drone_count = 0
        self.explorer_drone_count = 0
        self.offline_risk_assignments = 0
        self._coverage_samples: list[tuple[int, float]] = []
        self._relaxation_timer = 0

        self._init_drones(num_drones)
        self._init_sectors()
        self._initial_assignment()

    # ──────────────────────────────────────────
    # Initialisation
    # ──────────────────────────────────────────

    def _init_drones(self, n: int):
        for i in range(n):
            d = Drone(i, self.game_map)
            d._task_owner = self
            self.drones.append(d)

    def _init_sectors(self):
        """Divide the map into a SECTOR_ROWS × SECTOR_COLS grid of sectors."""
        rows_per = self.game_map.rows // config.SECTOR_ROWS
        cols_per = self.game_map.cols // config.SECTOR_COLS
        idx = 0
        for sr in range(config.SECTOR_ROWS):
            for sc in range(config.SECTOR_COLS):
                r0 = sr * rows_per
                c0 = sc * cols_per
                r1 = r0 + rows_per if sr < config.SECTOR_ROWS - 1 else self.game_map.rows
                c1 = c0 + cols_per if sc < config.SECTOR_COLS - 1 else self.game_map.cols
                sector = Sector(idx, c0, r0, c1, r1)
                sector.build_scan_queue(self.game_map)
                self.sectors.append(sector)
                idx += 1

    def _initial_assignment(self):
        """Start with frontier bids; keep sectors as a fallback."""
        self.frontiers.refresh(self.game_map)
        self._negotiate_frontiers(force=True)
        if not any(d.scan_queue for d in self.drones):
            available = [s for s in self.sectors if s.assigned_drone is None
                         and s.scan_cells]
            for i, drone in enumerate(self.drones):
                if i < len(available):
                    self._assign(drone, available[i])

    # ──────────────────────────────────────────
    # Assignment helpers
    # ──────────────────────────────────────────

    def _work_requires_offline(self, cells) -> bool:
        # Moving explorers cannot promise coverage for a whole task's lifetime.
        anchors = [(config.BASE_COL, config.BASE_ROW)] + [
            d.relay_anchor_cell for d in self.drones if d.relay_anchor_active and
            d.comm.is_connected and d.relay_anchor_cell is not None and
            d._at_cell_center(*d.relay_anchor_cell)
        ]
        safe_range = config.DRONE_COMM_RANGE / config.CELL_SIZE * config.COMM_RELAY_SAFE_RANGE
        return any(all(math.dist(cell, anchor) > safe_range for anchor in anchors) for cell in cells)

    def _can_claim_work(self, drone: Drone, cells) -> bool:
        return (not self._work_requires_offline(cells) or
                drone.drone_id in self.offline_assignments or
                len(self.offline_assignments) < config.COMM_MAX_OFFLINE_EXPLORERS)

    def _claim_assignment(self, drone: Drone, kind: str, task_id: int, work_cells=()):
        frontier = (next((f for f in self.frontiers.frontiers if f.frontier_id == task_id), None)
                    if kind == "frontier" else None)
        sector = self._get_sector(task_id) if kind == "sector" else None
        if not (frontier is not None or sector is not None or
                (kind == "relay" and task_id == drone.drone_id)):
            raise ValueError(f"unknown task {(kind, task_id)}")
        task = (kind, task_id)
        if any(owner != drone.drone_id and claim == task
               for owner, claim in self.assignments.items()):
            raise ValueError(f"task {task} already owned")
        if kind != "relay" and drone.relay_anchor_active:
            raise ValueError("relay already owned by its relay contract")
        if self.assignments.get(drone.drone_id) == task:
            return
        requires_offline = kind != "relay" and self._work_requires_offline(work_cells)
        if requires_offline and not self._can_claim_work(drone, work_cells):
            raise ValueError("offline exploration capacity already owned")
        self._release_assignment(drone, f"replace with {kind}")
        self.assignments[drone.drone_id] = task
        self.accounting.emit("task_awarded", drone.drone_id, f"{kind}:{task_id}", kind)
        if requires_offline:
            self.offline_assignments.add(drone.drone_id)
        if kind == "frontier":
            frontier.assigned_drone = drone.drone_id
            drone.current_frontier_id = task_id
            drone.current_frontier_cell = frontier.cell
        elif kind == "sector":
            sector.assigned_drone = drone.drone_id
            drone.assigned_sector = task_id
        drone.needs_frontier_reassign = False

    def _release_assignment(self, drone: Drone, reason: str, completed: bool = False):
        task = self.assignments.pop(drone.drone_id, None)
        self.offline_assignments.discard(drone.drone_id)
        if task is not None:
            kind, task_id = task
            self.accounting.emit("task_completed" if completed else "task_cancelled",
                                 drone.drone_id, f"{kind}:{task_id}", reason)
            if completed and kind == "frontier":
                self.frontiers_completed += 1
            elif completed and kind == "sector":
                self._get_sector(task_id).is_fully_scanned(self.game_map)
            elif not completed:
                self.task_cancellations[reason] = self.task_cancellations.get(reason, 0) + 1
        self.frontiers.release_drone(drone.drone_id)
        if completed and task is not None and task[0] == "frontier":
            self.frontiers.frontiers = [f for f in self.frontiers.frontiers if f.frontier_id != task[1]]
        for sector in self.sectors:
            if sector.assigned_drone == drone.drone_id:
                sector.assigned_drone = None
        drone.current_frontier_id = drone.current_frontier_cell = None
        drone.assigned_sector = drone.completed_frontier_id = None
        drone.scan_queue.clear()
        drone.path.clear()
        drone.waypoint_idx = 0
        drone._stuck_frames = 0
        drone._last_progress_position = None
        drone.relay_anchor_active = False
        drone.relay_anchor_cell = None
        drone.relay_anchor_until = 0
        drone.comm_role = "explorer"

    def _complete_assignment(self, drone: Drone):
        if drone.relay_anchor_active:
            return  # Holding at an anchor is ongoing work.
        self._release_assignment(drone, "completed", completed=True)
        drone.needs_frontier_reassign = True

    def _assign(self, drone: Drone, sector: Sector):
        """Assign a sector to a drone and build its scan queue."""
        if (drone.relay_anchor_active or drone.scan_queue or
                drone.state not in (IDLE, SCANNING) or
                sector.assigned_drone not in (None, drone.drone_id)):
            return

        # Build remaining scan queue (skip already-scanned cells)
        remaining = [
            (c, r) for c, r in sector.scan_cells
            if not self.game_map.fog[r, c]
        ]
        if not remaining:
            # Already scanned; pick next available sector
            sector.completed = True
            sector.assigned_drone = None
            drone.assigned_sector = None
            self._assign_nearest_sector(drone)
            return

        if not self._can_claim_work(drone, remaining):
            drone.decision = "waiting for offline exploration capacity"
            return

        personalized = self._personalize_scan_queue(drone, remaining)
        first_target = personalized[0]
        if (not drone.can_accept_task(first_target[0], first_target[1]) or
                not self._can_maintain_comm_to_cell(drone, first_target[0], first_target[1])):
            sector.assigned_drone = None
            drone.assigned_sector = None
            comm_risk = self._comm_risk_for_cell(drone, first_target[0], first_target[1])
            drone.decision = (
                f"sector deferred; {drone.task_energy_reason(first_target[0], first_target[1])} "
                f"comm risk {comm_risk:.1f}"
            )
            if drone.is_at_base():
                drone._dock()
            else:
                drone._initiate_return(self.drones)
            return

        comm_risk = self._comm_risk_for_cell(drone, first_target[0], first_target[1])
        planned = drone.prepare_energy_route(first_target, self.drones, self.reservations)
        if planned is None:
            drone.decision = "sector deferred; energy or route unavailable"
            return
        self._claim_assignment(drone, "sector", sector.idx, remaining)
        drone.comm_risk_score = comm_risk
        drone.comm_path_risk_weight = self._comm_path_weight_for(drone, comm_risk)
        drone.scan_queue = personalized
        drone.set_state_from_swarm = True  # flag consumed by drone
        drone.set_state(SCANNING)
        drone.path = planned
        drone.waypoint_idx = 0
        drone.target_cell = first_target

    def _assign_nearest_sector(self, drone: Drone):
        """Find the closest unassigned, incomplete sector and assign it."""
        if drone.relay_anchor_active or drone.scan_queue or drone.state not in (IDLE, SCANNING):
            return
        candidates = [
            s for s in self.sectors
            if s.assigned_drone is None and not s.completed and s.scan_cells
        ]
        def energy_feasible(sector):
            work = self._personalize_scan_queue(drone, [cell for cell in sector.scan_cells
                if not self.game_map.fog[cell[1], cell[0]]])
            return bool(work) and drone.can_accept_task(*work[0])
        candidates = [
            s for s in candidates
            if energy_feasible(s) and
            self._can_maintain_comm_to_cell(drone, s.centre[0], s.centre[1]) and
            self._can_claim_work(drone, [(c, r) for c, r in s.scan_cells if not self.game_map.fog[r, c]])
        ]
        if not candidates:
            # All sectors done/covered or too expensive for current battery.
            from core.drone import RETURNING
            if drone.is_at_base():
                drone._dock()
            else:
                drone.set_state(RETURNING)
                drone.decision = "sector too far; recharge first"
                drone.plan_path_to_base(self.drones)
            return

        dc, dr = drone.cell
        def score(s):
            sc, sr = s.centre
            travel = math.hypot(dc - sc, dr - sr)
            expansion = math.hypot(sc - config.BASE_COL, sr - config.BASE_ROW)
            comm_risk = self._comm_risk_for_cell(drone, sc, sr)
            spread = self._frontier_spread_penalty((sc, sr)) * 0.35
            return travel * 0.55 + comm_risk * 0.8 + spread - expansion * 0.7

        nearest = min(candidates, key=score)
        self._assign(drone, nearest)

    def _personalize_scan_queue(self, drone: Drone, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Preserve sector coverage while giving each drone a distinct route."""
        queue = list(cells)
        if len(queue) < 4 or config.AI_RANDOMNESS <= 0:
            return queue

        rng = random.Random(drone.ai_seed + (drone.assigned_sector or 0) * 131)

        if rng.random() < config.AI_RANDOMNESS * 0.55:
            queue.reverse()

        max_rotation = max(1, int(len(queue) * 0.18 * config.AI_RANDOMNESS))
        rotation = (drone.drone_id * max(1, max_rotation // max(1, len(self.drones))) +
                    rng.randint(0, max_rotation)) % len(queue)
        queue = queue[rotation:] + queue[:rotation]

        # Occasionally reverse short row bands; this breaks up identical
        # lawnmower corridors while retaining the sector's full cell set.
        band = max(6, int(18 - 8 * config.AI_RANDOMNESS))
        varied: list[tuple[int, int]] = []
        for i in range(0, len(queue), band):
            chunk = queue[i:i + band]
            if rng.random() < config.AI_RANDOMNESS * 0.35:
                chunk.reverse()
            varied.extend(chunk)
        return varied

    def _relay_anchor_count(self) -> int:
        active = [d for d in self.drones if d.state not in (FAILED, STRANDED)]
        if not active:
            return 0
        connected_ratio = self.last_comm_snapshot.get("connected_ratio", 1.0)
        weak_count = len(self.last_comm_snapshot.get("weak", []))
        base_count = max(config.COMM_MIN_RELAY_ANCHORS, round(len(active) * config.COMM_RELAY_FRACTION))
        if connected_ratio < config.COMM_MIN_CONNECTED_RATIO or weak_count >= 2:
            base_count += 1
        if connected_ratio < 0.45:
            base_count += 1
        if self.comm_risk_relaxation > 0.45 and connected_ratio >= config.COMM_MIN_CONNECTED_RATIO:
            base_count -= 1
        return min(
            max(config.COMM_MIN_RELAY_ANCHORS, int(base_count)),
            getattr(config, "COMM_MAX_RELAY_ANCHORS", 3),
            max(0, len(active) - 1),
        )

    def _explorer_drones(self) -> list[Drone]:
        return [
            d for d in self.drones
            if d.state not in (FAILED, STRANDED, RETURNING, CHARGING) and
            not d.relay_anchor_active
        ]

    def _role_counts(self) -> tuple[int, int]:
        relays = sum(1 for d in self.drones if d.comm_role == "relay" and d.relay_anchor_active)
        explorers = sum(
            1 for d in self.drones
            if d.comm_role != "relay" and d.state not in (FAILED, STRANDED, CHARGING, RETURNING)
        )
        return relays, explorers

    def _comm_anchor_cells(self) -> list[tuple[int, int]]:
        anchors = [(config.BASE_COL, config.BASE_ROW)]
        for drone in self.drones:
            if drone.state in (FAILED, STRANDED):
                continue
            if drone.relay_anchor_active or drone.comm.is_connected:
                anchors.append(drone.cell)
        return anchors

    def _comm_risk_for_cell(self, drone: Drone, col: int, row: int) -> float:
        safe_cells = (config.DRONE_COMM_RANGE / config.CELL_SIZE) * config.COMM_RELAY_SAFE_RANGE
        anchors = self._comm_anchor_cells()
        nearest_anchor = min(math.hypot(col - ac, row - ar) for ac, ar in anchors)
        local_gap = max(0.0, nearest_anchor - safe_cells)

        base_dist = math.hypot(col - config.BASE_COL, row - config.BASE_ROW)
        relay_budget = self._relay_anchor_count() + 1
        max_supported = safe_cells * relay_budget
        chain_gap = max(0.0, base_dist - max_supported)

        connected_ratio = self.last_comm_snapshot.get("connected_ratio", 1.0)
        degraded = max(0.0, config.COMM_MIN_CONNECTED_RATIO - connected_ratio) * 7.0
        relay_bonus = -2.0 if drone.comm_role == "relay" else 0.0
        return max(0.0, max(local_gap, chain_gap) + degraded + relay_bonus)

    def _can_maintain_comm_to_cell(self, drone: Drone, col: int, row: int) -> bool:
        return self._comm_risk_for_cell(drone, col, row) <= self._comm_risk_limit(drone, col, row)

    def _comm_risk_limit(self, drone: Drone, col: int | None = None, row: int | None = None) -> float:
        limit = config.COMM_FRONTIER_MAX_RISK + self.comm_risk_relaxation * config.COMM_RELAXATION_RISK_BONUS
        if (drone.comm_role != "relay" and getattr(config, "AUTONOMOUS_OFFLINE_MODE", False) and
                col is not None and row is not None and drone.can_accept_task(col, row)):
            limit += config.COMM_EXPLORER_OFFLINE_RISK_BONUS
        return limit

    def _comm_path_weight_for(self, drone: Drone, comm_risk: float = 0.0) -> float:
        if drone.comm_role == "relay":
            return config.COMM_PATH_RISK_WEIGHT
        relaxed = max(0.0, 1.0 - self.comm_risk_relaxation * 0.65)
        risk_softening = 0.65 if comm_risk <= config.COMM_FRONTIER_MAX_RISK else 0.45
        return config.COMM_PATH_RISK_WEIGHT * relaxed * risk_softening

    def _direction_preference_bonus(self, drone: Drone, col: int, row: int) -> float:
        explorers = max(1, len(self._explorer_drones()))
        angle = math.atan2(row - config.BASE_ROW, col - config.BASE_COL)
        desired = ((drone.drone_id % explorers) / explorers) * math.tau
        delta = math.atan2(math.sin(angle - desired), math.cos(angle - desired))
        return math.cos(delta) * config.FRONTIER_DIRECTION_WEIGHT

    def _frontier_spread_penalty(self, cell: tuple[int, int],
                                 claimed_cells: list[tuple[int, int]] | None = None,
                                 include_existing: bool = True) -> float:
        cells: list[tuple[int, int]] = list(claimed_cells or [])
        if include_existing:
            for peer in self.drones:
                if peer.current_frontier_cell is not None:
                    cells.append(peer.current_frontier_cell)
                elif peer.scan_queue:
                    cells.append(peer.scan_queue[0])
        penalty = 0.0
        for pc, pr in cells:
            dist = math.hypot(cell[0] - pc, cell[1] - pr)
            if dist < config.FRONTIER_SPREAD_RADIUS:
                penalty += (config.FRONTIER_SPREAD_RADIUS - dist) * config.FRONTIER_SPREAD_PENALTY
        return penalty

    def _frontier_expansion_bonus(self, frontier) -> float:
        base_dist = math.hypot(frontier.col - config.BASE_COL, frontier.row - config.BASE_ROW)
        return base_dist * config.FRONTIER_EXPANSION_WEIGHT

    def _nearest_passable_cell(self, col: int, row: int, radius: int = 6) -> tuple[int, int]:
        if self.game_map.is_passable(col, row):
            return col, row
        best = None
        best_dist = 10**9
        for rr in range(max(0, row - radius), min(self.game_map.rows, row + radius + 1)):
            for cc in range(max(0, col - radius), min(self.game_map.cols, col + radius + 1)):
                if not self.game_map.is_passable(cc, rr):
                    continue
                dist = abs(cc - col) + abs(rr - row)
                if dist < best_dist:
                    best = (cc, rr)
                    best_dist = dist
        return best if best is not None else (config.BASE_COL, config.BASE_ROW)

    def _farthest_active_goal(self) -> tuple[int, int]:
        goals: list[tuple[int, int]] = []
        for drone in self.drones:
            if drone.state in (FAILED, STRANDED, CHARGING):
                continue
            if drone.current_frontier_cell is not None:
                goals.append(drone.current_frontier_cell)
            elif drone.scan_queue:
                goals.append(drone.scan_queue[0])
            elif drone.target_cell is not None:
                goals.append(drone.target_cell)
        if not goals and self.frontiers.frontiers:
            goals = [frontier.cell for frontier in self.frontiers.frontiers[:8]]
        if not goals:
            return config.BASE_COL, config.BASE_ROW
        return max(
            goals,
            key=lambda cell: math.hypot(cell[0] - config.BASE_COL, cell[1] - config.BASE_ROW),
        )

    def _relay_anchor_targets(self) -> list[tuple[int, int]]:
        count = self._relay_anchor_count()
        if count <= 0:
            return []
        goal_col, goal_row = self._farthest_active_goal()
        dx = goal_col - config.BASE_COL
        dy = goal_row - config.BASE_ROW
        dist = math.hypot(dx, dy)
        if dist < 1:
            return []

        safe_step = (config.DRONE_COMM_RANGE / config.CELL_SIZE) * config.COMM_RELAY_SAFE_RANGE
        targets = []
        for idx in range(count):
            along = min(dist, safe_step * (idx + 1))
            if along >= dist:
                along = dist * (idx + 1) / (count + 1)
            t = along / dist
            col = int(round(config.BASE_COL + dx * t))
            row = int(round(config.BASE_ROW + dy * t))
            targets.append(self._nearest_passable_cell(col, row, radius=8))
        return targets

    def _assign_relay_roles(self, frame: int):
        candidates = [
            d for d in self.drones
            if d.state not in (FAILED, STRANDED, CHARGING, RETURNING, LOST_COMM) and
            not d.battery.should_return()
        ]
        relay_count = min(self._relay_anchor_count(), len(candidates))
        targets = self._relay_anchor_targets()
        # A minimum hold is not an expiry: keep productive connected anchors.
        # Release excess roles after the hold, or retarget a disconnected one.
        assignments = {}
        for drone in sorted(self.drones, key=lambda d: (d.distance_to_base(), d.drone_id)):
            if (drone.relay_anchor_active and drone.relay_anchor_cell is not None and
                    (drone in candidates or drone.state == LOST_COMM) and
                    (frame < drone.relay_anchor_until or drone.state == LOST_COMM or
                     (drone.comm.is_connected and len(assignments) < relay_count))):
                assignments[drone.drone_id] = drone.relay_anchor_cell
        remaining = [d for d in candidates if d.drone_id not in assignments]
        pending_targets = list(targets)
        for anchor in assignments.values():
            if pending_targets:
                occupied_target = min(pending_targets, key=lambda cell: math.dist(cell, anchor))
                pending_targets.remove(occupied_target)

        for target in pending_targets[:max(0, relay_count - len(assignments))]:
            if not remaining:
                break
            target = self._connected_relay_target(target)
            affordable = [d for d in remaining if d.can_accept_task(
                *target, hold_ticks=config.COMM_RELAY_ANCHOR_HOLD_FRAMES)]
            if not affordable:
                continue
            best = min(
                affordable,
                key=lambda d: (
                    math.hypot(d.cell[0] - target[0], d.cell[1] - target[1]) -
                    (4.0 if d.comm_role == "relay" else 0.0) -
                    d.battery.pct * 3.0,
                    d.drone_id,
                ),
            )
            assignments[best.drone_id] = target
            remaining.remove(best)

        if len(assignments) < relay_count:
            remaining.sort(key=lambda d: (
                d.comm_role != "relay",
                -d.battery.level,
                d.drone_id,
            ))
            for drone in remaining[:relay_count - len(assignments)]:
                target = self._connected_relay_target(drone.cell)
                if drone.can_accept_task(*target, hold_ticks=config.COMM_RELAY_ANCHOR_HOLD_FRAMES):
                    assignments[drone.drone_id] = target
        relays = set(assignments)

        for drone in self.drones:
            if drone.drone_id not in relays:
                if drone.relay_anchor_active:
                    self._release_assignment(drone, "relay lease ended")
                    if drone.state in (SCANNING, IDLE):
                        drone.set_state(IDLE)
                        drone.needs_frontier_reassign = True
                drone.comm_role = "explorer"
                drone.comm_path_risk_weight = self._comm_path_weight_for(drone, drone.comm_risk_score)
                if frame >= drone.relay_anchor_until:
                    drone.relay_anchor_active = False
                    drone.relay_anchor_cell = None
                continue

            target = assignments.get(drone.drone_id, drone.cell)
            new_role = not drone.relay_anchor_active
            if new_role:
                planned = drone.prepare_energy_route(target, self.drones, self.reservations,
                    hold_ticks=config.COMM_RELAY_ANCHOR_HOLD_FRAMES)
                if planned is None:
                    continue
            self._claim_assignment(drone, "relay", drone.drone_id)
            drone.comm_role = "relay"
            drone.comm_path_risk_weight = config.COMM_PATH_RISK_WEIGHT
            drone.relay_anchor_cell = target
            drone.relay_anchor_active = True
            if new_role:
                drone.scan_queue = [target]
                drone.set_state(SCANNING)
                drone.path = planned
                drone.waypoint_idx = 0
                drone.target_cell = target
            if frame >= drone.relay_anchor_until:
                drone.relay_anchor_until = frame + config.COMM_RELAY_ANCHOR_HOLD_FRAMES
            drone.relay_reason = "relay anchor"

    def _connected_relay_target(self, target):
        """A new anchor must attach to base or an already holding connected relay."""
        anchors = [(config.BASE_COL, config.BASE_ROW)] + [
            d.relay_anchor_cell for d in self.drones if d.relay_anchor_active and
            d.comm.is_connected and d.relay_anchor_cell is not None and
            d._at_cell_center(*d.relay_anchor_cell)
        ]
        safe_range = config.DRONE_COMM_RANGE / config.CELL_SIZE * config.COMM_RELAY_SAFE_RANGE
        anchor = min(anchors, key=lambda cell: math.dist(cell, target))
        distance = math.dist(anchor, target)
        if distance <= safe_range and self.game_map.is_passable(*target):
            return target
        fraction = min(1.0, safe_range / max(1.0, distance))
        col, row = (round(a + (b-a)*fraction) for a, b in zip(anchor, target))
        # Terrain fallback must preserve radio validity as well as passability.
        candidates = [(c, r) for r in range(max(0, row-8), min(self.game_map.rows, row+9))
                      for c in range(max(0, col-8), min(self.game_map.cols, col+9))
                      if self.game_map.is_passable(c, r) and math.dist((c, r), anchor) <= safe_range]
        return min(candidates, key=lambda cell: math.dist(cell, target), default=anchor)

    def _maintain_relay_anchors(self, frame: int):
        self._assign_relay_roles(frame)
        for drone in self.drones:
            if not drone.relay_anchor_active or drone.relay_anchor_cell is None:
                continue
            if drone.state in (FAILED, STRANDED, CHARGING, RETURNING, LOST_COMM):
                continue
            if drone.battery.should_return() or not drone.has_safe_return_energy(*drone.relay_anchor_cell):
                drone._energy_return(self.drones)
                continue
            if not drone._at_cell_center(*drone.relay_anchor_cell):
                if not drone.scan_queue or drone.scan_queue[0] != drone.relay_anchor_cell:
                    drone.scan_queue = [drone.relay_anchor_cell]
                    drone.current_frontier_id = None
                    drone.current_frontier_cell = None
                    drone.path.clear()
                    drone.set_state(SCANNING)
                    drone.plan_path_to(*drone.relay_anchor_cell, self.drones, self.reservations)
                drone.decision = f"moving to relay anchor {drone.relay_anchor_cell}"
            else:
                drone.scan_queue.clear()
                drone.path.clear()
                drone.set_state(IDLE)
                drone.decision = "relay anchor holding"

    def _nearest_comm_safe_cell(self, drone: Drone) -> tuple[int, int]:
        anchors = self._comm_anchor_cells()
        safe_cells = (config.DRONE_COMM_RANGE / config.CELL_SIZE) * config.COMM_RELAY_SAFE_RANGE
        dc, dr = drone.cell
        best = min(anchors, key=lambda cell: math.hypot(dc - cell[0], dr - cell[1]))
        if math.hypot(dc - best[0], dr - best[1]) <= safe_cells:
            return drone.cell
        return self._nearest_passable_cell(best[0], best[1], radius=5)

    def _repair_comm_mesh(self, frame: int):
        self._comm_repair_timer += 1
        snapshot = self.last_comm_snapshot
        connected = snapshot.get("connected", len(self.drones))
        total = max(1, snapshot.get("total", len(self.drones)))
        ratio = connected / total
        self.min_connected_count = min(self.min_connected_count, connected)
        if connected == 0:
            self.full_comm_collapse_events += 1

        if self._comm_repair_timer < config.COMM_MESH_REPAIR_INTERVAL:
            return
        self._comm_repair_timer = 0

        weak_ids = set(snapshot.get("weak", []))
        if ratio >= config.COMM_MIN_CONNECTED_RATIO and not weak_ids:
            return

        self.comm_repair_events += 1
        self._assign_relay_roles(frame)
        self.alerts.append("Swarm: repairing weak communication mesh")

        for drone in self.drones:
            if drone.state in (FAILED, STRANDED, CHARGING, RETURNING, LOST_COMM):
                continue
            if drone.relay_anchor_active:
                continue
            if drone.drone_id not in weak_ids and ratio >= config.COMM_MIN_CONNECTED_RATIO:
                continue
            target = drone.last_comm_safe_cell or self._nearest_comm_safe_cell(drone)
            if not self.game_map.is_passable(*target):
                target = self._nearest_comm_safe_cell(drone)
            if drone.cell == target:
                continue
            # A safety detour keeps the original contract and its remaining work.
            drone.scan_queue = [target] + [c for c in drone.scan_queue if c != target]
            drone.path.clear()
            drone.set_state(SCANNING)
            drone.plan_path_to(*target, self.drones, self.reservations)
            drone.decision = f"mesh repair toward {target}"

    def _update_exploration_balance(self, frame: int, record_sample: bool = True):
        coverage = self.game_map.exploration_pct()
        if record_sample:
            self._coverage_samples.append((frame, coverage))
            cutoff = frame - TICK_HZ * 60
            while len(self._coverage_samples) > 2 and self._coverage_samples[0][0] < cutoff:
                self._coverage_samples.pop(0)

            if len(self._coverage_samples) >= 2:
                start_frame, start_cov = self._coverage_samples[0]
                elapsed_min = max(1.0 / 60.0, (frame - start_frame) / TICK_HZ / 60.0)
                self.coverage_growth_per_min = max(0.0, (coverage - start_cov) / elapsed_min)
            else:
                self.coverage_growth_per_min = 0.0

            self._relaxation_timer += 1
            if self._relaxation_timer >= TICK_HZ:
                self._relaxation_timer = 0
                enough_history = frame >= TICK_HZ * 30
                stalled = self._coverage_stall_frames >= config.COMM_RELAXATION_START_FRAMES
                slow_growth = (
                    enough_history and
                    self.coverage_growth_per_min < config.EXPLORATION_MIN_GROWTH_PER_MIN
                )
                if stalled or slow_growth:
                    self.comm_risk_relaxation = min(
                        1.0,
                        self.comm_risk_relaxation + config.COMM_RELAXATION_STEP,
                    )
                else:
                    self.comm_risk_relaxation = max(
                        0.0,
                        self.comm_risk_relaxation - config.COMM_RELAXATION_DECAY,
                    )

        relays, explorers = self._role_counts()
        self.relay_drone_count = relays
        self.explorer_drone_count = explorers
        assigned = [
            d.current_frontier_cell or (d.scan_queue[0] if d.scan_queue else None)
            for d in self.drones
            if d.state not in (FAILED, STRANDED, CHARGING)
        ]
        assigned = [cell for cell in assigned if cell is not None]
        if assigned:
            self.average_frontier_distance = sum(
                math.hypot(cell[0] - config.BASE_COL, cell[1] - config.BASE_ROW)
                for cell in assigned
            ) / len(assigned)
        else:
            self.average_frontier_distance = 0.0

    def comm_debug_metrics(self) -> dict:
        return {
            "relay_drones": self.relay_drone_count,
            "explorer_drones": self.explorer_drone_count,
            "avg_frontier_distance": self.average_frontier_distance,
            "coverage_growth_per_min": self.coverage_growth_per_min,
            "comm_risk_relaxation": self.comm_risk_relaxation,
            "offline_risk_assignments": self.offline_risk_assignments,
        }

    def _negotiate_frontiers(self, force: bool = False):
        """Run negotiation now; force never authorizes preemption of live work."""
        if not self.frontiers.frontiers:
            return

        bidders = [
            d for d in self.drones
            if d.state not in (FAILED, STRANDED, RETURNING, CHARGING, LOST_COMM) and
            not d.relay_anchor_active and
            not d.battery.should_return() and
            not d.scan_queue and d.drone_id not in self.assignments
        ]
        if not bidders:
            return

        bids: list[tuple[float, int, float, object, Drone, bool]] = []
        drones_with_affordable_bid: set[int] = set()
        for drone in bidders:
            for frontier in self.frontiers.available():
                bid = drone.evaluate_frontier_bid(frontier, self.drones)
                if bid is not None and bid >= config.FRONTIER_MIN_BID:
                    drones_with_affordable_bid.add(drone.drone_id)
                    comm_risk = self._comm_risk_for_cell(drone, frontier.col, frontier.row)
                    drone.comm_risk_score = comm_risk
                    risk_limit = self._comm_risk_limit(drone, frontier.col, frontier.row)
                    if comm_risk > risk_limit:
                        drone.decision = f"frontier too comm-risky {comm_risk:.1f}"
                        continue
                    offline_risk = comm_risk > config.COMM_FRONTIER_MAX_RISK
                    risk_weight = config.COMM_FRONTIER_RISK_WEIGHT * max(0.25, 1.0 - self.comm_risk_relaxation * 0.7)
                    if drone.comm_role != "relay":
                        risk_weight *= 0.65
                    adjusted_bid = (
                        bid
                        + self._frontier_expansion_bonus(frontier)
                        + self._direction_preference_bonus(drone, frontier.col, frontier.row)
                        - self._frontier_spread_penalty(frontier.cell) * 0.35
                        - comm_risk * risk_weight
                    )
                    if adjusted_bid < config.FRONTIER_MIN_BID:
                        continue
                    bids.append((adjusted_bid, frontier.info_gain, comm_risk, frontier, drone, offline_risk))

        bids.sort(key=lambda item: (item[0], item[1]), reverse=True)
        claimed_frontiers: set[int] = set()
        claimed_drones: set[int] = set()
        claimed_cells: list[tuple[int, int]] = []
        offline_risk_claims = 0

        for enforce_spread in (True, False):
            for bid, _, comm_risk, frontier, drone, offline_risk in bids:
                if frontier.frontier_id in claimed_frontiers or drone.drone_id in claimed_drones:
                    continue
                if offline_risk and offline_risk_claims >= config.COMM_MAX_OFFLINE_EXPLORERS:
                    continue
                if enforce_spread and self._frontier_spread_penalty(frontier.cell, claimed_cells, include_existing=False) > 0:
                    continue
                drone.comm_risk_score = comm_risk
                drone.comm_path_risk_weight = self._comm_path_weight_for(drone, comm_risk)
                work_cells = self._frontier_work_cells(frontier, drone)
                if not self._can_claim_work(drone, work_cells):
                    continue
                if drone.accept_frontier_task(frontier, work_cells, self.drones, self.reservations) is False:
                    continue
                frontier.winning_bid = bid
                self.frontiers_assigned += 1
                claimed_frontiers.add(frontier.frontier_id)
                claimed_drones.add(drone.drone_id)
                claimed_cells.append(frontier.cell)
                if offline_risk:
                    offline_risk_claims += 1
                mode = " offline-capable" if offline_risk else ""
                msg = f"D{drone.drone_id} won F{frontier.frontier_id} bid {bid:.1f} risk {comm_risk:.1f}{mode}"
                self.negotiation_log.append(msg)
                drone.decision = msg

        for drone in bidders:
            if drone.drone_id in claimed_drones:
                continue
            if drone.drone_id not in drones_with_affordable_bid and self.frontiers.available():
                drone.decision = "all frontiers too far; recharge first"
                if drone.is_at_base():
                    drone._dock()
                else:
                    drone._initiate_return(self.drones)
            elif self.frontiers.available():
                drone.decision = "waiting for spread frontier"

        self.offline_risk_assignments += offline_risk_claims
        if len(self.negotiation_log) > 10:
            self.negotiation_log = self.negotiation_log[-10:]

    def _frontier_work_cells(self, frontier, drone: Drone) -> list[tuple[int, int]]:
        """Build a compact local scan packet around a won frontier."""
        cells = []
        radius = config.FRONTIER_INFO_RADIUS
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                col, row = frontier.col + dc, frontier.row + dr
                if not self.game_map.in_bounds(col, row) or not self.game_map.is_passable(col, row):
                    continue
                if dc * dc + dr * dr > radius * radius:
                    continue
                if not self.game_map.fog[row, col] or (col, row) == frontier.cell:
                    cells.append((col, row))

        dc, dr = drone.cell
        rng = random.Random(drone.ai_seed + frontier.frontier_id)
        cells.sort(key=lambda cell: (
            self.game_map.fog[cell[1], cell[0]],
            math.hypot(cell[0] - dc, cell[1] - dr),
            rng.random(),
        ))
        return cells[:config.FRONTIER_WORK_CELL_LIMIT] or [frontier.cell]

    def _get_sector(self, idx: int) -> Sector | None:
        for s in self.sectors:
            if s.idx == idx:
                return s
        return None

    # ──────────────────────────────────────────
    # Main update
    # ──────────────────────────────────────────

    def update(self, frame: int, weather: str):
        self.frame_count = frame
        self.accounting.tick = frame
        for drone in self.drones:
            drone._energy_weather = weather

        # 1. Update communication graph
        from core.communication import CommManager
        if not hasattr(self, '_comm_manager'):
            self._comm_manager = CommManager()
        self._comm_manager.update(self.drones)
        self.last_comm_snapshot = self._comm_manager.connectivity_snapshot(self.drones)
        self._update_exploration_balance(frame)
        self._maintain_relay_anchors(frame)
        self._repair_comm_mesh(frame)
        self._update_exploration_balance(frame, record_sample=False)

        if frame % config.COMM_SYNC_INTERVAL == 0:
            self._comm_manager.broadcast(self.drones)

        self._frontier_timer += 1
        if self._frontier_timer >= config.FRONTIER_REFRESH_INTERVAL:
            self._frontier_timer = 0
            self.frontiers.refresh(self.game_map)

        self._negotiation_timer += 1
        if self._negotiation_timer >= config.TASK_NEGOTIATION_INTERVAL:
            self._negotiation_timer = 0
            self._negotiate_frontiers()

        if any(d.needs_frontier_reassign for d in self.drones):
            self._negotiate_frontiers(force=True)

        self.reservations.rebuild(self.drones, start_tick=frame-1)
        self.reservations.begin_tick(frame, self.drones)

        # 2. Update each drone
        for drone in sorted(self.drones, key=self.reservations.priority_key):
            drone.update(frame, weather, self.drones, self.reservations, defer_sensing=True)
            if drone.state == SCANNING and not drone.scan_queue:
                drone._complete_task()
                drone.set_state(IDLE)
            # Collect drone alerts
            if drone.alerts:
                self.alerts.extend(drone.alerts)
                drone.alerts.clear()

        # Motion can break/restore a radio path within this tick. Deliver and
        # sense only after refreshing geometry; do not tick timeout counters twice.
        self._comm_manager.update(self.drones, advance_counters=False)
        self.last_comm_snapshot = self._comm_manager.connectivity_snapshot(self.drones)
        for drone in sorted(self.drones, key=self.reservations.priority_key):
            drone._sync_offline_discoveries()
            drone._tick_sensing()

        self.reservations.rebuild(self.drones, start_tick=frame)

        # 3. Rebalance sectors periodically
        self._watch_coverage_stall()

        self._rebalance_timer += 1
        if self._rebalance_timer >= config.REBALANCE_INTERVAL:
            self._rebalance_timer = 0
            self._rebalance()

        # 4. Handle drones that became idle
        self._negotiate_frontiers(force=True)
        for drone in self.drones:
            if drone.state == IDLE and drone.battery.pct > 0.4:
                if drone.state == IDLE and not drone.scan_queue:
                    self._assign_nearest_sector(drone)

    def _watch_coverage_stall(self):
        coverage = self.game_map.exploration_pct()
        if coverage > self._last_coverage + 0.001:
            self._last_coverage = coverage
            self._coverage_stall_frames = 0
            return

        self._coverage_stall_frames += 1
        if self._all_drones_unproductive() and self._coverage_stall_frames > config.EXPLORATION_STALL_FRAMES // 3:
            self._emergency_recover_swarm()
            return

        if (self._coverage_stall_frames > config.COMM_RELAXATION_START_FRAMES and
                self.coverage_growth_per_min < config.EXPLORATION_MIN_GROWTH_PER_MIN and
                self._coverage_stall_frames % (config.TASK_NEGOTIATION_INTERVAL * 2) == 0):
            self.frontiers.refresh(self.game_map)
            self.alerts.append(
                f"Swarm: relaxing comm risk for expansion ({self.comm_risk_relaxation:.2f})"
            )
            for drone in self.drones:
                if (drone.state in (IDLE, SCANNING) and not drone.relay_anchor_active and
                        not drone.battery.should_return() and not drone.has_path() and
                        drone._stuck_frames >= config.STUCK_WARN_FRAMES):
                    self._release_assignment(drone, "coverage stall without path")
                    drone.set_state(IDLE)
                    drone.needs_frontier_reassign = True
            self._negotiate_frontiers(force=True)

        if self._coverage_stall_frames < config.EXPLORATION_STALL_FRAMES:
            return

        self._coverage_stall_frames = 0
        self.coverage_stall_recoveries += 1
        self.frontiers.refresh(self.game_map)
        self.alerts.append("Swarm: coverage stalled, refreshing exploration tasks")

        for drone in self.drones:
            if (drone.state in (IDLE, SCANNING) and not drone.relay_anchor_active and
                    not drone.battery.should_return() and not drone.has_path() and
                    drone._stuck_frames >= config.STUCK_WARN_FRAMES):
                self._release_assignment(drone, "coverage stall without path")
                drone.set_state(IDLE)
                drone.needs_frontier_reassign = True

        self._negotiate_frontiers(force=True)
        for drone in self.drones:
            if drone.state == IDLE and not drone.scan_queue and not drone.battery.should_return():
                self._assign_nearest_sector(drone)

    def _all_drones_unproductive(self) -> bool:
        from core.drone import RETURNING, CHARGING, FAILED, STRANDED
        return all(d.state in (RETURNING, CHARGING, FAILED, STRANDED) or d.battery.is_empty() for d in self.drones)

    def _emergency_recover_swarm(self):
        from core.drone import CHARGING, IDLE, STRANDED
        self._coverage_stall_frames = 0
        self.emergency_recoveries += 1
        self.emergency_recovery_active = True
        self.alerts.append("Swarm: emergency recovery, boosting docked recharge/relaunch")
        self.frontiers.refresh(self.game_map)

        for drone in self.drones:
            if drone.battery.is_empty() and drone.can_charge_here() and drone.state != CHARGING:
                drone._dock()
            if drone.battery.is_empty() and not drone.can_charge_here() and drone.state != STRANDED:
                drone._strand("battery depleted away from docking zone")
            if drone.state == CHARGING and drone.can_charge_here():
                previous_charge = drone.battery.level
                drone.battery.level = min(
                    drone.battery.max,
                    drone.battery.level + config.BATTERY_EMERGENCY_CHARGE_RATE * TICK_HZ
                )
                drone.battery.recharged += drone.battery.level - previous_charge
                if drone.battery.level >= config.BATTERY_RELAUNCH_THRESH:
                    drone.battery.stop_charging()
                    drone.set_state(IDLE)
                    drone.path.clear()
                    drone.decision = "emergency relaunch"
            if drone.state == IDLE and not drone.battery.should_return():
                drone.needs_frontier_reassign = True

        self._negotiate_frontiers(force=True)
        for drone in self.drones:
            if drone.state == IDLE and not drone.scan_queue and not drone.battery.should_return():
                self._assign_nearest_sector(drone)

    def _rebalance(self):
        """
        Dynamic load balancing:
        - Detect failed / lost drones and redistribute their sectors
        - Find idle charged drones and assign new sectors
        """
        from core.drone import FAILED, STRANDED, CHARGING, IDLE, RETURNING

        for drone in self.drones:
            if drone.state in (FAILED, STRANDED) and drone.assigned_sector is not None:
                self._release_assignment(drone, "inactive")
                self.alerts.append(f"Swarm: re-routing sector from inactive D{drone.drone_id}")

            # Assign partially-scanned sectors to returning drones with good battery
            if drone.state == IDLE and drone.battery.pct > 0.5:
                self._assign_nearest_sector(drone)

    # ──────────────────────────────────────────
    # Statistics
    # ──────────────────────────────────────────

    def mission_progress(self) -> float:
        return self.game_map.exploration_pct()

    def sectors_completed(self) -> int:
        return sum(1 for s in self.sectors if s.completed)

    def drone_state_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.drones:
            counts[d.state] = counts.get(d.state, 0) + 1
        return counts

    def active_alerts(self) -> list[str]:
        """Return and clear queued alerts."""
        out = list(self.alerts[-20:])   # keep last 20
        return out

    def comm_manager(self):
        return getattr(self, '_comm_manager', None)

    def rescue_stranded_to_base(self) -> int:
        """Explicit operator rescue: recover stranded drones back to the dock."""
        rescued = 0
        for drone in self.drones:
            if drone.state != STRANDED:
                continue
            bx, by = drone.base_px
            drone.px, drone.py = bx, by
            drone.vx = drone.vy = 0.0
            drone.battery.level = 0.0
            drone.battery.stop_charging()
            if drone._dock():
                drone._event("drone_rescued", reason="operator relocation to dock")
                drone.decision = "manual rescue to dock"
                rescued += 1
        if rescued:
            self.alerts.append(f"Swarm: manual rescue recovered {rescued} stranded drone(s)")
        else:
            self.alerts.append("Swarm: manual rescue requested; no stranded drones")
        return rescued
