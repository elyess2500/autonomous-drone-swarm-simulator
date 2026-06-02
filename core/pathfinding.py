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
from typing import Optional
from core.map import Map


def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Octile distance heuristic (better than Manhattan for 8-directional movement)."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


def find_path(
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
) -> list[tuple[int, int]]:
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

    Returns
    -------
    list of (col, row) tuples representing the path (including start and goal),
    or an empty list if no path found.
    """
    # If goal is blocked, find nearest passable fallback
    if not game_map.is_passable(goal_col, goal_row):
        goal_col, goal_row = _nearest_passable(game_map, goal_col, goal_row)
        if goal_col is None:
            return []

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
        return [start]

    # open_set: (f_score, counter, (col, row))
    counter   = 0
    open_set  = []
    heapq.heappush(open_set, (0.0, counter, start))

    came_from: dict[tuple, tuple] = {}
    g_score: dict[tuple, float]   = {start: 0.0}
    f_score: dict[tuple, float]   = {start: heuristic(start, goal)}
    in_open: set                   = {start}

    directions = (
        [(0, 1), (1, 0), (0, -1), (-1, 0)]
        if not allow_diagonal
        else [(0, 1), (1, 0), (0, -1), (-1, 0),
              (1, 1), (1, -1), (-1, 1), (-1, -1)]
    )
    diag_cost = math.sqrt(2)

    iterations = 0
    while open_set and iterations < max_iterations:
        iterations += 1
        _, _, current = heapq.heappop(open_set)
        in_open.discard(current)

        if current == goal:
            return _reconstruct(came_from, current)

        cx, cy = current
        for dx, dy in directions:
            nx, ny = cx + dx, cy + dy
            neighbor = (nx, ny)

            if not game_map.is_passable(nx, ny):
                continue

            # Soft congestion penalty for occupied cells, nearby drones, and
            # peers' planned corridors. This discourages stacking without
            # making narrow passages impossible.
            drone_penalty = _congestion_penalty(neighbor, occupied, planned_cost, randomness)
            step = int(g_score[current]) + 1
            if reservation_table is not None and drone_id is not None:
                drone_penalty += reservation_table.cell_penalty(drone_id, neighbor, step)
                drone_penalty += reservation_table.edge_penalty(drone_id, current, neighbor, step)
            if comm_anchors and comm_safe_range > 0.0 and comm_risk_weight > 0.0:
                drone_penalty += _comm_mesh_penalty(
                    neighbor,
                    comm_anchors,
                    comm_safe_range,
                    comm_risk_weight,
                )

            pref_penalty = direction_bias.get((dx, dy), 0.0) if direction_bias else 0.0
            move_cost = (diag_cost if (dx != 0 and dy != 0) else 1.0) + drone_penalty + pref_penalty
            tentative_g = g_score[current] + move_cost

            if tentative_g < g_score.get(neighbor, math.inf):
                came_from[neighbor] = current
                g_score[neighbor]   = tentative_g
                tie_noise = _stable_cell_noise(neighbor, ai_seed) * 0.08 * max(0.0, randomness)
                f                   = tentative_g + heuristic(neighbor, goal) + tie_noise
                f_score[neighbor]   = f
                if neighbor not in in_open:
                    counter += 1
                    heapq.heappush(open_set, (f, counter, neighbor))
                    in_open.add(neighbor)

    return []  # No path found


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
    """Bresenham line check — True if all cells between a and b are passable."""
    x0, y0 = a
    x1, y1 = b
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        if not game_map.is_passable(x0, y0):
            return False
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return True
