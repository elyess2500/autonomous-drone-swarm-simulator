"""
ui/minimap.py - Small overview minimap rendered in the title bar area.

Shows the full map at reduced resolution with drone positions overlaid.
"""

import pygame
import config
from core.map import CELL_OBSTACLE, CELL_NOFLY, CELL_MISSION
from core.drone import STATE_COLOR
from core.utils import get_font, draw_text


MINI_W = 160
MINI_H = int(MINI_W * config.MAP_ROWS / config.MAP_COLS)
MINI_X = config.MAP_OFFSET_X
MINI_Y = 4   # sits in the title bar strip above the main map


class Minimap:
    """
    Renders a MINI_W × MINI_H pixel overview of the game map.
    The minimap is rebuilt every N frames (not every frame) for performance.
    """

    def __init__(self):
        self._surface = pygame.Surface((MINI_W, MINI_H))
        self._dirty   = True
        self._timer   = 0
        self._rebuild_interval = 10   # frames
        self._smooth_positions: dict[int, tuple[float, float]] = {}

    # ──────────────────────────────────────────
    # Scale helpers
    # ──────────────────────────────────────────

    def _to_mini(self, col: int, row: int) -> tuple[int, int]:
        mx = int(col / config.MAP_COLS * MINI_W)
        my = int(row / config.MAP_ROWS * MINI_H)
        return mx, my

    # ──────────────────────────────────────────
    # Build / update
    # ──────────────────────────────────────────

    def _rebuild(self, game_map):
        surf = self._surface
        surf.fill(config.C_FOG)

        scale_x = MINI_W / config.MAP_COLS
        scale_y = MINI_H / config.MAP_ROWS

        for r in range(0, config.MAP_ROWS, 2):
            for c in range(0, config.MAP_COLS, 2):
                mx = int(c * scale_x)
                my = int(r * scale_y)
                pw = max(1, int(scale_x * 2))
                ph = max(1, int(scale_y * 2))

                if not game_map.fog[r, c]:
                    color = config.C_FOG
                else:
                    ct = game_map.grid[r, c]
                    if ct == CELL_OBSTACLE:
                        color = config.C_OBSTACLE
                    elif ct == CELL_NOFLY:
                        color = config.C_NOFLY
                    elif ct == CELL_MISSION:
                        color = config.C_MISSION_ZONE
                    else:
                        color = (25, 38, 60)
                pygame.draw.rect(surf, color, (mx, my, pw, ph))

        # Base marker
        bx, by = self._to_mini(config.BASE_COL, config.BASE_ROW)
        pygame.draw.circle(surf, config.C_BASE, (bx, by), 3)

        self._dirty = False

    def draw(self, screen: pygame.Surface, game_map, drones: list, frame: int, camera=None):
        """Draw minimap onto the screen surface."""
        self._timer += 1
        if self._timer >= self._rebuild_interval or self._dirty:
            self._timer = 0
            self._rebuild(game_map)

        # Copy base surface
        mini_copy = self._surface.copy()

        # Draw drone dots
        scale_x = MINI_W / config.MAP_COLS
        scale_y = MINI_H / config.MAP_ROWS
        for d in drones:
            col, row = d.cell
            tx = col * scale_x
            ty = row * scale_y
            sx, sy = self._smooth_positions.get(d.drone_id, (tx, ty))
            sx += (tx - sx) * 0.35
            sy += (ty - sy) * 0.35
            self._smooth_positions[d.drone_id] = (sx, sy)
            mx = int(sx)
            my = int(sy)
            color = STATE_COLOR.get(d.state, config.C_STATE_IDLE)
            pygame.draw.circle(mini_copy, color, (mx, my), 2)

        if camera is not None and camera.zoom >= 1.0:
            vx = int(camera.x / config.MAP_PIXEL_W * MINI_W)
            vy = int(camera.y / config.MAP_PIXEL_H * MINI_H)
            vw = max(4, int((config.MAP_PIXEL_W / max(1.0, camera.zoom)) / config.MAP_PIXEL_W * MINI_W))
            vh = max(4, int((config.MAP_PIXEL_H / max(1.0, camera.zoom)) / config.MAP_PIXEL_H * MINI_H))
            pygame.draw.rect(mini_copy, config.C_UI_ACCENT, (vx, vy, vw, vh), 1)

        # Border
        pygame.draw.rect(mini_copy, config.C_UI_BORDER,
                         (0, 0, MINI_W, MINI_H), 1)

        screen.blit(mini_copy, (MINI_X, MINI_Y))

        # Label
        font = get_font(config.FONT_MONO_SM)
        draw_text(screen, "OVERVIEW", MINI_X, MINI_Y + MINI_H + 2,
                  font, config.C_UI_BORDER)
