"""
core/utils.py - Shared utility functions used throughout the simulator.
"""

import math
import pygame
import config


# ──────────────────────────────────────────────
# Math helpers
# ──────────────────────────────────────────────

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)


def lerp_color(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )


def pulse(frame: int, period: int = 60, lo: float = 0.4, hi: float = 1.0) -> float:
    """Return a smoothly oscillating value between lo and hi."""
    t = (math.sin(frame / period * math.pi * 2) + 1) / 2
    return lerp(lo, hi, t)


def world_to_screen(px: float, py: float) -> tuple[int, int]:
    """Convert map-relative pixel coords to screen coords."""
    return int(px + config.MAP_OFFSET_X), int(py + config.MAP_OFFSET_Y)


def screen_to_world(sx: int, sy: int) -> tuple[int, int]:
    return sx - config.MAP_OFFSET_X, sy - config.MAP_OFFSET_Y


# ──────────────────────────────────────────────
# Drawing helpers
# ──────────────────────────────────────────────

def draw_text(
    surf: pygame.Surface,
    text: str,
    x: int,
    y: int,
    font: pygame.font.Font,
    color: tuple = config.C_UI_TEXT,
    anchor: str = "topleft",
):
    """Render text with optional anchor (topleft, topright, center)."""
    img = font.render(text, True, color)
    rect = img.get_rect()
    setattr(rect, anchor, (x, y))
    surf.blit(img, rect)
    return rect


def draw_bar(
    surf: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    value: float,
    max_val: float,
    fg_color: tuple,
    bg_color: tuple = config.C_UI_PANEL,
    border_color: tuple = config.C_UI_BORDER,
):
    """Draw a filled progress bar."""
    pygame.draw.rect(surf, bg_color,     (x, y, w, h))
    fill_w = int(w * clamp(value / max(1, max_val), 0, 1))
    pygame.draw.rect(surf, fg_color,     (x, y, fill_w, h))
    pygame.draw.rect(surf, border_color, (x, y, w, h), 1)


def draw_rounded_rect(
    surf: pygame.Surface,
    color: tuple,
    rect: pygame.Rect,
    radius: int = 6,
    width: int = 0,
):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def draw_panel(
    surf: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    title: str = "",
    font: pygame.font.Font | None = None,
):
    """Draw a dark panel with optional title."""
    draw_rounded_rect(surf, config.C_UI_PANEL, pygame.Rect(x, y, w, h), 6)
    draw_rounded_rect(surf, config.C_UI_BORDER, pygame.Rect(x, y, w, h), 6, 1)
    if title and font:
        draw_text(surf, title, x + 8, y + 6, font, config.C_UI_ACCENT)
    return y + (22 if title else 6)   # return y offset after title


# ──────────────────────────────────────────────
# Font cache (avoid recreating fonts each frame)
# ──────────────────────────────────────────────

_font_cache: dict[tuple, pygame.font.Font] = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _font_cache:
        try:
            _font_cache[key] = pygame.font.SysFont("consolas", size, bold=bold)
        except Exception:
            _font_cache[key] = pygame.font.SysFont("monospace", size, bold=bold)
    return _font_cache[key]
