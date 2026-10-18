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
from core.simulation import make_simulation
from core.utils import world_to_screen, get_font, draw_text, draw_rounded_rect, pulse, lerp_color, clamp
from ui.dashboard import Dashboard
from ui.console import SETTINGS, Layout, MIN_SIZE, select_at
from ui.minimap import Minimap
from ui.replay_view import draw_replay
# Compatibility exports; rendering implementation belongs to presentation.
from ui.presentation import (
    Particle,
    Camera,
    draw_menu_screen,
    draw_pause_screen,
    draw_end_screen,
    draw_settings_screen,
    draw_color_legend,
    draw_weather_overlay,
    draw_mission_complete_screen,
    draw_swarm_debug_overlay,
    draw_comm_graph_overlay,
    draw_docking_debug_line,
    draw_lost_comm_debug_line,
    render_simulation_frame,
)


APP_MENU = "menu"
APP_RUNNING = "running"
APP_PAUSED = "paused"
APP_SETTINGS = "settings"
APP_END = "end"


def is_mission_failed(swarm, mission) -> bool:
    # FAILED drones recover and STRANDED drones allow operator rescue. ADSS has
    # no irreversible failure/time-limit policy; blockage is not an outcome.
    return False


# ──────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────

def main():
    """Compatibility entry point for the same graphical controller."""
    run_app()


def run_app():
    pygame.init()
    pygame.display.set_caption(config.WINDOW_TITLE)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    game_map, swarm, mission, seed = make_simulation()
    dashboard = Dashboard()
    minimap = Minimap()
    map_surf = pygame.Surface((config.MAP_PIXEL_W, config.MAP_PIXEL_H))
    camera = Camera()
    flags = {
        "show_heatmap": False,
        "show_comm": True,
        "show_sensor": False,
        "show_trail": False,
        "show_frontiers": False,
        "show_reservations": False,
        "show_decisions": False,
        "show_dashboard": True, "show_events": True, "show_minimap": True, "show_truth": False,
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
                dashboard.message = f"Replay load failed: {exc}"
                app_state = APP_MENU
                return True
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
            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((max(MIN_SIZE[0], event.w), max(MIN_SIZE[1], event.h)), pygame.RESIZABLE)
                continue
            if event.type == pygame.KEYDOWN and (event.key in (pygame.K_F1, pygame.K_QUESTION) or getattr(event, 'unicode', '') == '?'):
                dashboard.help_visible = not getattr(dashboard, 'help_visible', False)
                continue
            if mission.replay_playback_active and app_state in (APP_RUNNING, APP_PAUSED, APP_END):
                from ui.replay_view import handle_replay_input
                if handle_replay_input(event, mission.replay_player, screen.get_size()):
                    continue
            if event.type == pygame.MOUSEBUTTONDOWN and app_state in (APP_RUNNING, APP_PAUSED, APP_END):
                layout = Layout.for_size(screen.get_size(), flags.get('show_dashboard', True), flags.get('show_events', True))
                if event.button == 3:
                    dashboard.selected_id = None
                elif event.button == 1:
                    mini = getattr(dashboard, 'minimap_rect', None)
                    if mini is not None and mini.collidepoint(event.pos):
                        camera.follow_id = None
                        camera.target_x = (event.pos[0]-mini.x)/mini.w*config.MAP_PIXEL_W - config.MAP_PIXEL_W/max(1,camera.target_zoom)/2
                        camera.target_y = (event.pos[1]-mini.y)/mini.h*config.MAP_PIXEL_H - config.MAP_PIXEL_H/max(1,camera.target_zoom)/2
                        camera._clamp_targets()
                        continue
                    selected = next((i for i, rect in getattr(dashboard, 'drone_rects', {}).items() if rect.collidepoint(event.pos)), None)
                    if selected is None:
                        selected = select_at(event.pos, swarm.drones, camera, layout.viewport)
                    dashboard.selected_id = selected
                    dashboard.detail_scroll = 0
                continue
            if event.type == pygame.MOUSEWHEEL and app_state in (APP_RUNNING, APP_PAUSED, APP_END):
                layout = Layout.for_size(screen.get_size(), flags.get('show_dashboard', True), flags.get('show_events', True))
                if flags.get('show_dashboard', True) and layout.sidebar.collidepoint(pygame.mouse.get_pos()):
                    dashboard.detail_scroll = max(0, min(11, getattr(dashboard, 'detail_scroll', 0) - event.y))
                else:
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
                keys = [key for label, key in SETTINGS]
                if event.key == pygame.K_ESCAPE:
                    app_state = APP_MENU
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    settings_selected = (settings_selected + 1) % len(keys)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    settings_selected = (settings_selected - 1) % len(keys)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    flags[keys[settings_selected]] = not flags[keys[settings_selected]]
                elif pygame.K_1 <= event.key <= pygame.K_9:
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
                camera.reset()
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
            elif event.key in (pygame.K_b, pygame.K_n, pygame.K_j, pygame.K_g):
                key = {pygame.K_b:'show_dashboard', pygame.K_n:'show_minimap', pygame.K_j:'show_events', pygame.K_g:'show_truth'}[event.key]
                flags[key] = not flags[key]
            elif event.key == pygame.K_i:
                dashboard.message = mission.experiment.identity
            elif event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                step = 1 if event.key == pygame.K_RIGHTBRACKET else -1
                dashboard.fleet_page = (getattr(dashboard, 'fleet_page', 0) + step) % max(1, (len(swarm.drones)+7)//8)
            elif event.key == pygame.K_y:
                if not mission.replay_playback_active:
                    swarm.rescue_stranded_to_base()
            elif event.key == pygame.K_e:
                try:
                    dashboard.message = "Saved replay: " + str(mission.export_replay())
                except Exception as exc:
                    dashboard.message = f"Replay export failed: {exc}"
            elif event.key == pygame.K_l:
                try:
                    mission.load_last_replay()
                except Exception as exc:
                    dashboard.message = f"Replay load failed: {exc}"

        if app_state == APP_MENU:
            draw_menu_screen(screen, menu_selected, frame)
            if getattr(dashboard, 'message', ''):
                from ui.console import text, WARN
                text(screen, dashboard.message, 25, screen.get_height()-35, 12, WARN, width=screen.get_width()-50)
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

        if mission.replay_playback_active:
            if app_state == APP_RUNNING:
                mission.update()
            draw_replay(screen, mission.replay_player, app_state != APP_RUNNING)
            if getattr(dashboard, 'help_visible', False):
                from ui.console import draw_help
                draw_help(screen)
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
        dashboard.app_status = app_state.upper()

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
