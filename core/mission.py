"""
core/mission.py - Mission-level controller.

Manages:
  - Overall mission state (RUNNING / COMPLETE)
  - Dynamic weather simulation
  - Wind zone effects
  - Mission timer
  - End-of-mission statistics
"""

import os
import random
import time
import config
from core.analytics import MissionAnalytics, MetricsCsvLogger, export_replay, load_replay


class Weather:
    """Simulates changing weather conditions."""

    def __init__(self):
        self.current: str = "Clear"
        self._timer: int  = 0
        self._change_interval = config.WEATHER_CHANGE_INTERVAL

    def update(self, frame: int):
        self._timer += 1
        if self._timer >= self._change_interval:
            self._timer = 0
            # Weighted random transition
            weights = {"Clear": 0.4, "Cloudy": 0.3, "Windy": 0.2, "Stormy": 0.1}
            # Bias away from current
            probs = {k: v for k, v in weights.items() if k != self.current}
            total = sum(probs.values())
            r = random.random() * total
            cumulative = 0.0
            for w, p in probs.items():
                cumulative += p
                if r <= cumulative:
                    self.current = w
                    break

    @property
    def is_stormy(self) -> bool:
        return self.current == "Stormy"

    @property
    def is_windy(self) -> bool:
        return self.current in ("Windy", "Stormy")

    @property
    def color(self) -> tuple[int, int, int]:
        return {
            "Clear":  config.C_UI_OK,
            "Cloudy": config.C_UI_TEXT,
            "Windy":  config.C_UI_WARN,
            "Stormy": config.C_UI_DANGER,
        }.get(self.current, config.C_UI_TEXT)

    def icon(self) -> str:
        return {
            "Clear":  "☀",
            "Cloudy": "☁",
            "Windy":  "≋",
            "Stormy": "⚡",
        }.get(self.current, "?")


class MissionStats:
    """Accumulated statistics for the end-of-mission report."""

    def __init__(self, num_drones: int):
        self.num_drones     = num_drones
        self.start_time     = time.time()
        self.end_time: float | None = None

        self.cells_scanned   = 0
        self.missions_found  = 0
        self.total_missions  = (config.DEMO_MISSION_ZONE_COUNT
                                if getattr(config, "QUICK_DEMO_MODE", False)
                                else config.MISSION_ZONE_COUNT)
        self.drone_failures  = 0
        self.battery_returns = 0
        self.comm_losses     = 0
        self.weather_events  = 0

    def elapsed_seconds(self) -> float:
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def elapsed_str(self) -> str:
        s = int(self.elapsed_seconds())
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def complete(self):
        self.end_time = time.time()

    def summary_lines(self) -> list[str]:
        return [
            f"Mission Duration  : {self.elapsed_str()}",
            f"Drones Deployed   : {self.num_drones}",
            f"Map Coverage      : {self.cells_scanned} cells",
            f"Survivors Found   : {self.missions_found}/{self.total_missions}",
            f"Hardware Failures : {self.drone_failures}",
            f"Battery Returns   : {self.battery_returns}",
            f"Comm-Loss Events  : {self.comm_losses}",
            f"Weather Events    : {self.weather_events}",
        ]


# Mission state constants
MISSION_RUNNING   = "running"
MISSION_COMPLETE  = "complete"


class Mission:
    """
    Top-level mission object owned by the main simulation loop.
    """

    def __init__(self, game_map, swarm):
        self.game_map = game_map
        self.swarm    = swarm
        self.weather  = Weather()
        self.stats    = MissionStats(len(swarm.drones))
        self.stats.total_missions = len(game_map.mission_zones)
        self.state: str = MISSION_RUNNING
        self.frame: int = 0
        self.seed = getattr(game_map, "seed", 0)
        self.analytics = MissionAnalytics()
        self.metrics = self.analytics.sample(self)
        self.metrics_logger = MetricsCsvLogger(self.seed)
        self.last_replay_path: str | None = None
        self.replay_playback_active = False
        self._loaded_replay: list[dict] = []
        self._replay_playback_idx = 0

        # Replay buffer
        self._replay_buffer: list[dict] = []
        self._replay_timer  = 0

    def update(self):
        if self.replay_playback_active:
            self._tick_replay_playback()
            return

        self.frame += 1

        # Weather simulation
        self.weather.update(self.frame)

        # Swarm update (passes weather to drones)
        self.swarm.update(self.frame, self.weather.current)
        self.metrics = self.analytics.sample(self)
        if self.frame % config.TARGET_FPS == 0:
            self.metrics_logger.write(self.metrics)

        # Stats accumulation
        from core.drone import FAILED, RETURNING, LOST_COMM
        for d in self.swarm.drones:
            pass  # detailed stats updated via alerts

        # Check mission completion
        if (self.game_map.exploration_pct() >= 0.98 or
                len(self.game_map.mission_found) >= len(self.game_map.mission_zones)):
            if self.state == MISSION_RUNNING:
                self.state = MISSION_COMPLETE
                self.stats.complete()
                self.stats.missions_found = len(self.game_map.mission_found)
                self.swarm.alerts.append("★ MISSION COMPLETE ★")

        # Replay snapshot
        self._replay_timer += 1
        if self._replay_timer >= config.REPLAY_RECORD_INTERVAL:
            self._replay_timer = 0
            self._record_snapshot()

    def _record_snapshot(self):
        """Store a lightweight snapshot for replay."""
        if len(self._replay_buffer) >= config.REPLAY_MAX_FRAMES:
            return
        snap = {
            "frame": self.frame,
            "weather": self.weather.current,
            "exploration": self.game_map.exploration_pct(),
            "metrics": self.metrics.csv_row(),
            "drones": [
                {
                    "id":    d.drone_id,
                    "px":    d.px,
                    "py":    d.py,
                    "state": d.state,
                    "bat":   d.battery.level,
                }
                for d in self.swarm.drones
            ],
        }
        self._replay_buffer.append(snap)

    def get_replay(self) -> list[dict]:
        return list(self._replay_buffer)

    def export_replay(self, path: str | None = None) -> str:
        if path is None:
            os.makedirs(config.REPLAY_EXPORT_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(config.REPLAY_EXPORT_DIR, f"mission_replay_{stamp}_seed{self.seed}.json")
        export_replay(path, self.seed, self.get_replay(), self.metrics)
        self.last_replay_path = path
        self.swarm.alerts.append(f"Replay exported: {path}")
        return path

    def load_replay(self, path: str) -> int:
        payload = load_replay(path)
        self._loaded_replay = list(payload["frames"])
        self._replay_playback_idx = 0
        self.replay_playback_active = bool(self._loaded_replay)
        self.last_replay_path = path
        self.swarm.alerts.append(f"Replay loaded: {len(self._loaded_replay)} frames")
        return len(self._loaded_replay)

    def load_last_replay(self) -> int:
        if self.last_replay_path and os.path.exists(self.last_replay_path):
            return self.load_replay(self.last_replay_path)
        if not os.path.isdir(config.REPLAY_EXPORT_DIR):
            raise FileNotFoundError("No replay directory exists yet")
        files = [
            os.path.join(config.REPLAY_EXPORT_DIR, name)
            for name in os.listdir(config.REPLAY_EXPORT_DIR)
            if name.endswith(".json")
        ]
        if not files:
            raise FileNotFoundError("No replay JSON files found")
        return self.load_replay(max(files, key=os.path.getmtime))

    def _tick_replay_playback(self):
        if not self._loaded_replay:
            self.replay_playback_active = False
            return
        snap = self._loaded_replay[self._replay_playback_idx]
        self.frame = int(snap.get("frame", self.frame))
        self.weather.current = snap.get("weather", self.weather.current)
        by_id = {d.drone_id: d for d in self.swarm.drones}
        for item in snap.get("drones", []):
            drone = by_id.get(item.get("id"))
            if drone is None:
                continue
            drone.px = float(item.get("px", drone.px))
            drone.py = float(item.get("py", drone.py))
            drone.state = item.get("state", drone.state)
            drone.battery.level = float(item.get("bat", drone.battery.level))
        metric_data = snap.get("metrics")
        if metric_data:
            for key, value in metric_data.items():
                if hasattr(self.metrics, key):
                    setattr(self.metrics, key, value)
        self._replay_playback_idx += 1
        if self._replay_playback_idx >= len(self._loaded_replay):
            self.replay_playback_active = False
            self.swarm.alerts.append("Replay playback complete")
