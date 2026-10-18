"""Live presentation helpers. They observe simulation state, never advance it.

The application owns display lifecycle, input, pause and update scheduling.
Map/Drone compatibility draw methods and their visual caches remain in core.
"""
import math
import random
import pygame
import config
from core.utils import world_to_screen, get_font, draw_text, draw_rounded_rect, pulse, lerp_color, clamp
from ui.replay_view import draw_replay
from ui.console import SETTINGS, draw_console


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


def draw_menu_screen(screen: pygame.Surface, selected: int, frame: int) -> list[tuple[str, pygame.Rect]]:
    screen.fill((5, 8, 15))
    font_title = get_font(34, bold=True)
    font_lg = get_font(config.FONT_TITLE, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = screen.get_width() // 2
    y = 145
    glow = 0
    pygame.draw.line(screen, (52, 68, 85), (cx - 240, y + 90), (cx + 240, y + 90))
    draw_text(screen, "AUTONOMOUS DRONE SWARM", cx, y, font_title, config.C_UI_ACCENT, anchor="center")
    draw_text(screen, "Search / coordination / energy / connectivity", cx, y + 42,
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
        draw_text(screen, f"{idx + 1}. {label}", rect.centerx, rect.centery,
                  font_lg, config.C_UI_TEXT if active else (160, 178, 194), anchor="center")
        buttons.append((label, rect))

    draw_text(screen, "1-5 / arrows / Enter to start. Demo changes camera only. Fixed simulation ticks.",
              cx, screen.get_height() - 64, font_md, (160, 178, 194), anchor="center")
    return buttons


def draw_pause_screen(screen: pygame.Surface, mission, swarm, frame: int, demo_mode: bool):
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 175))
    screen.blit(overlay, (0, 0))
    font_xl = get_font(30, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = screen.get_width() // 2
    y = 190
    draw_text(screen, "MISSION PAUSED", cx, y, font_xl, config.C_UI_ACCENT, anchor="center")
    y += 52
    metrics = mission.metrics
    lines = [
        f"Coverage: {metrics.coverage_pct:.1f}%   Survivors: {len(swarm.game_map.mission_found)}/{len(swarm.game_map.mission_zones)}",
        f"Active drones: {metrics.active_drones}   Failed: {metrics.failed_drones}   Avg battery: {metrics.average_battery:.0f}%",
        f"Comm health: {metrics.communication_health * 100:.0f}%   Heuristic score: {metrics.mission_efficiency:.1f}",
        f"Mode: {'Cinematic demo' if demo_mode else 'Operator'}",
        "P resume   R restart   E export replay   L load replay   ESC menu",
        "+/- zoom   arrows pan   SPACE follow drone   F/C/S/T/V/D overlays",
    ]
    for line in lines:
        draw_text(screen, line, cx, y, font_md, config.C_UI_TEXT, anchor="center")
        y += 24


def draw_end_screen(screen: pygame.Surface, mission, swarm, frame: int, failed: bool):
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 168))
    screen.blit(overlay, (0, 0))
    font_xl = get_font(30, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = screen.get_width() // 2
    y = 170
    title = "MISSION FAILURE" if failed else "MISSION SUCCESS"
    color = config.C_UI_DANGER if failed else config.C_UI_OK
    draw_text(screen, title, cx, y, font_xl, color, anchor="center")
    y += 50
    for line in mission.stats.summary_lines():
        draw_text(screen, line, cx, y, font_md, config.C_UI_TEXT, anchor="center")
        y += 22
    y += 12
    draw_text(screen, f"Coverage {mission.metrics.coverage_pct:.1f}%   Heuristic score {mission.metrics.mission_efficiency:.1f}",
              cx, y, font_md, config.C_UI_ACCENT, anchor="center")
    y += 36
    draw_text(screen, "R restart   E export replay   ESC main menu",
              cx, y, font_md, config.C_UI_BORDER, anchor="center")


def draw_settings_screen(screen: pygame.Surface, selected: int, flags: dict, camera: Camera, frame: int):
    screen.fill((7, 10, 18))
    font_xl = get_font(28, bold=True)
    font_md = get_font(config.FONT_MONO_MD)
    cx = screen.get_width() // 2
    y = 70
    draw_text(screen, "PRESENTATION SETTINGS", cx, y, font_xl, config.C_UI_ACCENT, anchor="center")
    y += 64
    items = SETTINGS
    for idx, (label, key) in enumerate(items):
        state = "ON" if flags.get(key, key in ("show_dashboard", "show_events", "show_minimap")) else "OFF"
        color = config.C_UI_ACCENT if idx == selected else config.C_UI_TEXT
        draw_text(screen, f"{idx + 1}. {label:<24} {state}", cx - 190, y, font_md, color)
        y += 32
    y += 12
    draw_text(screen, f"Camera zoom {camera.target_zoom:.2f}   follow {'D' + str(camera.follow_id) if camera.follow_id is not None else 'OFF'}",
              cx - 190, y, font_md, (160, 178, 194))
    y += 30
    draw_text(screen, "Active experiment is immutable. These controls change presentation only.",
              cx, y, font_md, (160, 178, 194), anchor="center")
    y += 30
    draw_text(screen, "Arrows select / Enter toggle | 1-9 shortcuts | ESC menu",
              cx, y, font_md, (160, 178, 194), anchor="center")


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
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))

    font_xl = get_font(28, bold=True)
    font_lg = get_font(config.FONT_TITLE, bold=True)
    font_md = get_font(config.FONT_MONO_MD)

    cx = screen.get_width() // 2
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
            f"{battery_state}{100*drone.battery.pct:.0f}% {charge_reason}"
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


def render_simulation_frame(screen, map_surf, camera, game_map, swarm, mission,
                            dashboard, minimap, particles, flags, fps_display,
                            frame, seed, demo_mode):
    if mission.replay_playback_active:
        draw_replay(screen, mission.replay_player)
        return
    draw_console(screen, map_surf, camera, game_map, swarm, mission,
                 dashboard, flags, fps_display, seed)
