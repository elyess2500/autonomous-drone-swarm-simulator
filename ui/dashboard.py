"""
ui/dashboard.py - Real-time HUD overlay.

Renders:
  - Title bar with FPS, weather, mission clock
  - Drone status cards (state, battery bar, signal icon)
  - Mission progress bar
  - Active alerts log
  - Sector completion grid
  - Controls legend
"""

import pygame
import config
from core.utils import (draw_text, draw_bar, draw_panel, draw_rounded_rect,
                         get_font, pulse, lerp_color, clamp)
from core.drone import STATE_COLOR, IDLE, SCANNING, RETURNING, CHARGING, FAILED, LOST_COMM, STRANDED


# Panel layout constants
DASH_X  = config.MAP_OFFSET_X + config.MAP_PIXEL_W + 8   # left edge of dashboard
DASH_Y  = config.MAP_OFFSET_Y
DASH_W  = config.SCREEN_WIDTH - DASH_X - 8
DASH_H  = config.SCREEN_HEIGHT - DASH_Y - 8


class Dashboard:
    """
    Stateless renderer — call draw() each frame with current simulation state.
    """

    def __init__(self):
        self._alert_log: list[str] = []   # rolling log of alerts
        self._alert_max = 12
        self._metric_anim: dict[str, float] = {}

    # ──────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────

    def add_alerts(self, alerts: list[str]):
        for a in alerts:
            if a not in self._alert_log[-3:]:   # de-duplicate recent
                self._alert_log.append(a)
        # Trim
        if len(self._alert_log) > self._alert_max:
            self._alert_log = self._alert_log[-self._alert_max:]

    def draw(self, surf: pygame.Surface, swarm, mission, fps: int, frame: int,
             show_heatmap: bool, show_comm: bool):
        """
        Parameters
        ----------
        surf     : main screen surface
        swarm    : Swarm instance
        mission  : Mission instance
        fps      : measured FPS
        frame    : current frame number
        """
        x, y = DASH_X, DASH_Y
        w    = DASH_W

        # Background panel
        pygame.draw.rect(surf, config.C_UI_BG,
                         pygame.Rect(x - 4, y - 4, w + 8, DASH_H + 8))
        pygame.draw.rect(surf, config.C_UI_BORDER,
                         pygame.Rect(x - 4, y - 4, w + 8, DASH_H + 8), 1)

        y = self._draw_title_bar(surf, x, y, w, fps, frame, mission)
        y = self._draw_mission_progress(surf, x, y, w, swarm, mission, frame)
        y = self._draw_metrics_panel(surf, x, y, w, mission)
        y = self._draw_drone_cards(surf, x, y, w, swarm, frame)
        y = self._draw_alerts(surf, x, y, w, frame)
        y = self._draw_sector_grid(surf, x, y, w, swarm)
        self._draw_legend(surf, x, y, w, show_heatmap, show_comm)

    # ──────────────────────────────────────────
    # Sections
    # ──────────────────────────────────────────

    def _draw_title_bar(self, surf, x, y, w, fps, frame, mission) -> int:
        font_lg  = get_font(config.FONT_TITLE, bold=True)
        font_md  = get_font(config.FONT_MONO_MD)
        font_sm  = get_font(config.FONT_MONO_SM)

        # Title
        draw_text(surf, "◈ DRONE SWARM SIM", x, y, font_lg, config.C_UI_ACCENT)
        y += 26

        # FPS + clock
        m_str = mission.stats.elapsed_str()
        weather = mission.weather
        w_color = weather.color
        draw_text(surf, f"FPS {fps:3d}   TIME {m_str}", x, y, font_md, config.C_UI_TEXT)
        draw_text(surf, f"{weather.icon()} {weather.current}",
                  x + w - 90, y, font_md, w_color)
        y += 18

        # Mission state
        ms_color = config.C_UI_OK if mission.state == "running" else config.C_UI_ACCENT
        ms_text  = "● ACTIVE" if mission.state == "running" else "★ COMPLETE"
        draw_text(surf, ms_text, x, y, font_md, ms_color)
        y += 20

        # Divider
        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_mission_progress(self, surf, x, y, w, swarm, mission, frame) -> int:
        font_md = get_font(config.FONT_MONO_MD)
        font_sm = get_font(config.FONT_MONO_SM)

        pct = swarm.mission_progress()
        mz_found = len(swarm.game_map.mission_found)
        mz_total = config.MISSION_ZONE_COUNT

        draw_text(surf, "MISSION PROGRESS", x, y, font_md, config.C_UI_ACCENT)
        y += 16

        bar_color = lerp_color(config.C_UI_WARN, config.C_UI_OK, pct)
        draw_bar(surf, x, y, w, 14, pct, 1.0, bar_color)
        draw_text(surf, f"{pct*100:.1f}%", x + w // 2, y + 2, font_sm,
                  config.C_BG, anchor="center")
        y += 18

        draw_text(surf, f"Survivors  {mz_found}/{mz_total}   "
                       f"Sectors {swarm.sectors_completed()}/{len(swarm.sectors)}",
                  x, y, font_sm, config.C_UI_TEXT)
        y += 18

        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_metrics_panel(self, surf, x, y, w, mission) -> int:
        font_md = get_font(config.FONT_MONO_MD, bold=True)
        font_sm = get_font(config.FONT_MONO_SM)
        metrics = mission.metrics

        def anim(key: str, value: float) -> float:
            prev = self._metric_anim.get(key, value)
            prev += (value - prev) * 0.18
            self._metric_anim[key] = prev
            return prev

        draw_text(surf, "MISSION METRICS", x, y, font_md, config.C_UI_ACCENT)
        y += 16

        coverage = anim("coverage", metrics.coverage_pct)
        avg_bat = anim("battery", metrics.average_battery)
        comm = anim("comm", metrics.communication_health * 100.0)
        frontier = anim("frontier", metrics.frontier_completion_rate * 100.0)
        efficiency = anim("efficiency", metrics.mission_efficiency)
        rows = [
            ("Coverage", f"{coverage:5.1f}%", "Active", str(metrics.active_drones)),
            ("Failed", str(metrics.failed_drones), "Avg Bat", f"{avg_bat:4.0f}%"),
            ("Comm", f"{comm:4.0f}%", "Frontier", f"{frontier:4.0f}%"),
            ("NearMiss", str(metrics.collision_near_misses), "Stuck", str(metrics.stuck_recoveries)),
            ("Efficiency", f"{efficiency:5.1f}", "Replay", "PLAY" if mission.replay_playback_active else "LIVE"),
        ]
        mid = x + w // 2
        for left_label, left_val, right_label, right_val in rows:
            draw_text(surf, f"{left_label:<9}{left_val:>7}", x, y, font_sm, config.C_UI_TEXT)
            draw_text(surf, f"{right_label:<8}{right_val:>6}", mid, y, font_sm, config.C_UI_TEXT)
            y += 13

        draw_text(surf, "CSV " + mission.metrics_logger.path[-34:], x, y, font_sm, config.C_UI_BORDER)
        y += 14

        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_drone_cards(self, surf, x, y, w, swarm, frame) -> int:
        font_md = get_font(config.FONT_MONO_MD, bold=True)
        font_sm = get_font(config.FONT_MONO_SM)

        draw_text(surf, "DRONES", x, y, font_md, config.C_UI_ACCENT)
        y += 16

        card_h  = 36
        card_w  = w
        cols_per_row = 2
        card_inner_w = (card_w - 4) // cols_per_row

        for i, drone in enumerate(swarm.drones):
            cx = x + (i % cols_per_row) * card_inner_w
            cy = y + (i // cols_per_row) * (card_h + 3)

            # Card background
            dc = STATE_COLOR.get(drone.state, config.C_STATE_IDLE)
            bg = tuple(max(0, v - 180) for v in dc)
            draw_rounded_rect(surf, bg, pygame.Rect(cx, cy, card_inner_w - 2, card_h), 4)
            draw_rounded_rect(surf, dc, pygame.Rect(cx, cy, card_inner_w - 2, card_h), 4, 1)

            # Drone ID
            draw_text(surf, f"D{drone.drone_id}", cx + 4, cy + 2, font_md, dc)

            # State abbreviation
            state_abbr = {
                IDLE:      "IDLE",
                SCANNING:  "SCAN",
                RETURNING: "RTB ",
                CHARGING:  "CHG ",
                FAILED:    "FAIL",
                STRANDED:  "STRD",
                LOST_COMM: "LOST",
                "avoiding": "AVOD",
            }.get(drone.state, drone.state[:4].upper())
            draw_text(surf, state_abbr, cx + 4, cy + 16, font_sm, config.C_UI_TEXT)

            # Battery bar
            bat_color = drone.battery.color()
            draw_bar(surf, cx + card_inner_w // 2, cy + 4,
                     card_inner_w // 2 - 4, 8,
                     drone.battery.level, config.BATTERY_MAX, bat_color)
            draw_text(surf, f"{drone.battery.level:4.0f}%",
                      cx + card_inner_w // 2, cy + 14,
                      font_sm, bat_color)

            # Comm signal icon
            sig = drone.comm.signal_quality
            sig_color = lerp_color(config.C_UI_DANGER, config.C_UI_OK, sig)
            sig_char = "▊" if sig > 0.6 else ("▌" if sig > 0.3 else "▍")
            draw_text(surf, sig_char, cx + card_inner_w - 14, cy + 4, font_sm, sig_color)

        rows_used = (len(swarm.drones) + cols_per_row - 1) // cols_per_row
        y += rows_used * (card_h + 3) + 8

        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_alerts(self, surf, x, y, w, frame) -> int:
        font_md = get_font(config.FONT_MONO_MD, bold=True)
        font_sm = get_font(config.FONT_MONO_SM)

        draw_text(surf, "ALERTS", x, y, font_md, config.C_UI_ACCENT)
        y += 16

        visible = self._alert_log[-6:]
        for j, msg in enumerate(visible):
            age = len(visible) - 1 - j
            alpha_t = 1.0 - age / max(1, len(visible))
            a_color = lerp_color(config.C_UI_BORDER, config.C_UI_WARN, alpha_t)
            # Newest entry pulses
            if j == len(visible) - 1:
                p = pulse(frame, 45)
                a_color = lerp_color(config.C_UI_TEXT, config.C_UI_DANGER, p * 0.6)
            # Truncate long messages
            txt = msg[:40] if len(msg) > 40 else msg
            draw_text(surf, txt, x, y, font_sm, a_color)
            y += 13

        if not visible:
            draw_text(surf, "-- no alerts --", x, y, font_sm, config.C_UI_BORDER)
            y += 13

        y += 4
        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_sector_grid(self, surf, x, y, w, swarm) -> int:
        font_md = get_font(config.FONT_MONO_MD, bold=True)
        font_sm = get_font(config.FONT_MONO_SM)

        draw_text(surf, "SECTOR MAP", x, y, font_md, config.C_UI_ACCENT)
        y += 16

        cell_w = w // config.SECTOR_COLS
        cell_h = 12

        for s in swarm.sectors:
            sc = s.idx % config.SECTOR_COLS
            sr = s.idx // config.SECTOR_COLS
            rx = x + sc * cell_w
            ry = y + sr * cell_h

            if s.completed:
                color = config.C_UI_OK
            elif s.assigned_drone is not None:
                # Color by assigned drone state
                for d in swarm.drones:
                    if d.drone_id == s.assigned_drone:
                        color = STATE_COLOR.get(d.state, config.C_UI_WARN)
                        break
                else:
                    color = config.C_UI_WARN
            else:
                color = config.C_UI_BORDER

            pygame.draw.rect(surf, color, pygame.Rect(rx + 1, ry + 1, cell_w - 2, cell_h - 2))

        y += config.SECTOR_ROWS * cell_h + 8
        pygame.draw.line(surf, config.C_UI_BORDER, (x, y), (x + w, y), 1)
        y += 6
        return y

    def _draw_legend(self, surf, x, y, w, show_heatmap, show_comm):
        font_sm = get_font(config.FONT_MONO_SM)
        lines = [
            "[H] Heatmap " + ("ON " if show_heatmap else "OFF"),
            "[C] Comm    " + ("ON " if show_comm    else "OFF"),
            "[P] Pause   [Space] Follow",
            "[+/-] Zoom  [Arrows] Pan",
            "[R] Restart [ESC] Menu/Pause",
        ]
        for ln in lines:
            draw_text(surf, ln, x, y, font_sm, config.C_UI_BORDER)
            y += 13
