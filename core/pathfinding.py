"""
core/pathfinding.py - A* pathfinding on the grid map.

Supports:
  - Standard A* with Manhattan + diagonal heuristic
  - Passability check delegated to Map
  - Path smoothing (optional)
  - Nearby-cell fallback when goal is blocked
"""

import heapq
import math
from dataclasses import dataclass
from enum import Enum
from numbers import Integral
from typing import Optional
from core.map import Map
from core.geometry import segment_is_clear


def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Octile distance heuristic (better than Manhattan for 8-directional movement)."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


class PathStatus(str, Enum):
    FOUND = "found"
    INVALID_INPUT = "invalid_input"
    UNREACHABLE = "unreachable"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class PathResult:
    status: PathStatus
    path: list[tuple[int, int]]
    requested_goal: tuple[int, int]
    resolved_goal: tuple[int, int] | None
    cost: float = math.inf
    expanded: int = 0


def find_path(
    game_map: Map, start_col: int, start_row: int, goal_col: int, goal_row: int,
    allow_diagonal: bool = True,
    other_drone_positions: Optional[list[tuple[int, int]]] = None,
    other_drone_paths: Optional[list[list[tuple[int, int]]]] = None,
    ai_seed: int = 0, drone_id: int | None = None,
    direction_bias: Optional[dict[tuple[int, int], float]] = None,
    reservation_table=None,
    comm_anchor_cells: Optional[list[tuple[int, int]]] = None,
    comm_range_cells: float | None = None, comm_risk_weight: float = 0.0,
    randomness: float = 0.0, max_iterations: int = 4000,
) -> list[tuple[int, int]]:
    """Compatibility API: a start-to-resolved-goal path, or [] on failure.

    See find_path_result for status, fallback endpoint, cost and search effort.
    All existing positional and keyword arguments retain their meaning.
    """
    return find_path_result(
        game_map, start_col, start_row, goal_col, goal_row, allow_diagonal,
        other_drone_positions, other_drone_paths, ai_seed, drone_id,
        direction_bias, reservation_table, comm_anchor_cells, comm_range_cells,
        comm_risk_weight, randomness, max_iterations,
    ).path


def find_path_result(
    game_map: Map,
    start_col: int,
    start_row: int,
    goal_col: int,
    goal_row: int,
    allow_diagonal: bool = True,
    other_drone_positions: Optional[list[tuple[int, int]]] = None,
    other_drone_paths: Optional[list[list[tuple[int, int]]]] = None,
    ai_seed: int = 0,
    drone_id: int | None = None,
    direction_bias: Optional[dict[tuple[int, int], float]] = None,
    reservation_table=None,
    comm_anchor_cells: Optional[list[tuple[int, int]]] = None,
    comm_range_cells: float | None = None,
    comm_risk_weight: float = 0.0,
    randomness: float = 0.0,
    max_iterations: int = 4000,
) -> PathResult:
    """
    Run A* from (start_col, start_row) to (goal_col, goal_row).

    Parameters
    ----------
    game_map : Map
        Used to query passability.
    start_col, start_row : int
        Starting grid cell.
    goal_col, goal_row : int
        Target grid cell.
    allow_diagonal : bool
        If True, 8-directional movement; otherwise 4-directional.
    other_drone_positions : list of (col, row) tuples, optional
        Cells occupied by other drones — treated as soft obstacles.
    max_iterations : int
        Safety cap on loop count.

    Static costs are cardinal 1 / diagonal sqrt(2), plus direction bias and
    nonnegative congestion/communication penalties. Biased base moves must be
    strictly positive. A scaled octile/Manhattan lower bound handles discounts.
    Seeded variation breaks equal-f ties only; it never perturbs f itself.

    max_iterations bounds expanded non-goal nodes (stale heap entries do not
    count). Reservations contribute a static spatial congestion envelope only.
    Execution enforces tick-time contacts; this is not a space-time planner.
    """
    requested = (goal_col, goal_row)
    resolved = None

    def result(status, path=None, cost=math.inf, expanded=0):
        return PathResult(status, path or [], requested, resolved, cost, expanded)

    coordinates = (start_col, start_row, goal_col, goal_row)
    if (any(not isinstance(v, Integral) or isinstance(v, bool) for v in coordinates) or
            not isinstance(max_iterations, Integral) or isinstance(max_iterations, bool) or
            max_iterations < 0 or not isinstance(ai_seed, Integral)):
        return result(PathStatus.INVALID_INPUT)
    if (not game_map.is_passable(start_col, start_row) or
            not game_map.in_bounds(goal_col, goal_row)):
        return result(PathStatus.INVALID_INPUT)
    if (not math.isfinite(randomness) or randomness < 0 or
            not math.isfinite(comm_risk_weight) or comm_risk_weight < 0 or
            (comm_range_cells is not None and (not math.isfinite(comm_range_cells) or comm_range_cells < 0))):
        return result(PathStatus.INVALID_INPUT)
    directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    if allow_diagonal:
        directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    move_costs = {d: math.hypot(*d) + (direction_bias or {}).get(d, 0.0) for d in directions}
    if any(not math.isfinite(c) or c <= 0 for c in move_costs.values()):
        return result(PathStatus.INVALID_INPUT)
    scale = min(1.0, min(c / math.hypot(*d) for d, c in move_costs.items()))

    def lower_bound(a, b):
        distance = heuristic(a, b) if allow_diagonal else abs(a[0]-b[0]) + abs(a[1]-b[1])
        return distance * scale

    # If goal is blocked, find nearest passable fallback
    if not game_map.is_passable(goal_col, goal_row):
        goal_col, goal_row = _nearest_passable(game_map, goal_col, goal_row)
        if goal_col is None:
            return result(PathStatus.UNREACHABLE)
    resolved = (goal_col, goal_row)

    occupied = set(other_drone_positions) if other_drone_positions else set()
    comm_anchors = list(comm_anchor_cells or [])
    comm_safe_range = comm_range_cells if comm_range_cells is not None else 0.0
    planned_cost: dict[tuple[int, int], float] = {}
    if other_drone_paths:
        for path in other_drone_paths:
            for step_idx, cell in enumerate(path[:30]):
                planned_cost[cell] = planned_cost.get(cell, 0.0) + max(0.5, 4.0 - step_idx * 0.12)

    start = (start_col, start_row)
    goal  = (goal_col,  goal_row)

    if start == goal:
        return result(PathStatus.FOUND, [start], 0.0)

    # Every improved label is pushed. Old labels are ignored when popped.
    counter   = 0
    open_set  = []
    heapq.heappush(open_set, (lower_bound(start, goal), 0.0, counter, 0.0, start))

    came_from: dict[tuple, tuple] = {}
    g_score: dict[tuple, float]   = {start: 0.0}

    iterations = 0
    while open_set:
        _, _, _, queued_g, current = heapq.heappop(open_set)
        if queued_g != g_score[current]:
            continue

        if current == goal:
            return result(PathStatus.FOUND, _reconstruct(came_from, current), queued_g, iterations)
        if iterations >= max_iterations:
            return result(PathStatus.BUDGET_EXHAUSTED, expanded=iterations)
        iterations += 1

        cx, cy = current
        for dx, dy in directions:
            nx, ny = cx + dx, cy + dy
            neighbor = (nx, ny)

            if not game_map.is_passable(nx, ny):
                continue
            if dx and dy and (not game_map.is_passable(cx + dx, cy) or
                              not game_map.is_passable(cx, cy + dy)):
                continue  # A diagonal must not touch a blocked corner.

            # Soft congestion penalty for occupied cells, nearby drones, and
            # peers' planned corridors. This discourages stacking without
            # making narrow passages impossible.
            drone_penalty = _congestion_penalty(neighbor, occupied, planned_cost, randomness)
            if reservation_table is not None and drone_id is not None:
                penalty = getattr(reservation_table, "spatial_penalty", None)
                if penalty is not None:
                    drone_penalty += penalty(drone_id, neighbor)
            if comm_anchors and comm_safe_range > 0.0 and comm_risk_weight > 0.0:
                drone_penalty += _comm_mesh_penalty(
                    neighbor,
                    comm_anchors,
                    comm_safe_range,
                    comm_risk_weight,
                )

            if not math.isfinite(drone_penalty) or drone_penalty < 0:
                return result(PathStatus.INVALID_INPUT, expanded=iterations)
            move_cost = move_costs[(dx, dy)] + drone_penalty
            tentative_g = g_score[current] + move_cost

            if tentative_g < g_score.get(neighbor, math.inf):
                came_from[neighbor] = current
                g_score[neighbor]   = tentative_g
                tie_noise = _stable_cell_noise(neighbor, ai_seed) * 0.08 * max(0.0, randomness)
                f = tentative_g + lower_bound(neighbor, goal)
                counter += 1
                heapq.heappush(open_set, (f, tie_noise, counter, tentative_g, neighbor))

    return result(PathStatus.UNREACHABLE, expanded=iterations)


def _stable_cell_noise(cell: tuple[int, int], seed: int) -> float:
    """Return deterministic 0..1 noise for a cell and drone-specific seed."""
    x, y = cell
    n = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF) / 0xFFFF


def _congestion_penalty(
    cell: tuple[int, int],
    occupied: set[tuple[int, int]],
    planned_cost: dict[tuple[int, int], float],
    randomness: float,
) -> float:
    penalty = planned_cost.get(cell, 0.0)
    if cell in occupied:
        penalty += 8.0

    cx, cy = cell
    for ox, oy in occupied:
        dist = abs(cx - ox) + abs(cy - oy)
        if dist == 1:
            penalty += 3.0
        elif dist == 2:
            penalty += 1.25

    return penalty * (0.6 + max(0.0, randomness))


def _comm_mesh_penalty(
    cell: tuple[int, int],
    anchors: list[tuple[int, int]],
    safe_range_cells: float,
    weight: float,
) -> float:
    nearest = min(math.hypot(cell[0] - ax, cell[1] - ay) for ax, ay in anchors)
    if nearest <= safe_range_cells:
        return 0.0
    return ((nearest - safe_range_cells) / max(1.0, safe_range_cells)) * weight


def _reconstruct(came_from: dict, current: tuple) -> list[tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _nearest_passable(
    game_map: Map,
    col: int,
    row: int,
    search_radius: int = 6,
) -> tuple[Optional[int], Optional[int]]:
    """BFS outward from (col, row) to find the nearest passable cell."""
    from collections import deque
    visited = set()
    queue   = deque([(col, row)])
    visited.add((col, row))

    while queue:
        c, r = queue.popleft()
        if game_map.is_passable(c, r):
            return c, r
        for dc, dr in [(0,1),(1,0),(0,-1),(-1,0)]:
            nc, nr = c + dc, r + dr
            if (nc, nr) not in visited and game_map.in_bounds(nc, nr):
                dist = abs(nc - col) + abs(nr - row)
                if dist <= search_radius:
                    visited.add((nc, nr))
                    queue.append((nc, nr))
    return None, None


def smooth_path(
    game_map: Map,
    path: list[tuple[int, int]],
    max_segment_cells: int | None = None,
) -> list[tuple[int, int]]:
    """
    Greedy string-pull / line-of-sight smoothing.
    Removes redundant waypoints when direct line is clear.
    """
    if any(not _line_of_sight(game_map, a, b) for a, b in zip(path, path[1:])):
        return []  # Do not pass an invalid input segment to the controller.
    if len(path) <= 2:
        return path

    smoothed = [path[0]]
    anchor   = 0

    for i in range(1, len(path)):
        segment_too_long = (
            max_segment_cells is not None and
            max(abs(path[i][0] - path[anchor][0]), abs(path[i][1] - path[anchor][1])) > max_segment_cells
        )
        if segment_too_long or not _line_of_sight(game_map, path[anchor], path[i]):
            smoothed.append(path[i - 1])
            anchor = i - 1

    smoothed.append(path[-1])
    return smoothed


def _line_of_sight(
    game_map: Map,
    a: tuple[int, int],
    b: tuple[int, int],
) -> bool:
    """Check the same closed-cell terrain geometry used by movement."""
    return segment_is_clear(game_map, (a[0] + 0.5, a[1] + 0.5),
                            (b[0] + 0.5, b[1] + 0.5))
