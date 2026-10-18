"""
core/intelligence.py - Frontier negotiation and reservation-table helpers.

The simulator still runs in one process, but drones evaluate frontier bids from
their own state. Swarm only arbitrates conflicting claims and exposes debug data.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from core.experiment import settings as config
from core.geometry import motion_step, swept_cells, trajectories_contact


@dataclass
class Frontier:
    """A compact exploration task centered on a frontier cell."""

    frontier_id: int
    col: int
    row: int
    info_gain: int
    assigned_drone: int | None = None
    winning_bid: float = 0.0

    @property
    def cell(self) -> tuple[int, int]:
        return self.col, self.row


class FrontierMap:
    """Find and cluster exploration frontiers from the shared map."""

    def __init__(self):
        self.frontiers: list[Frontier] = []
        self._next_id = 0

    def refresh(self, game_map, reserved_targets: set[tuple[int, int]] | None = None):
        reserved_targets = reserved_targets or set()
        candidates: list[tuple[int, int, int]] = []

        for row in range(game_map.rows):
            for col in range(game_map.cols):
                if not game_map.fog[row, col] or not game_map.is_passable(col, row):
                    continue
                if (col, row) in reserved_targets:
                    continue
                if self._touches_unknown(game_map, col, row):
                    gain = self._info_gain(game_map, col, row)
                    if gain > 0:
                        candidates.append((gain, col, row))

        candidates.sort(reverse=True)
        clustered: list[tuple[int, int, int]] = []
        radius = config.FRONTIER_CLUSTER_RADIUS
        for gain, col, row in candidates:
            if len(clustered) >= config.MAX_FRONTIERS:
                break
            if any(abs(col - c) + abs(row - r) <= radius for _, c, r in clustered):
                continue
            clustered.append((gain, col, row))

        old = {f.cell: f for f in self.frontiers}
        # A refresh discovers opportunities; it must not revoke live contracts.
        self.frontiers = [f for f in self.frontiers if f.assigned_drone is not None]
        live_cells = {f.cell for f in self.frontiers}
        for gain, col, row in clustered:
            if (col, row) in live_cells or len(self.frontiers) >= config.MAX_FRONTIERS:
                continue
            frontier = old.get((col, row))
            if frontier is None:
                frontier = Frontier(self._next_id, col, row, gain)
                self._next_id += 1
            frontier.info_gain = gain
            self.frontiers.append(frontier)

    def available(self) -> list[Frontier]:
        return [f for f in self.frontiers if f.assigned_drone is None]

    def assigned_to(self, drone_id: int) -> Frontier | None:
        for frontier in self.frontiers:
            if frontier.assigned_drone == drone_id:
                return frontier
        return None

    def release_drone(self, drone_id: int):
        for frontier in self.frontiers:
            if frontier.assigned_drone == drone_id:
                frontier.assigned_drone = None
                frontier.winning_bid = 0.0

    def _touches_unknown(self, game_map, col: int, row: int) -> bool:
        for dc, dr in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nc, nr = col + dc, row + dr
            if game_map.in_bounds(nc, nr) and not game_map.fog[nr, nc]:
                return True
        return False

    def _info_gain(self, game_map, col: int, row: int) -> int:
        gain = 0
        radius = config.FRONTIER_INFO_RADIUS
        r2 = radius * radius
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dc * dc + dr * dr > r2:
                    continue
                nc, nr = col + dc, row + dr
                if game_map.in_bounds(nc, nr) and not game_map.fog[nr, nc]:
                    gain += 1
        return gain


class ReservationTable:
    """Tick-indexed trajectory forecasts, plus an authoritative one-tick gate.

    Forecasts are soft advice: FSM decisions can replace a path on the next tick.
    cells[cell][tick] includes every owner sweeping that closed cell during
    (tick-1, tick]; trajectories retain exact pixel endpoints. No claim wins by
    overwriting storage. Static A* uses only the spatial envelope, never cost as
    time. Point-contact enforcement is separate from conservative cell overlap.
    """

    def __init__(self):
        self.cells = {}
        self.edges = {}
        self.trajectories = {}
        self.segments = {}
        self._envelope = {}
        self.priority_key = lambda drone: drone.drone_id
        self.wait_limit = config.STUCK_REROUTE_FRAMES
        self.max_recoveries = 2
        self.counters = dict(conflicts=0, waits=0, recovery_attempts=0,
                             recoveries=0, deadlocks=0)
        self.frame = None
        self._waits = {}
        self._attempts = {}
        self._deadlocked = set()
        self._recovery_goal = {}

    def begin_tick(self, frame, drones):
        """Snapshot start positions; uncommitted peers are allowed to stay put.

        Call movers in priority_key order. A rejected move never invalidates an
        earlier commitment: earlier moves already checked this stationary case.
        """
        self.frame = frame
        self._drones = {d.drone_id: d for d in drones}
        self._starts = {d.drone_id: (d.px, d.py) for d in drones}
        self._ends = dict(self._starts)
        self._requested = set()
        for drone in drones:
            drone._motion_table = self
            drone._collision_waiting = False

    def _blockers(self, drone, end):
        owner = drone.drone_id
        return [other for idx, other in self._drones.items() if idx != owner and
                trajectories_contact(self._starts[owner], end, self._starts[idx],
                                     self._ends[idx], drone.base_px)]

    def try_move(self, drone, end):
        owner = drone.drone_id
        goal = (drone.state, drone.target_cell)
        if self._recovery_goal.get(owner) != goal:
            self._recovery_goal[owner] = goal
            self._attempts.pop(owner, None)
            self._deadlocked.discard(owner)
        if owner in self._requested:
            return False  # At most one physical movement per simulation tick.
        self._requested.add(owner)
        blockers = self._blockers(drone, end)
        if not blockers:
            self._ends[owner] = end
            self._waits[owner] = 0
            return True
        self.counters['conflicts'] += len(blockers)
        self.counters['waits'] += 1
        drone._event('collision_rejected', blockers=sorted(d.drone_id for d in blockers))
        drone._event('collision_wait')
        self._waits[owner] = self._waits.get(owner, 0) + 1
        drone._collision_waiting = True
        drone.decision = 'collision yield; retaining task and waypoint'
        if self._waits[owner] >= self.wait_limit:
            self._recover(drone, blockers)
        return False

    def waypoint_progress(self, drone):
        """Only reaching the goal resets backoff, not a reroute's start node."""
        if drone.target_cell is not None and drone._at_cell_center(*drone.target_cell):
            self._attempts.pop(drone.drone_id, None)
            self._deadlocked.discard(drone.drone_id)

    def _recover(self, drone, blockers):
        owner = drone.drone_id
        # Lower priority yields; a permanently stationary peer always has space.
        eligible = any(self.priority_key(d) < self.priority_key(drone) or
                       d.state in ('idle', 'failed', 'stranded', 'charging') for d in blockers)
        if not eligible or getattr(drone, '_yield_target', None) is not None:
            return
        attempts = self._attempts.get(owner, 0)
        if attempts >= self.max_recoveries:
            if owner not in self._deadlocked:
                self._deadlocked.add(owner)
                self.counters['deadlocks'] += 1
                drone._event('backoff_exhausted')
            return
        self._attempts[owner] = attempts + 1
        self.counters['recovery_attempts'] += 1
        drone._event('backoff_attempt')
        self._waits[owner] = 0
        start = (drone.px, drone.py)
        target = drone.current_waypoint_px() or start
        heading = (target[0]-start[0], target[1]-start[1])
        # Sideways first, then backwards; fixed cardinal order breaks ties.
        directions = sorted(((0, 1), (1, 0), (0, -1), (-1, 0)),
                            key=lambda d: abs(d[0]*heading[0]+d[1]*heading[1]))
        col, row = drone.cell
        for dc, dr in directions:
            if dc*heading[0]+dr*heading[1] > 1e-9:
                continue
            cell = (col+dc, row+dr)
            end = drone.game_map.cell_to_pixel(*cell)
            if not self._clear(drone, start, end):
                continue
            if any(trajectories_contact(start, end, (d.px, d.py), (d.px, d.py), drone.base_px)
                   for d in self._drones.values() if d is not drone):
                continue
            drone._yield_target = cell
            self.counters['recoveries'] += 1
            drone._event('backoff_initiated')
            drone.decision = 'bounded collision sidestep; retaining task'
            return

    def _record(self, owner, tick, start, end):
        self.trajectories.setdefault(owner, {})[tick] = end
        for cell in swept_cells(start, end):
            self.cells.setdefault(cell, {}).setdefault(tick, set()).add(owner)
            self._envelope.setdefault(cell, set()).add(owner)
        scale = config.CELL_SIZE
        a = (math.floor(start[0]/scale), math.floor(start[1]/scale))
        b = (math.floor(end[0]/scale), math.floor(end[1]/scale))
        self.edges.setdefault((a, b), {}).setdefault(tick, set()).add(owner)
        self.segments.setdefault(tick, []).append((owner, start, end))

    def rebuild(self, drones, start_tick=0):
        self.cells.clear()
        self.edges.clear()
        self.trajectories.clear()
        self.segments.clear()
        self._envelope.clear()
        for drone in sorted(drones, key=lambda d: d.drone_id):
            point = (drone.px, drone.py)
            self._record(drone.drone_id, start_tick, point, point)
            path = list(drone.path[drone.waypoint_idx:])
            yielding = getattr(drone, '_yield_target', None)
            if yielding is not None:
                path = [yielding]  # Replanning follows a completed sidestep.
            if drone.state in ('idle', 'failed', 'stranded', 'charging'):
                path = []
            index = 0
            for tick in range(start_tick+1, start_tick+config.RESERVATION_HORIZON+1):
                previous = point
                # Returning drones enter the existing physical docking approach.
                direct = (drone.state == 'returning' and yielding is None and
                          math.dist(point, drone.base_px) <= config.BASE_DOCKING_RADIUS_PX + config.PATH_WAYPOINT_DIST*1.5)
                if drone.state == 'returning' and math.dist(point, drone.base_px) <= config.BASE_DOCKING_RADIUS_PX:
                    point = drone.base_px
                elif direct and self._clear(drone, point, drone.base_px):
                    point, _ = motion_step(drone.game_map, point, drone.base_px)
                    point = previous if point is None else point
                elif index < len(path):
                    target = drone.game_map.cell_to_pixel(*path[index])
                    point, arrived = motion_step(drone.game_map, point, target)
                    point = previous if point is None else point
                    if arrived:
                        index += 1
                self._record(drone.drone_id, tick, previous, point)

    @staticmethod
    def _clear(drone, start, end):
        from core.geometry import segment_is_clear
        scale = config.CELL_SIZE
        return segment_is_clear(drone.game_map, (start[0]/scale, start[1]/scale),
                                (end[0]/scale, end[1]/scale))

    def reserve_path(self, drone_id, start, path, start_tick=0):
        """Legacy cell-path adapter: normal-speed free-space forecast only.

        Rebuild(drones) is the authoritative wind/terrain-aware forecast API.
        """
        if drone_id in self.trajectories:
            raise ValueError('owner already reserved; rebuild to replace its trajectory')
        class FreeSpace:
            def is_wind(self, *cell):
                return False
            def is_passable(self, *cell):
                return True
        scale = config.CELL_SIZE
        center = lambda cell: ((cell[0]+.5)*scale, (cell[1]+.5)*scale)
        point, index = center(start), 0
        self._record(drone_id, start_tick, point, point)
        for tick in range(start_tick+1, start_tick+config.RESERVATION_HORIZON+1):
            previous = point
            if index < len(path):
                point, arrived = motion_step(FreeSpace(), point, center(path[index]))
                if arrived:
                    index += 1
            self._record(drone_id, tick, previous, point)

    def spatial_penalty(self, drone_id, cell):
        return len(self._envelope.get(cell, set()) - {drone_id}) * config.RESERVATION_CELL_PENALTY

    def cell_penalty(self, drone_id, cell, step):
        return len(self.cells.get(cell, {}).get(step, set()) - {drone_id}) * config.RESERVATION_CELL_PENALTY

    def edge_penalty(self, drone_id, start, end, step):
        return len(self.edges.get((end, start), {}).get(step, set()) - {drone_id}) * config.RESERVATION_EDGE_PENALTY

    def debug_cells(self, max_cells=180):
        return [(c, r, min(ticks)) for (c, r), ticks in list(self.cells.items())[:max_cells]]


def distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
