"""
core/intelligence.py - Frontier negotiation and reservation-table helpers.

The simulator still runs in one process, but drones evaluate frontier bids from
their own state. Swarm only arbitrates conflicting claims and exposes debug data.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import config


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

        old_assignments = {f.cell: f.assigned_drone for f in self.frontiers}
        self.frontiers = []
        for gain, col, row in clustered:
            self.frontiers.append(Frontier(
                frontier_id=self._next_id,
                col=col,
                row=row,
                info_gain=gain,
                assigned_drone=old_assignments.get((col, row)),
            ))
            self._next_id += 1

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
    """Soft time-indexed path reservations for collision avoidance."""

    def __init__(self):
        self.cells: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
        self.edges: dict[tuple[int, int], set[tuple[tuple[int, int], tuple[int, int], int]]] = {}

    def rebuild(self, drones):
        self.cells.clear()
        self.edges.clear()
        for drone in drones:
            if drone.has_path():
                self.reserve_path(drone.drone_id, drone.cell, drone.path[drone.waypoint_idx:])

    def reserve_path(self, drone_id: int, start: tuple[int, int], path: list[tuple[int, int]]):
        prev = start
        for step, cell in enumerate(path[:config.RESERVATION_HORIZON], start=1):
            self.cells.setdefault(cell, {})[step] = drone_id
            self.edges.setdefault((prev, cell), set()).add((prev, cell, step, drone_id))
            prev = cell

    def cell_penalty(self, drone_id: int, cell: tuple[int, int], step: int) -> float:
        owners = self.cells.get(cell)
        if not owners:
            return 0.0
        penalty = 0.0
        for reserved_step, owner in owners.items():
            if owner == drone_id:
                continue
            if abs(reserved_step - step) <= 1:
                penalty += config.RESERVATION_CELL_PENALTY
        return penalty

    def edge_penalty(
        self,
        drone_id: int,
        start: tuple[int, int],
        end: tuple[int, int],
        step: int,
    ) -> float:
        penalty = 0.0
        for edge in self.edges.get((end, start), set()):
            _, _, reserved_step, owner = edge
            if owner != drone_id and abs(reserved_step - step) <= 1:
                penalty += config.RESERVATION_EDGE_PENALTY
        return penalty

    def debug_cells(self, max_cells: int = 180) -> list[tuple[int, int, int]]:
        out: list[tuple[int, int, int]] = []
        for cell, steps in self.cells.items():
            if not steps:
                continue
            out.append((cell[0], cell[1], min(steps)))
            if len(out) >= max_cells:
                break
        return out


def distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
