"""
core/map.py - 2D grid map with terrain generation, fog-of-war, and zone overlays.

The Map holds a 2D numpy array of CellType values plus separate arrays for:
  - fog-of-war (explored / unexplored)
  - scan-count heatmap
  - mission-zone lookup
"""

import numpy as np
import random
import pygame
import config

# ──────────────────────────────────────────────
# Cell type constants
# ──────────────────────────────────────────────
CELL_FREE      = 0
CELL_OBSTACLE  = 1
CELL_NOFLY     = 2
CELL_THREAT    = 3
CELL_WIND      = 4
CELL_MISSION   = 5   # search-and-rescue target

# Label map for rendering
CELL_COLOR = {
    CELL_FREE:     config.C_SCANNED,
    CELL_OBSTACLE: config.C_OBSTACLE,
    CELL_NOFLY:    config.C_NOFLY,
    CELL_THREAT:   config.C_THREAT,
    CELL_WIND:     config.C_WIND,
    CELL_MISSION:  config.C_MISSION_ZONE,
}


class Zone:
    """A circular zone on the map (no-fly, threat, wind, mission)."""

    def __init__(self, col: int, row: int, radius: int, zone_type: int):
        self.col   = col
        self.row   = row
        self.radius = radius
        self.zone_type = zone_type

    def contains(self, col: int, row: int) -> bool:
        return (col - self.col) ** 2 + (row - self.row) ** 2 <= self.radius ** 2


class Map:
    """
    Main map object.  One instance exists per simulation run.

    Attributes
    ----------
    grid : ndarray (rows, cols) int8
        Cell type for every cell.
    fog  : ndarray (rows, cols) bool
        True = explored/revealed.
    heatmap : ndarray (rows, cols) int16
        Number of times each cell has been scanned.
    zones : list[Zone]
        All named zones.
    mission_zones : list[Zone]
        Subset of zones with zone_type == CELL_MISSION.
    mission_found : set
        Indices of mission zones that have been discovered.
    """

    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else random.randint(0, 99999)
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        self.rows = config.MAP_ROWS
        self.cols = config.MAP_COLS

        self.grid    = np.zeros((self.rows, self.cols), dtype=np.int8)
        self.fog     = np.zeros((self.rows, self.cols), dtype=bool)
        self.heatmap = np.zeros((self.rows, self.cols), dtype=np.int16)

        self.zones: list[Zone] = []
        self.mission_zones: list[Zone] = []
        self.mission_found: set = set()

        self._generate()

        # Pre-render the static tile surface (redrawn only when fog changes)
        self._tile_surface: pygame.Surface | None = None
        self._fog_dirty = True

    # ──────────────────────────────────────────
    # Generation
    # ──────────────────────────────────────────

    def _generate(self):
        """Procedurally generate terrain, zones, and obstacles."""
        rows, cols = self.rows, self.cols

        # 1. Random obstacle scatter
        for r in range(rows):
            for c in range(cols):
                if random.random() < config.OBSTACLE_DENSITY:
                    self.grid[r, c] = CELL_OBSTACLE

        # 2. Cellular-automata smoothing pass (makes clumps look natural)
        for _ in range(3):
            new_grid = self.grid.copy()
            for r in range(1, rows - 1):
                for c in range(1, cols - 1):
                    neighbours = int(self.grid[r-1, c]) + int(self.grid[r+1, c]) + \
                                 int(self.grid[r, c-1]) + int(self.grid[r, c+1])
                    if self.grid[r, c] == CELL_OBSTACLE and neighbours < 2:
                        new_grid[r, c] = CELL_FREE
                    elif self.grid[r, c] == CELL_FREE and neighbours >= 3:
                        new_grid[r, c] = CELL_OBSTACLE
            self.grid = new_grid

        # 3. Guarantee base area is free
        br, bc = config.BASE_ROW, config.BASE_COL
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r2, c2 = br + dr, bc + dc
                if 0 <= r2 < rows and 0 <= c2 < cols:
                    self.grid[r2, c2] = CELL_FREE

        # 4. Place circular zones (no-fly, threat, wind)
        zone_specs = [
            (config.NOFLY_ZONE_COUNT,   config.NOFLY_ZONE_RADIUS,  CELL_NOFLY),
            (config.THREAT_ZONE_COUNT,  config.THREAT_ZONE_RADIUS, CELL_THREAT),
            (config.WIND_ZONE_COUNT,    config.WIND_ZONE_RADIUS,   CELL_WIND),
        ]
        for count, radius, ztype in zone_specs:
            for _ in range(count):
                c_col = random.randint(radius + 5, cols - radius - 5)
                c_row = random.randint(radius + 5, rows - radius - 5)
                # Skip if too close to base
                if abs(c_col - bc) < 8 and abs(c_row - br) < 8:
                    continue
                zone = Zone(c_col, c_row, radius, ztype)
                self.zones.append(zone)
                if ztype == CELL_MISSION:
                    self.mission_zones.append(zone)
                # Stamp into grid (obstacles cleared inside zones)
                for r in range(max(0, c_row - radius), min(rows, c_row + radius + 1)):
                    for c in range(max(0, c_col - radius), min(cols, c_col + radius + 1)):
                        if zone.contains(c, r):
                            if ztype != CELL_MISSION:
                                self.grid[r, c] = ztype
                            else:
                                if self.grid[r, c] == CELL_OBSTACLE:
                                    self.grid[r, c] = CELL_FREE  # clear for rescue

        # 5. Place survivor zones only on base-reachable, explorable cells.
        self._place_mission_zones()

        # 6. Reveal starting area around base
        self.reveal_area(bc, br, 4)

    def _effective_mission_count(self) -> int:
        if getattr(config, "QUICK_DEMO_MODE", False):
            return min(config.MISSION_ZONE_COUNT, config.DEMO_MISSION_ZONE_COUNT)
        return config.MISSION_ZONE_COUNT

    def _reachable_from_base(self) -> set[tuple[int, int]]:
        from collections import deque
        start = (config.BASE_COL, config.BASE_ROW)
        visited = {start}
        queue = deque([start])
        while queue:
            col, row = queue.popleft()
            for dc, dr in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                nc, nr = col + dc, row + dr
                if (nc, nr) in visited or not self.is_passable(nc, nr):
                    continue
                visited.add((nc, nr))
                queue.append((nc, nr))
        return visited

    def _place_mission_zones(self):
        reachable = list(self._reachable_from_base())
        min_dist = 20 if getattr(config, "QUICK_DEMO_MODE", False) else 18
        max_dist = 38 if getattr(config, "QUICK_DEMO_MODE", False) else 999
        candidates = []
        for col, row in reachable:
            dist = abs(col - config.BASE_COL) + abs(row - config.BASE_ROW)
            if min_dist <= dist <= max_dist:
                candidates.append((col, row, dist))
        if not candidates:
            candidates = [(c, r, 0) for c, r in reachable]
        random.shuffle(candidates)
        if getattr(config, "QUICK_DEMO_MODE", False):
            candidates.sort(key=lambda item: item[2])

        mission_count = self._effective_mission_count()
        placed: list[tuple[int, int]] = []
        for col, row, _ in candidates:
            if len(placed) >= mission_count:
                break
            min_spacing = 10 if getattr(config, "QUICK_DEMO_MODE", False) else 12
            if any((col - pc) ** 2 + (row - pr) ** 2 < min_spacing ** 2 for pc, pr in placed):
                continue
            zone = Zone(col, row, 3, CELL_MISSION)
            self.zones.append(zone)
            self.mission_zones.append(zone)
            placed.append((col, row))
            self._clear_mission_area(zone)

    def _clear_mission_area(self, zone: Zone):
        for r in range(max(0, zone.row - zone.radius), min(self.rows, zone.row + zone.radius + 1)):
            for c in range(max(0, zone.col - zone.radius), min(self.cols, zone.col + zone.radius + 1)):
                if zone.contains(c, r) and self.grid[r, c] in (CELL_OBSTACLE, CELL_NOFLY):
                    self.grid[r, c] = CELL_FREE

    # ──────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────

    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def is_passable(self, col: int, row: int) -> bool:
        """A cell is passable if it's in bounds, not an obstacle, and not a no-fly zone."""
        if not self.in_bounds(col, row):
            return False
        ct = self.grid[row, col]
        return ct not in (CELL_OBSTACLE, CELL_NOFLY)

    def cell_type(self, col: int, row: int) -> int:
        if not self.in_bounds(col, row):
            return CELL_OBSTACLE
        return int(self.grid[row, col])

    def is_wind(self, col: int, row: int) -> bool:
        return self.in_bounds(col, row) and self.grid[row, col] == CELL_WIND

    def is_threat(self, col: int, row: int) -> bool:
        return self.in_bounds(col, row) and self.grid[row, col] == CELL_THREAT

    def reveal_area(self, col: int, row: int, radius: int):
        """Mark cells within `radius` cells of (col, row) as explored."""
        r2 = radius * radius
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dr * dr + dc * dc <= r2:
                    nr, nc = row + dr, col + dc
                    if self.in_bounds(nc, nr):
                        if not self.fog[nr, nc]:
                            self.fog[nr, nc] = True
                            self.heatmap[nr, nc] += 1
                            self._fog_dirty = True

    def scan_area(self, col: int, row: int, radius: int):
        """Same as reveal_area but increments heatmap each call."""
        for nc, nr in self.cells_in_radius(col, row, radius):
            self.fog[nr, nc] = True
            self.heatmap[nr, nc] += 1
        self._fog_dirty = True

    def cells_in_radius(self, col: int, row: int, radius: int) -> set[tuple[int, int]]:
        """Return in-bounds cells within a circular scan radius."""
        cells = set()
        r2 = radius * radius
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dr * dr + dc * dc <= r2:
                    nr, nc = row + dr, col + dc
                    if self.in_bounds(nc, nr):
                        cells.add((nc, nr))
        return cells

    def reveal_cells(self, cells: set[tuple[int, int]] | list[tuple[int, int]]) -> int:
        """Merge locally discovered cells into the global explored map."""
        newly_revealed = 0
        for col, row in cells:
            if not self.in_bounds(col, row):
                continue
            if not self.fog[row, col]:
                newly_revealed += 1
            self.fog[row, col] = True
            self.heatmap[row, col] += 1
        if cells:
            self._fog_dirty = True
        return newly_revealed

    def exploration_pct(self) -> float:
        """Return fraction of non-obstacle cells that have been explored."""
        passable = np.sum(self.grid != CELL_OBSTACLE)
        if passable == 0:
            return 1.0
        revealed = np.sum(self.fog & (self.grid != CELL_OBSTACLE))
        return float(revealed) / float(passable)

    def check_mission_discovery(self, col: int, row: int) -> list[int]:
        """Return indices of newly-found mission zones near (col, row)."""
        found = self.detect_mission_near(col, row)
        for i in found:
            self.mission_found.add(i)
        return found

    def detect_mission_near(self, col: int, row: int,
                            exclude_found: bool = True) -> list[int]:
        """Return mission indices near a cell without mutating mission state."""
        found = []
        bonus = (config.DEMO_SURVIVOR_DETECTION_BONUS
                 if getattr(config, "QUICK_DEMO_MODE", False)
                 else config.SURVIVOR_DETECTION_BONUS)
        for i, mz in enumerate(self.mission_zones):
            if not exclude_found or i not in self.mission_found:
                dist2 = (col - mz.col) ** 2 + (row - mz.row) ** 2
                if dist2 <= (mz.radius + bonus) ** 2:
                    found.append(i)
        return found

    def survivor_debug(self, drones: list | None = None) -> list[dict]:
        """Return reachability and sensor-range info for mission debug overlays."""
        reachable = self._reachable_from_base()
        bonus = (config.DEMO_SURVIVOR_DETECTION_BONUS
                 if getattr(config, "QUICK_DEMO_MODE", False)
                 else config.SURVIVOR_DETECTION_BONUS)
        out = []
        for i, mz in enumerate(self.mission_zones):
            in_sensor = False
            nearest = None
            if drones:
                for drone in drones:
                    dc, dr = drone.cell
                    dist = ((dc - mz.col) ** 2 + (dr - mz.row) ** 2) ** 0.5
                    nearest = dist if nearest is None else min(nearest, dist)
                    if dist <= mz.radius + bonus:
                        in_sensor = True
            out.append({
                "idx": i,
                "cell": (mz.col, mz.row),
                "reachable": (mz.col, mz.row) in reachable,
                "found": i in self.mission_found,
                "in_sensor": in_sensor,
                "nearest_drone_cells": nearest,
                "detect_radius": mz.radius + bonus,
            })
        return out

    # ──────────────────────────────────────────
    # Pixel helpers
    # ──────────────────────────────────────────

    def cell_to_pixel(self, col: int, row: int) -> tuple[int, int]:
        """Center pixel of a grid cell (relative to map origin)."""
        x = col * config.CELL_SIZE + config.CELL_SIZE // 2
        y = row * config.CELL_SIZE + config.CELL_SIZE // 2
        return x, y

    def pixel_to_cell(self, px: int, py: int) -> tuple[int, int]:
        return px // config.CELL_SIZE, py // config.CELL_SIZE

    # ──────────────────────────────────────────
    # Rendering
    # ──────────────────────────────────────────

    def build_tile_surface(self) -> pygame.Surface:
        """Build (or rebuild) the static tile surface.  Expensive; cached."""
        surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
        cell = config.CELL_SIZE

        for r in range(self.rows):
            for c in range(self.cols):
                rect = pygame.Rect(c * cell, r * cell, cell, cell)
                if not self.fog[r, c]:
                    pygame.draw.rect(surf, config.C_FOG, rect)
                else:
                    ct = int(self.grid[r, c])
                    color = CELL_COLOR.get(ct, config.C_SCANNED)
                    pygame.draw.rect(surf, color, rect)
                    # Subtle grid lines
                    pygame.draw.rect(surf, config.C_GRID, rect, 1)

        self._tile_surface = surf
        self._fog_dirty = False
        return surf

    def get_tile_surface(self) -> pygame.Surface:
        if self._fog_dirty or self._tile_surface is None:
            return self.build_tile_surface()
        return self._tile_surface

    def draw_heatmap_overlay(self, surf: pygame.Surface, alpha: int = 80):
        """Draw a semi-transparent heatmap overlay on top of the tile surface."""
        max_heat = max(1, int(self.heatmap.max()))
        cell = config.CELL_SIZE
        overlay = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
        for r in range(self.rows):
            for c in range(self.cols):
                val = self.heatmap[r, c]
                if val == 0:
                    continue
                t = min(1.0, val / max_heat)
                red   = int(config.C_HEATMAP_LOW[0] + t * (config.C_HEATMAP_HIGH[0] - config.C_HEATMAP_LOW[0]))
                green = int(config.C_HEATMAP_LOW[1] + t * (config.C_HEATMAP_HIGH[1] - config.C_HEATMAP_LOW[1]))
                blue  = int(config.C_HEATMAP_LOW[2] + t * (config.C_HEATMAP_HIGH[2] - config.C_HEATMAP_LOW[2]))
                a     = int(alpha * t)
                pygame.draw.rect(overlay, (red, green, blue, a),
                                 pygame.Rect(c * cell, r * cell, cell, cell))
        surf.blit(overlay, (0, 0))

    def draw_mission_zones(self, surf: pygame.Surface):
        """Draw pulsing rings around undiscovered mission zones (only if revealed by fog)."""
        cell = config.CELL_SIZE
        for i, mz in enumerate(self.mission_zones):
            if not self.fog[mz.row, mz.col]:
                continue  # still fogged
            px = mz.col * cell + cell // 2
            py = mz.row * cell + cell // 2
            color = (0, 255, 100) if i in self.mission_found else (255, 200, 0)
            pygame.draw.circle(surf, color, (px, py), mz.radius * cell, 2)
            if i not in self.mission_found:
                # Inner pulse (handled by caller via frame counter)
                pygame.draw.circle(surf, (255, 220, 50), (px, py), 4)

    def draw_base(self, surf: pygame.Surface):
        """Draw the base station marker."""
        cell = config.CELL_SIZE
        bx = config.BASE_COL * cell + cell // 2
        by = config.BASE_ROW * cell + cell // 2
        pygame.draw.circle(surf, config.C_BASE, (bx, by), config.BASE_RADIUS_PX)
        pygame.draw.circle(surf, (255, 255, 255), (bx, by), config.BASE_RADIUS_PX, 2)
