"""
main.py - Autonomous Drone Swarm Simulator
==========================================

Entry point.  Run with:

    python main.py

Controls
--------
  H        Toggle heatmap overlay
  C        Toggle communication links
  S        Toggle sensor rings
  T        Toggle drone trails
  F        Toggle assigned frontier overlay
  V        Toggle reservation-table overlay
  D        Toggle drone decision labels
  P        Pause / resume
  + / -    Camera zoom
  Arrows   Camera pan
  SPACE    Follow next drone
  E        Export replay JSON
  L        Load latest replay JSON
  Y        Rescue stranded drones to base
  R        Restart simulation
  ESC      Quit
  Mouse    Click map to inspect cell (debug)
"""

import math
import sys
import random
import pygame

import config
from core.map import Map
from core.swarm import Swarm
from core.mission import Mission, MISSION_COMPLETE
from core.utils import world_to_screen, get_font, draw_text, draw_rounded_rect, pulse, lerp_color, clamp
from ui.dashboard import Dashboard
from ui.minimap import Minimap


# ──────────────────────────────────────────────
# Particle system for visual fx
# ──────────────────────────────────────────────

class Particle:
    """Tiny spark spawned when a mission zone is discovered."""
    def __init__(self, x, y):
        import math, random
        self.x, self.y = x, y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(0.5, 2.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.randint(30, 70)
        self.max_life = self.life
        self.color = random.choice([
            (0, 255, 100), (255, 220, 50), (0, 200, 255), (255, 255, 255)
        ])

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.04   # gravity
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        alpha = int(255 * self.life / self.max_life)
        r, g, b = self.color
        pygame.draw.circle(surf, (r, g, b), (int(self.x), int(self.y)), 2)


# ──────────────────────────────────────────────
# Simulation wrapper
# ──────────────────────────────────────────────

def make_simulation(seed=None):
    """Create a fresh simulation with a new random seed."""
    if seed is None:
        seed = (config.RANDOM_SEED if config.RANDOM_SEED is not None
                else random.randint(0, 99999))
    game_map = Map(seed=seed)
    swarm    = Swarm(game_map, config.NUM_DRONES)
    mission  = Mission(game_map, swarm)
    return game_map, swarm, mission, seed


APP_MENU = "menu"
APP_RUNNING = "running"
APP_PAUSED = "paused"
APP_SETTINGS = "settings"
APP_END = "end"


class Camera:
    """Smooth map viewport for zoom, pan, and follow-drone views."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.follow_id: int | None = None

    def reset(self):
        self.x = self.y = self.target_x = self.target_y = 0.0
        self.zoom = self.target_zoom = 1.0
        self.follow_id = None

    def set_zoom(self, zoom: float):
        self.target_zoom = clamp(zoom, 0.75, 2.2)

    def zoom_by(self, delta: float):
        self.set_zoom(self.target_zoom + delta)

    def pan(self, dx: float, dy: float):
        self.follow_id = None
        self.target_x += dx
        self.target_y += dy
        self._clamp_targets()

    def follow_next(self, drones):
        active = [d for d in drones if d.state not in ("failed", "stranded")]
        if not active:
            self.follow_id = None
            return
        ids = [d.drone_id for d in active]
        if self.follow_id not in ids:
            self.follow_id = ids[0]
        else:
            self.follow_id = ids[(ids.index(self.follow_id) + 1) % len(ids)]
        self.set_zoom(max(self.target_zoom, 1.35))

    def follow_drone(self, drone_id: int, zoom: float = 1.45):
        self.follow_id = drone_id
        self.set_zoom(zoom)

    def update(self, drones, keys=None):
        if keys:
            speed = 7.0 / max(1.0, self.target_zoom)
            dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
            dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
            if dx or dy:
                self.pan(dx * speed, dy * speed)

        if self.follow_id is not None:
            drone = next((d for d in drones if d.drone_id == self.follow_id), None)
            if drone is not None:
                visible_w = config.MAP_PIXEL_W / max(1.0, self.target_zoom)
                visible_h = config.MAP_PIXEL_H / max(1.0, self.target_zoom)
                self.target_x = drone.px - visible_w / 2
                self.target_y = drone.py - visible_h / 2
                self._clamp_targets()

        self.zoom += (self.target_zoom - self.zoom) * 0.12
        self.x += (self.target_x - self.x) * 0.12
        self.y += (self.target_y - self.y) * 0.12

    def _clamp_targets(self):
        zoom = max(1.0, self.target_zoom)
        visible_w = config.MAP_PIXEL_W / zoom
        visible_h = config.MAP_PIXEL_H / zoom
        self.target_x = clamp(self.target_x, 0.0, max(0.0, config.MAP_PIXEL_W - visible_w))
        self.target_y = clamp(self.target_y, 0.0, max(0.0, config.MAP_PIXEL_H - visible_h))

    def render(self, map_surf: pygame.Surface) -> pygame.Surface:
        if self.zoom < 0.99:
            scaled_w = int(config.MAP_PIXEL_W * self.zoom)
            scaled_h = int(config.MAP_PIXEL_H * self.zoom)
            out = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
            out.fill((6, 9, 16))
            scaled = pygame.transform.scale(map_surf, (scaled_w, scaled_h))
            out.blit(scaled, ((config.MAP_PIXEL_W - scaled_w) // 2,
                              (config.MAP_PIXEL_H - scaled_h) // 2))
            return out

        zoom = max(1.0, self.zoom)
        visible_w = max(1, int(config.MAP_PIXEL_W / zoom))
        visible_h = max(1, int(config.MAP_PIXEL_H / zoom))
        x = int(clamp(self.x, 0, max(0, config.MAP_PIXEL_W - visible_w)))
        y = int(clamp(self.y, 0, max(0, config.MAP_PIXEL_H - visible_h)))
        crop = map_surf.subsurface(pygame.Rect(x, y, visible_w, visible_h)).copy()
        return pygame.transform.scale(crop, (config.MAP_PIXEL_W, config.MAP_PIXEL_H))


def is_mission_failed(swarm, mission) -> bool:
    if mission.state == MISSION_COMPLETE:
        return False
    blocked = {"failed", "stranded"}
    productive = [
        d for d in swarm.drones
        if d.state not in blocked and not (d.battery.is_empty() and not d.can_charge_here())
    ]
    return not productive and len(swarm.game_map.mission_found) < len(swarm.game_map.mission_zones)


def draw_menu_screen(screen: pygame.Surface, selected: int, frame: int) -> list[tuple[str, pygame.Rect]]:
    screen.fill((5, 8, 15))
    font_title = get_font(34, bold=True)
    font_lg = get_font(config.FONT_TITLE, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = config.SCREEN_WIDTH // 2
    y = 145
    glow = int(35 + 25 * pulse(frame, 120))
    pygame.draw.circle(screen, (0, 130, 180), (cx, y + 10), 140 + glow, 1)
    draw_text(screen, "AUTONOMOUS DRONE SWARM", cx, y, font_title, config.C_UI_ACCENT, anchor="center")
    draw_text(screen, "mission-grade search, relay mesh, offline autonomy", cx, y + 42,
              font_md, config.C_UI_TEXT, anchor="center")

    items = [
        ("Start Mission", pygame.K_1),
        ("Demo Mode", pygame.K_2),
        ("Replay Viewer", pygame.K_3),
        ("Settings", pygame.K_4),
        ("Quit", pygame.K_5),
    ]
    buttons = []
    y = 275
    for idx, (label, key) in enumerate(items):
        rect = pygame.Rect(cx - 170, y + idx * 52, 340, 38)
        active = idx == selected
        bg = (18, 35, 50) if active else (13, 18, 30)
        border = config.C_UI_ACCENT if active else config.C_UI_BORDER
        draw_rounded_rect(screen, bg, rect, 8)
        draw_rounded_rect(screen, border, rect, 8, 1)
        draw_text(screen, f"{idx + 1}. {label}", rect.centerx, rect.y + 10,
                  font_lg, config.C_UI_TEXT if active else config.C_UI_BORDER, anchor="center")
        buttons.append((label, rect))

    draw_text(screen, "Keyboard: 1-5, Enter, arrows. Demo mode keeps normal survivor realism.",
              cx, config.SCREEN_HEIGHT - 86, font_md, config.C_UI_BORDER, anchor="center")
    return buttons


def draw_pause_screen(screen: pygame.Surface, mission, swarm, frame: int, demo_mode: bool):
    overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 175))
    screen.blit(overlay, (0, 0))
    font_xl = get_font(30, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = config.SCREEN_WIDTH // 2
    y = 190
    draw_text(screen, "MISSION PAUSED", cx, y, font_xl, config.C_UI_ACCENT, anchor="center")
    y += 52
    metrics = mission.metrics
    lines = [
        f"Coverage: {metrics.coverage_pct:.1f}%   Survivors: {len(swarm.game_map.mission_found)}/{len(swarm.game_map.mission_zones)}",
        f"Active drones: {metrics.active_drones}   Failed: {metrics.failed_drones}   Avg battery: {metrics.average_battery:.0f}%",
        f"Comm health: {metrics.communication_health * 100:.0f}%   Efficiency: {metrics.mission_efficiency:.1f}",
        f"Mode: {'Cinematic demo' if demo_mode else 'Operator'}",
        "P resume   R restart   E export replay   L load replay   ESC menu",
        "+/- zoom   arrows pan   SPACE follow drone   F/C/S/T/V/D overlays",
    ]
    for line in lines:
        draw_text(screen, line, cx, y, font_md, config.C_UI_TEXT, anchor="center")
        y += 24


def draw_end_screen(screen: pygame.Surface, mission, swarm, frame: int, failed: bool):
    overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 168))
    screen.blit(overlay, (0, 0))
    font_xl = get_font(30, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = config.SCREEN_WIDTH // 2
    y = 170
    title = "MISSION FAILURE" if failed else "MISSION SUCCESS"
    color = config.C_UI_DANGER if failed else config.C_UI_OK
    draw_text(screen, title, cx, y, font_xl, color, anchor="center")
    y += 50
    for line in mission.stats.summary_lines():
        draw_text(screen, line, cx, y, font_md, config.C_UI_TEXT, anchor="center")
        y += 22
    y += 12
    draw_text(screen, f"Coverage {mission.metrics.coverage_pct:.1f}%   Efficiency {mission.metrics.mission_efficiency:.1f}",
              cx, y, font_md, config.C_UI_ACCENT, anchor="center")
    y += 36
    draw_text(screen, "R restart   E export replay   ESC main menu",
              cx, y, font_md, config.C_UI_BORDER, anchor="center")


def draw_settings_screen(screen: pygame.Surface, selected: int, flags: dict, camera: Camera, frame: int):
    screen.fill((7, 10, 18))
    font_xl = get_font(28, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = config.SCREEN_WIDTH // 2
    y = 125
    draw_text(screen, "SETTINGS", cx, y, font_xl, config.C_UI_ACCENT, anchor="center")
    y += 64
    items = [
        ("Communication overlay", "show_comm"),
        ("Sensor rings", "show_sensor"),
        ("Drone trails", "show_trail"),
        ("Frontier overlay", "show_frontiers"),
        ("Reservation overlay", "show_reservations"),
        ("Decision labels", "show_decisions"),
        ("Heatmap overlay", "show_heatmap"),
    ]
    for idx, (label, key) in enumerate(items):
        state = "ON" if flags[key] else "OFF"
        color = config.C_UI_ACCENT if idx == selected else config.C_UI_TEXT
        draw_text(screen, f"{idx + 1}. {label:<24} {state}", cx - 190, y, font_md, color)
        y += 30
    y += 12
    draw_text(screen, f"Camera zoom {camera.target_zoom:.2f}   follow {'D' + str(camera.follow_id) if camera.follow_id is not None else 'OFF'}",
              cx - 190, y, font_md, config.C_UI_BORDER)
    y += 44
    draw_text(screen, "Enter/1-7 toggle   +/- zoom   SPACE cycle follow   ESC main menu",
              cx, y, font_md, config.C_UI_BORDER, anchor="center")


def draw_color_legend(screen: pygame.Surface, x: int, y: int):
    from core.drone import STATE_COLOR
    font = get_font(config.FONT_MONO_SM)
    entries = [
        ("SCAN", STATE_COLOR.get("scanning", config.C_STATE_SCANNING)),
        ("RTB", STATE_COLOR.get("returning", config.C_STATE_RETURNING)),
        ("CHARGE", STATE_COLOR.get("charging", config.C_STATE_CHARGING)),
        ("LOST", STATE_COLOR.get("lost_comm", config.C_STATE_LOST)),
        ("STRANDED", STATE_COLOR.get("stranded", config.C_STATE_STRANDED)),
    ]
    for label, color in entries:
        pygame.draw.rect(screen, color, pygame.Rect(x, y + 3, 10, 10))
        draw_text(screen, label, x + 15, y, font, config.C_UI_BORDER)
        x += 82


def draw_weather_overlay(surf: pygame.Surface, weather_type: str, frame: int):
    """Animated weather effects drawn over the map viewport."""
    if weather_type == "Clear":
        return

    viewport = pygame.Rect(config.MAP_OFFSET_X, config.MAP_OFFSET_Y,
                           config.MAP_PIXEL_W, config.MAP_PIXEL_H)
    if weather_type == "Stormy":
        # Random lightning flicker
        if random.random() < 0.005:
            overlay = pygame.Surface(
                (config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
            overlay.fill((210, 230, 255, 45))
            surf.blit(overlay, viewport.topleft)

    if weather_type in ("Windy", "Stormy"):
        # Horizontal streak lines simulating wind
        streak_surf = pygame.Surface(
            (config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
        for i in range(18 if weather_type == "Stormy" else 10):
            sy = random.randint(0, config.MAP_PIXEL_H)
            sx = (frame * (5 if weather_type == "Stormy" else 3) + i * 93) % (config.MAP_PIXEL_W + 120) - 120
            length = random.randint(28, 84)
            alpha = random.randint(18, 52)
            pygame.draw.line(streak_surf, (180, 200, 255, alpha),
                             (sx, sy), (sx + length, sy + random.randint(-2, 2)), 1)
        surf.blit(streak_surf, viewport.topleft)

    if weather_type in ("Cloudy", "Stormy"):
        # Very subtle dark vignette
        vign = pygame.Surface(
            (config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
        vign.fill((0, 0, 0, 24 if weather_type == "Cloudy" else 38))
        for i in range(6):
            x = int((frame * 0.25 + i * 190) % (config.MAP_PIXEL_W + 160) - 80)
            y = 35 + i * 95 % config.MAP_PIXEL_H
            pygame.draw.ellipse(vign, (180, 200, 230, 12), (x, y, 150, 44))
        surf.blit(vign, viewport.topleft)


def draw_mission_complete_screen(surf: pygame.Surface, mission, frame: int):
    """Semi-transparent overlay with mission statistics."""
    overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))

    font_xl = get_font(28, bold=True)
    font_lg = get_font(config.FONT_TITLE, bold=True)
    font_md = get_font(config.FONT_MONO_MD)

    cx = config.SCREEN_WIDTH // 2
    cy = config.SCREEN_HEIGHT // 2 - 100

    # Pulsing title
    p = pulse(frame, 60)
    title_color = lerp_color((0, 220, 120), (0, 180, 255), p)
    draw_text(surf, "★  MISSION COMPLETE  ★", cx, cy,
              font_xl, title_color, anchor="center")
    cy += 50

    for line in mission.stats.summary_lines():
        draw_text(surf, line, cx, cy, font_md, config.C_UI_TEXT, anchor="center")
        cy += 20

    cy += 20
    draw_text(surf, "Press [R] to restart or [ESC] to quit",
              cx, cy, font_lg, config.C_UI_BORDER, anchor="center")


def draw_swarm_debug_overlay(
    surf: pygame.Surface,
    swarm,
    show_frontiers: bool,
    show_reservations: bool,
    show_decisions: bool,
):
    """Draw optional AI-debug overlays in map-local coordinates."""
    font_sm = get_font(config.FONT_MONO_SM)

    if show_reservations:
        for col, row, step in swarm.reservations.debug_cells():
            x, y = swarm.game_map.cell_to_pixel(col, row)
            alpha = max(25, 120 - step * 4)
            color = (255, 80, 180, alpha)
            overlay = pygame.Surface((config.CELL_SIZE, config.CELL_SIZE), pygame.SRCALPHA)
            overlay.fill(color)
            surf.blit(overlay, (x - config.CELL_SIZE // 2, y - config.CELL_SIZE // 2))

    if show_frontiers:
        for frontier in swarm.frontiers.frontiers:
            x, y = swarm.game_map.cell_to_pixel(frontier.col, frontier.row)
            assigned = frontier.assigned_drone is not None
            color = (0, 255, 160) if assigned else (255, 220, 60)
            radius = 6 if assigned else 4
            pygame.draw.circle(surf, color, (x, y), radius, 2)
            label = f"F{frontier.frontier_id}"
            if assigned:
                label += f":D{frontier.assigned_drone}"
            draw_text(surf, label, x + 5, y - 12, font_sm, color)

        for info in swarm.game_map.survivor_debug(swarm.drones):
            col, row = info["cell"]
            x, y = swarm.game_map.cell_to_pixel(col, row)
            if info["found"]:
                color = (0, 255, 80)
                status = "FOUND"
            elif info["in_sensor"]:
                color = (255, 80, 80)
                status = "SENSOR"
            elif info["reachable"]:
                color = (255, 220, 60)
                status = "OK"
            else:
                color = (255, 0, 0)
                status = "BLOCKED"
            pygame.draw.circle(surf, color, (x, y), info["detect_radius"] * config.CELL_SIZE, 1)
            pygame.draw.circle(surf, color, (x, y), 5)
            draw_text(surf, f"S{info['idx']} {status}", x + 7, y + 4, font_sm, color)

    if show_decisions:
        for drone in swarm.drones:
            if not drone.decision:
                continue
            x, y = int(drone.px) + 10, int(drone.py) + 10
            text = drone.decision[:34]
            draw_text(surf, text, x, y, font_sm, (235, 235, 255))


def draw_comm_graph_overlay(surf: pygame.Surface, swarm):
    """Draw relay graph, weak links, relay anchors, and disconnected clusters."""
    manager = swarm.comm_manager()
    if manager is None:
        return
    font_sm = get_font(config.FONT_MONO_SM)
    base_x, base_y = swarm.game_map.cell_to_pixel(config.BASE_COL, config.BASE_ROW)
    by_id = {drone.drone_id: drone for drone in swarm.drones}

    # Base-to-drone links.
    for drone in swarm.drones:
        if -1 in drone.comm.connected_ids:
            pygame.draw.line(
                surf, (0, 230, 120),
                (base_x, base_y), (int(drone.px), int(drone.py)), 2,
            )

    # Relay tree links discovered by BFS from base.
    for child_id, parent_id in getattr(manager, "relay_links", []):
        child = by_id.get(child_id)
        parent = by_id.get(parent_id)
        if child is None or parent is None:
            continue
        pygame.draw.line(
            surf, (80, 180, 255),
            (int(child.px), int(child.py)), (int(parent.px), int(parent.py)), 2,
        )

    # Weak or disconnected drones.
    weak = set(getattr(manager, "weak_drone_ids", set()))
    for drone in swarm.drones:
        if drone.drone_id in weak:
            color = config.C_UI_WARN if drone.comm.is_connected else config.C_UI_DANGER
            pygame.draw.circle(surf, color, (int(drone.px), int(drone.py)), config.DRONE_RADIUS + 7, 2)
            draw_text(surf, "WEAK" if drone.comm.is_connected else "DISC",
                      int(drone.px) + 8, int(drone.py) - 18, font_sm, color)

        if drone.relay_anchor_active and drone.relay_anchor_cell is not None:
            ax, ay = swarm.game_map.cell_to_pixel(*drone.relay_anchor_cell)
            pygame.draw.circle(surf, (180, 230, 255), (ax, ay), 7, 2)
            pygame.draw.line(surf, (180, 230, 255), (int(drone.px), int(drone.py)), (ax, ay), 1)
            draw_text(surf, f"R{drone.drone_id}", ax + 7, ay + 2, font_sm, (180, 230, 255))

    # Disconnected clusters.
    for idx, cluster in enumerate(getattr(manager, "disconnected_clusters", [])):
        points = [(int(by_id[d].px), int(by_id[d].py)) for d in cluster if d in by_id]
        if not points:
            continue
        cx = sum(p[0] for p in points) // len(points)
        cy = sum(p[1] for p in points) // len(points)
        pygame.draw.circle(surf, config.C_UI_DANGER, (cx, cy), 18 + len(points) * 4, 1)
        draw_text(surf, f"CL{idx}:{len(points)}", cx + 10, cy + 10, font_sm, config.C_UI_DANGER)


def draw_docking_debug_line(screen: pygame.Surface, swarm):
    font = get_font(config.FONT_MONO_SM)
    parts = []
    for drone in swarm.drones:
        dist_cells = drone.distance_to_base() / config.CELL_SIZE
        dock = "DOCK" if drone.can_charge_here() else "FIELD"
        battery_state = "CHG" if drone.battery.charging else ("EMP" if drone.battery.is_empty() else "BAT")
        charge_reason = drone.charging_status()
        parts.append(
            f"D{drone.drone_id}:{dist_cells:.0f}c {dock} "
            f"{battery_state}{drone.battery.level:.0f}% {charge_reason}"
        )
    for row, start in enumerate(range(0, len(parts), 4)):
        line = " | ".join(parts[start:start + 4])
        draw_text(screen, line[:190], config.MAP_OFFSET_X + 180, 44 + row * 12, font, config.C_UI_BORDER)


def draw_lost_comm_debug_line(screen: pygame.Surface, swarm):
    snapshot = getattr(swarm, "last_comm_snapshot", {}) or {}
    metrics = swarm.comm_debug_metrics() if hasattr(swarm, "comm_debug_metrics") else {}
    summary = (
        f"COMM {snapshot.get('connected', len(swarm.drones))}/{snapshot.get('total', len(swarm.drones))} "
        f"weak:{len(snapshot.get('weak', []))} "
        f"clusters:{len(snapshot.get('disconnected_clusters', []))} "
        f"relay:{metrics.get('relay_drones', 0)} exp:{metrics.get('explorer_drones', 0)} "
        f"fd:{metrics.get('avg_frontier_distance', 0.0):.1f} "
        f"grow:{metrics.get('coverage_growth_per_min', 0.0) * 100:.1f}%/m "
        f"relax:{metrics.get('comm_risk_relaxation', 0.0):.2f}"
    )
    tracked = [
        drone for drone in swarm.drones
        if (drone.comm_mode_label() != "ONLINE" or
            drone.comm.frames_since_contact > 0)
    ]
    font = get_font(config.FONT_MONO_SM)
    y = config.MAP_OFFSET_Y + 6
    if not tracked:
        draw_text(screen, summary + " ONLINE", config.MAP_OFFSET_X + 12, y, font, config.C_UI_OK)
        return
    for row, start in enumerate(range(0, len(tracked), 2)):
        line = " | ".join(
            drone.lost_comm_debug_status()[:76]
            for drone in tracked[start:start + 2]
        )
        rect = pygame.Rect(config.MAP_OFFSET_X + 8, y + row * 13 - 2, 720, 13)
        pygame.draw.rect(screen, (8, 10, 18), rect)
        pygame.draw.rect(screen, config.C_UI_WARN, rect, 1)
        draw_text(screen, line, config.MAP_OFFSET_X + 12, y + row * 13, font, config.C_UI_WARN)


# ──────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────

def main():
    pygame.init()
    pygame.display.set_caption(config.WINDOW_TITLE)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    clock  = pygame.time.Clock()

    # ── Init simulation ──────────────────────
    game_map, swarm, mission, seed = make_simulation()
    dashboard = Dashboard()
    minimap   = Minimap()

    # ── Render surfaces ──────────────────────
    # Map surface (world-space, offset to screen via MAP_OFFSET_*)
    map_surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))

    # ── State flags ──────────────────────────
    show_heatmap = False
    show_comm    = True
    show_sensor  = True
    show_trail   = True
    show_frontiers = False
    show_reservations = False
    show_decisions = False

    frame        = 0
    fps_display  = 60
    fps_timer    = 0

    particles: list[Particle] = []
    prev_found   = set()

    # ──────────────────────────────────────────
    # Game loop
    # ──────────────────────────────────────────
    running = True
    while running:

        # ── Events ──────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game_map, swarm, mission, seed = make_simulation()
                    dashboard = Dashboard()
                    minimap   = Minimap()
                    particles.clear()
                    prev_found.clear()
                    frame = 0
                elif event.key == pygame.K_h:
                    show_heatmap = not show_heatmap
                elif event.key == pygame.K_c:
                    show_comm = not show_comm
                elif event.key == pygame.K_s:
                    show_sensor = not show_sensor
                elif event.key == pygame.K_t:
                    show_trail = not show_trail
                elif event.key == pygame.K_f:
                    show_frontiers = not show_frontiers
                elif event.key == pygame.K_v:
                    show_reservations = not show_reservations
                elif event.key == pygame.K_d:
                    show_decisions = not show_decisions
                elif event.key == pygame.K_y:
                    swarm.rescue_stranded_to_base()
                elif event.key == pygame.K_e:
                    try:
                        mission.export_replay()
                    except Exception as exc:
                        swarm.alerts.append(f"Replay export failed: {exc}")
                elif event.key == pygame.K_l:
                    try:
                        mission.load_last_replay()
                    except Exception as exc:
                        swarm.alerts.append(f"Replay load failed: {exc}")

        # ── Simulation step ──────────────────────
        if mission.state != MISSION_COMPLETE:
            mission.update()

        # Collect alerts for dashboard
        dashboard.add_alerts(swarm.active_alerts())

        # Spawn particles on mission discovery
        new_found = game_map.mission_found - prev_found
        for mz_idx in new_found:
            mz = game_map.mission_zones[mz_idx]
            bx, by = game_map.cell_to_pixel(mz.col, mz.row)
            for _ in range(40):
                particles.append(Particle(
                    bx + config.MAP_OFFSET_X,
                    by + config.MAP_OFFSET_Y))
        prev_found = set(game_map.mission_found)

        # Update particles
        particles = [p for p in particles if p.life > 0]
        for p in particles:
            p.update()

        # FPS measurement
        fps_timer += 1
        if fps_timer >= 20:
            fps_timer   = 0
            fps_display = int(clock.get_fps())

        # ── Render ──────────────────────────────
        screen.fill(config.C_BG)

        # 1. Map background (tile surface with fog-of-war)
        tile_surf = game_map.get_tile_surface()
        map_surf.blit(tile_surf, (0, 0))

        # 2. Heatmap overlay
        if show_heatmap:
            game_map.draw_heatmap_overlay(map_surf)

        # 3. Mission zones
        game_map.draw_mission_zones(map_surf)

        # 4. Base station
        game_map.draw_base(map_surf)

        draw_swarm_debug_overlay(
            map_surf, swarm,
            show_frontiers=show_frontiers,
            show_reservations=show_reservations,
            show_decisions=False,
        )

        # 5. Communication links (drone-to-drone)
        if show_comm:
            comm_surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
            for drone in swarm.drones:
                drone.draw_comm_links(comm_surf, swarm.drones)
            draw_comm_graph_overlay(comm_surf, swarm)
            map_surf.blit(comm_surf, (0, 0))

        # 6. Drones
        for drone in swarm.drones:
            drone.draw(map_surf, show_sensor=show_sensor, show_trail=show_trail,
                       show_comm=show_comm)

        # 7. Drone ID labels
        font_sm = get_font(config.FONT_MONO_SM)
        for drone in swarm.drones:
            lx = int(drone.px) + config.DRONE_RADIUS + 2
            ly = int(drone.py) - config.DRONE_RADIUS - 1
            draw_text(map_surf, f"D{drone.drone_id}", lx, ly, font_sm, (220, 220, 255))

        if show_decisions:
            draw_swarm_debug_overlay(
                map_surf, swarm,
                show_frontiers=False,
                show_reservations=False,
                show_decisions=True,
            )

        # 8. Blit map_surf to screen with offset
        screen.blit(map_surf, (config.MAP_OFFSET_X, config.MAP_OFFSET_Y))

        # 9. Map border
        pygame.draw.rect(screen, config.C_UI_BORDER,
                         (config.MAP_OFFSET_X, config.MAP_OFFSET_Y,
                          config.MAP_PIXEL_W, config.MAP_PIXEL_H), 1)

        # 10. Weather effects
        draw_weather_overlay(screen, mission.weather.current, frame)

        # 11. Particles
        for p in particles:
            p.draw(screen)

        # 12. Minimap (title-bar area, above map)
        minimap.draw(screen, game_map, swarm.drones, frame)

        # 13. Top title bar info (right side of minimap)
        font_title = get_font(config.FONT_TITLE, bold=True)
        font_md    = get_font(config.FONT_MONO_MD)
        title_x = config.MAP_OFFSET_X + 180
        draw_text(screen, "AUTONOMOUS DRONE SWARM SIMULATOR",
                  title_x, 8, font_title, config.C_UI_ACCENT)
        draw_text(screen, f"Seed: {seed}   Drones: {config.NUM_DRONES}   "
                          f"Map: {config.MAP_COLS}×{config.MAP_ROWS}",
                  title_x, 28, font_md, config.C_UI_TEXT)

        draw_text(screen, f"[F]Frontiers {'ON' if show_frontiers else 'OFF'}  "
                          f"[V]Reservations {'ON' if show_reservations else 'OFF'}  "
                          f"[D]Decisions {'ON' if show_decisions else 'OFF'}  [Y]Rescue [E]Export [L]Load",
                  title_x + 420, 28, font_md, config.C_UI_BORDER)
        draw_docking_debug_line(screen, swarm)
        draw_lost_comm_debug_line(screen, swarm)

        # 14. Dashboard panel (right side)
        dashboard.draw(screen, swarm, mission, fps_display, frame,
                       show_heatmap, show_comm)

        # 15. Mission complete overlay
        if mission.state == MISSION_COMPLETE:
            draw_mission_complete_screen(screen, mission, frame)

        pygame.display.flip()
        clock.tick(config.TARGET_FPS)
        frame += 1

    pygame.quit()
    sys.exit(0)


def render_simulation_frame(screen, map_surf, camera, game_map, swarm, mission,
                            dashboard, minimap, particles, flags, fps_display,
                            frame, seed, demo_mode):
    screen.fill(config.C_BG)
    map_surf.blit(game_map.get_tile_surface(), (0, 0))

    if flags["show_heatmap"]:
        game_map.draw_heatmap_overlay(map_surf)

    game_map.draw_mission_zones(map_surf)
    game_map.draw_base(map_surf)
    draw_swarm_debug_overlay(
        map_surf, swarm,
        show_frontiers=flags["show_frontiers"],
        show_reservations=flags["show_reservations"],
        show_decisions=False,
    )

    if flags["show_comm"]:
        comm_surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H), pygame.SRCALPHA)
        for drone in swarm.drones:
            drone.draw_comm_links(comm_surf, swarm.drones, frame)
        draw_comm_graph_overlay(comm_surf, swarm)
        map_surf.blit(comm_surf, (0, 0))

    for drone in swarm.drones:
        drone.draw(
            map_surf,
            show_sensor=flags["show_sensor"],
            show_trail=flags["show_trail"],
            show_comm=flags["show_comm"],
            frame=frame,
        )

    font_sm = get_font(config.FONT_MONO_SM)
    for drone in swarm.drones:
        draw_text(
            map_surf,
            f"D{drone.drone_id}",
            int(drone.px) + config.DRONE_RADIUS + 2,
            int(drone.py) - config.DRONE_RADIUS - 1,
            font_sm,
            (220, 220, 255),
        )

    if flags["show_decisions"]:
        draw_swarm_debug_overlay(
            map_surf, swarm,
            show_frontiers=False,
            show_reservations=False,
            show_decisions=True,
        )

    for p in particles:
        p.draw(map_surf)

    screen.blit(camera.render(map_surf), (config.MAP_OFFSET_X, config.MAP_OFFSET_Y))
    pygame.draw.rect(screen, config.C_UI_BORDER,
                     (config.MAP_OFFSET_X, config.MAP_OFFSET_Y,
                      config.MAP_PIXEL_W, config.MAP_PIXEL_H), 1)
    draw_weather_overlay(screen, mission.weather.current, frame)
    minimap.draw(screen, game_map, swarm.drones, frame, camera)

    font_title = get_font(config.FONT_TITLE, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    title_x = config.MAP_OFFSET_X + 180
    mode_label = "DEMO" if demo_mode else ("REPLAY" if mission.replay_playback_active else "MISSION")
    follow = f"D{camera.follow_id}" if camera.follow_id is not None else "OFF"
    draw_text(screen, "AUTONOMOUS DRONE SWARM SIMULATOR",
              title_x, 8, font_title, config.C_UI_ACCENT)
    draw_text(screen, f"Seed: {seed}   Mode: {mode_label}   Zoom: {camera.zoom:.2f}   Follow: {follow}",
              title_x, 28, font_md, config.C_UI_TEXT)
    draw_text(screen, f"[P]Pause [F]Frontiers {'ON' if flags['show_frontiers'] else 'OFF'}  "
                      f"[V]Reservations {'ON' if flags['show_reservations'] else 'OFF'}  "
                      f"[D]Decisions {'ON' if flags['show_decisions'] else 'OFF'}  "
                      f"[Space]Follow [+/-]Zoom",
              title_x + 420, 28, font_md, config.C_UI_BORDER)
    draw_docking_debug_line(screen, swarm)
    draw_lost_comm_debug_line(screen, swarm)
    draw_color_legend(screen, config.MAP_OFFSET_X + 10, config.MAP_OFFSET_Y + config.MAP_PIXEL_H + 6)
    dashboard.draw(screen, swarm, mission, fps_display, frame,
                   flags["show_heatmap"], flags["show_comm"])


def run_app():
    pygame.init()
    pygame.display.set_caption(config.WINDOW_TITLE)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    game_map, swarm, mission, seed = make_simulation()
    dashboard = Dashboard()
    minimap = Minimap()
    map_surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
    camera = Camera()
    flags = {
        "show_heatmap": False,
        "show_comm": True,
        "show_sensor": True,
        "show_trail": True,
        "show_frontiers": False,
        "show_reservations": False,
        "show_decisions": False,
    }
    frame = 0
    fps_display = 60
    fps_timer = 0
    particles: list[Particle] = []
    prev_found = set()
    app_state = APP_MENU
    menu_selected = 0
    settings_selected = 0
    demo_mode = False
    mission_failed = False

    def reset_simulation(cinematic: bool = False):
        nonlocal game_map, swarm, mission, seed, dashboard, minimap
        nonlocal particles, prev_found, frame, demo_mode, mission_failed
        game_map, swarm, mission, seed = make_simulation()
        dashboard = Dashboard()
        minimap = Minimap()
        particles = []
        prev_found = set()
        frame = 0
        demo_mode = cinematic
        mission_failed = False
        camera.reset()
        if cinematic:
            camera.set_zoom(1.25)
            flags.update({
                "show_comm": True,
                "show_sensor": True,
                "show_trail": True,
                "show_frontiers": True,
                "show_reservations": False,
                "show_decisions": False,
            })

    def handle_menu_action(label: str) -> bool:
        nonlocal app_state, demo_mode
        if label == "Start Mission":
            reset_simulation(False)
            app_state = APP_RUNNING
        elif label == "Demo Mode":
            reset_simulation(True)
            app_state = APP_RUNNING
        elif label == "Replay Viewer":
            reset_simulation(False)
            demo_mode = False
            try:
                mission.load_last_replay()
                camera.set_zoom(1.05)
            except Exception as exc:
                swarm.alerts.append(f"Replay load failed: {exc}")
            app_state = APP_RUNNING
        elif label == "Settings":
            app_state = APP_SETTINGS
        elif label == "Quit":
            return False
        return True

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            if event.type == pygame.MOUSEWHEEL and app_state in (APP_RUNNING, APP_PAUSED, APP_END):
                camera.zoom_by(0.12 * event.y)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and app_state == APP_MENU:
                for label, rect in draw_menu_screen(screen, menu_selected, frame):
                    if rect.collidepoint(event.pos):
                        running = handle_menu_action(label)
                        break
                continue
            if event.type != pygame.KEYDOWN:
                continue

            if app_state == APP_MENU:
                labels = ["Start Mission", "Demo Mode", "Replay Viewer", "Settings", "Quit"]
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    menu_selected = (menu_selected + 1) % len(labels)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    menu_selected = (menu_selected - 1) % len(labels)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    running = handle_menu_action(labels[menu_selected])
                elif pygame.K_1 <= event.key <= pygame.K_5:
                    running = handle_menu_action(labels[event.key - pygame.K_1])
                continue

            if app_state == APP_SETTINGS:
                keys = list(flags.keys())
                if event.key == pygame.K_ESCAPE:
                    app_state = APP_MENU
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    settings_selected = (settings_selected + 1) % len(keys)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    settings_selected = (settings_selected - 1) % len(keys)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    flags[keys[settings_selected]] = not flags[keys[settings_selected]]
                elif pygame.K_1 <= event.key <= pygame.K_7:
                    idx = event.key - pygame.K_1
                    if idx < len(keys):
                        flags[keys[idx]] = not flags[keys[idx]]
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    camera.zoom_by(0.15)
                elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                    camera.zoom_by(-0.15)
                continue

            if event.key == pygame.K_ESCAPE:
                app_state = APP_PAUSED if app_state == APP_RUNNING else APP_MENU
            elif event.key == pygame.K_p:
                app_state = APP_PAUSED if app_state == APP_RUNNING else APP_RUNNING
            elif event.key == pygame.K_m:
                app_state = APP_MENU
            elif event.key == pygame.K_r:
                reset_simulation(demo_mode)
                app_state = APP_RUNNING
            elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                camera.zoom_by(0.15)
            elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                camera.zoom_by(-0.15)
            elif event.key == pygame.K_SPACE:
                camera.follow_next(swarm.drones)
            elif event.key == pygame.K_q:
                camera.follow_id = None
                camera.set_zoom(1.0)
            elif event.key == pygame.K_h:
                flags["show_heatmap"] = not flags["show_heatmap"]
            elif event.key == pygame.K_c:
                flags["show_comm"] = not flags["show_comm"]
            elif event.key == pygame.K_s:
                flags["show_sensor"] = not flags["show_sensor"]
            elif event.key == pygame.K_t:
                flags["show_trail"] = not flags["show_trail"]
            elif event.key == pygame.K_f:
                flags["show_frontiers"] = not flags["show_frontiers"]
            elif event.key == pygame.K_v:
                flags["show_reservations"] = not flags["show_reservations"]
            elif event.key == pygame.K_d:
                flags["show_decisions"] = not flags["show_decisions"]
            elif event.key == pygame.K_y:
                swarm.rescue_stranded_to_base()
            elif event.key == pygame.K_e:
                try:
                    mission.export_replay()
                except Exception as exc:
                    swarm.alerts.append(f"Replay export failed: {exc}")
            elif event.key == pygame.K_l:
                try:
                    mission.load_last_replay()
                except Exception as exc:
                    swarm.alerts.append(f"Replay load failed: {exc}")

        if app_state == APP_MENU:
            draw_menu_screen(screen, menu_selected, frame)
            pygame.display.flip()
            clock.tick(config.TARGET_FPS)
            frame += 1
            continue
        if app_state == APP_SETTINGS:
            draw_settings_screen(screen, settings_selected, flags, camera, frame)
            pygame.display.flip()
            clock.tick(config.TARGET_FPS)
            frame += 1
            continue

        if app_state == APP_RUNNING and mission.state != MISSION_COMPLETE and not mission_failed:
            mission.update()
            mission_failed = is_mission_failed(swarm, mission)
            if mission_failed or mission.state == MISSION_COMPLETE:
                app_state = APP_END

        if demo_mode and app_state == APP_RUNNING:
            flags["show_comm"] = True
            flags["show_trail"] = True
            flags["show_sensor"] = frame % 900 < 690
            flags["show_frontiers"] = frame % 960 < 300
            flags["show_reservations"] = frame % 1500 < 240
            active = [d for d in swarm.drones if d.state in ("scanning", "lost_comm", "returning")]
            if active and frame % 420 == 0:
                camera.follow_drone(random.choice(active).drone_id, 1.45)
            if mission.replay_playback_active:
                camera.set_zoom(1.15)

        keys = pygame.key.get_pressed() if app_state in (APP_RUNNING, APP_PAUSED, APP_END) else None
        camera.update(swarm.drones, keys)
        dashboard.add_alerts(swarm.active_alerts())

        new_found = game_map.mission_found - prev_found
        for mz_idx in new_found:
            mz = game_map.mission_zones[mz_idx]
            bx, by = game_map.cell_to_pixel(mz.col, mz.row)
            for _ in range(70):
                particles.append(Particle(bx, by))
            finder = next((d.drone_id for d in swarm.drones if mz_idx in d.mission_found), 0)
            camera.follow_drone(finder, 1.65)
        prev_found = set(game_map.mission_found)

        particles = [p for p in particles if p.life > 0]
        for p in particles:
            p.update()

        fps_timer += 1
        if fps_timer >= 20:
            fps_timer = 0
            fps_display = int(clock.get_fps())

        render_simulation_frame(screen, map_surf, camera, game_map, swarm, mission,
                                dashboard, minimap, particles, flags, fps_display,
                                frame, seed, demo_mode)
        if app_state == APP_PAUSED:
            draw_pause_screen(screen, mission, swarm, frame, demo_mode)
        elif app_state == APP_END:
            draw_end_screen(screen, mission, swarm, frame, mission_failed)

        pygame.display.flip()
        clock.tick(config.TARGET_FPS)
        frame += 1

    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    run_app()
