"""Shared point-agent terrain geometry, in continuous grid coordinates.

Blocked cells are closed squares: touching a blocked corner/edge is invalid.
Drone radius is visual; finite-body and inter-agent clearance are separate work.
"""
import math
from core.experiment import settings as config


def motion_step(game_map, start, end):
    """One simulation tick, in pixels; None means terrain blocks the step."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance <= 1e-9:
        return start, True
    scale = config.CELL_SIZE
    cell = (math.floor(start[0] / scale), math.floor(start[1] / scale))
    speed = config.DRONE_SPEED_WIND if game_map.is_wind(*cell) else config.DRONE_SPEED
    step = min(speed, distance)
    point = end if step == distance else (start[0]+dx/distance*step, start[1]+dy/distance*step)
    if not segment_is_clear(game_map, (start[0]/scale, start[1]/scale),
                            (point[0]/scale, point[1]/scale)):
        return None, False
    return point, step == distance


def swept_cells(start, end):
    """All closed grid cells touched by a pixel segment, including corners."""
    cells = set()

    class Collector:
        def is_passable(self, col, row):
            cells.add((col, row))
            return True

    scale = config.CELL_SIZE
    segment_is_clear(Collector(), (start[0]/scale, start[1]/scale),
                     (end[0]/scale, end[1]/scale))
    return cells


def trajectories_contact(a0, a1, b0, b1, base):
    """Synchronous point contact during one tick, except shared docking space."""
    rx, ry = a0[0]-b0[0], a0[1]-b0[1]
    vx, vy = a1[0]-a0[0]-b1[0]+b0[0], a1[1]-a0[1]-b1[1]+b0[1]
    vv = vx*vx + vy*vy
    t = min(1.0, max(0.0, -(rx*vx+ry*vy)/vv)) if vv else 0.0
    if math.hypot(rx+vx*t, ry+vy*t) > 1e-7:
        return False
    # Check the entire contact interval, not just its minimum-distance point.
    # Almost co-moving centers can have their closest point inside the base yet
    # remain within numerical contact tolerance after leaving the shared zone.
    if vv:
        center = -(rx*vx+ry*vy)/vv
        minimum_sq = (rx+vx*center)**2 + (ry+vy*center)**2
        half_width = math.sqrt(max(0.0, 1e-14-minimum_sq)/vv)
        bounds = (max(0.0, center-half_width), min(1.0, center+half_width))
    else:
        bounds = (0.0, 1.0)
    # The docking disk is convex, so both ends suffice for each trajectory.
    return any(math.dist((p[0]+(q[0]-p[0])*at, p[1]+(q[1]-p[1])*at), base)
               > config.BASE_DOCKING_RADIUS_PX
               for p, q in ((a0,a1), (b0,b1)) for at in bounds)


def segment_is_clear(game_map, start, end):
    """Supercover grid traversal, including both cells at a corner crossing."""
    x, y = start
    ex, ey = end
    if not all(math.isfinite(v) for v in (x, y, ex, ey)):
        return False
    dx, dy = ex - x, ey - y
    col, row = math.floor(x), math.floor(y)
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)

    def clear(c, r):
        if not game_map.is_passable(c, r):
            return False
        # A segment lying on a grid edge touches cells on both sides.
        if dx == 0 and x == math.floor(x) and not game_map.is_passable(c - 1, r):
            return False
        if dy == 0 and y == math.floor(y) and not game_map.is_passable(c, r - 1):
            return False
        return True

    def endpoint_clear(px, py):
        cs = [math.floor(px)]
        rs = [math.floor(py)]
        if px == cs[0]:
            cs.append(cs[0] - 1)
        if py == rs[0]:
            rs.append(rs[0] - 1)
        return all(game_map.is_passable(c, r) for c in cs for r in rs)

    if not endpoint_clear(x, y) or not endpoint_clear(ex, ey):
        return False
    tx = ((col + 1 - x) / dx if dx > 0 else (col - x) / dx) if dx else math.inf
    ty = ((row + 1 - y) / dy if dy > 0 else (row - y) / dy) if dy else math.inf
    dtx, dty = (1 / abs(dx) if dx else math.inf), (1 / abs(dy) if dy else math.inf)
    while min(tx, ty) <= 1.0:
        if abs(tx - ty) <= 1e-12:
            if not clear(col + sx, row) or not clear(col, row + sy):
                return False
            col, row = col + sx, row + sy
            tx, ty = tx + dtx, ty + dty
        elif tx < ty:
            col += sx
            tx += dtx
        else:
            row += sy
            ty += dty
        if not clear(col, row):
            return False
    return True
