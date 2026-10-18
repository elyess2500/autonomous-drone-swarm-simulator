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
import copy
from core.experiment import (Experiment, SimulationClock, TICK_HZ,
                             in_experiment, settings as config)
from core.analytics import MissionAnalytics, MetricsCsvLogger
from core import replay
from core.persistence import unique_path


class Weather:
    """Simulates changing weather conditions."""

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else Experiment().stream('environment')
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
            r = self.rng.random() * total
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

    def __init__(self, num_drones: int, clock=None):
        self.num_drones     = num_drones
        self.clock = clock if clock is not None else SimulationClock()
        self.start_time     = self.clock.seconds
        self.end_time: float | None = None

        self._mission = None
        self._frozen = None
        self.total_missions  = (config.DEMO_MISSION_ZONE_COUNT
                                if getattr(config, "QUICK_DEMO_MODE", False)
                                else config.MISSION_ZONE_COUNT)

    def _values(self):
        if self._mission is None:
            return dict(cells_scanned=0, missions_found=0, drone_failures=0,
                        battery_returns=0, comm_losses=0, weather_events=0)
        m = self._mission
        from core.map import CELL_OBSTACLE
        a = m.swarm.accounting
        return dict(cells_scanned=int(((m.game_map.grid != CELL_OBSTACLE) & m.game_map.fog).sum()),
                    missions_found=len(m.game_map.mission_found),
                    drone_failures=a.count('hardware_failure'),
                    battery_returns=a.count('return_started'),
                    comm_losses=a.count('lost_comm_entry'), weather_events=a.count('weather_changed'))

    def _get(self, key):
        return (self._frozen if self._frozen is not None else self._values())[key]

    cells_scanned = property(lambda self: self._get('cells_scanned'))
    missions_found = property(lambda self: self._get('missions_found'))
    drone_failures = property(lambda self: self._get('drone_failures'))
    battery_returns = property(lambda self: self._get('battery_returns'))
    comm_losses = property(lambda self: self._get('comm_losses'))
    weather_events = property(lambda self: self._get('weather_events'))

    def elapsed_seconds(self) -> float:
        end = self.end_time if self.end_time is not None else self.clock.seconds
        return end - self.start_time

    def elapsed_str(self) -> str:
        s = int(self.elapsed_seconds())
        m, s = divmod(s, 60)
        return f"{m:02d}:{s:02d}"

    def complete(self):
        if self.end_time is None:
            self.end_time = self.clock.seconds
            self._frozen = self._values()

    def summary_lines(self) -> list[str]:
        return [
            f"Mission Duration  : {self.elapsed_str()}",
            f"Drones Deployed   : {self.num_drones}",
            f"Map Coverage      : {self.cells_scanned} cells",
            f"Survivors Found   : {self.missions_found}/{self.total_missions}",
            f"Hardware Failures : {self.drone_failures}",
            f"Return Entries    : {self.battery_returns}",
            f"LOST_COMM Entries : {self.comm_losses}",
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
        self.experiment = game_map.experiment
        self.clock = SimulationClock()
        self.weather  = Weather(self.experiment.stream('environment'))
        self.stats    = MissionStats(len(swarm.drones), self.clock)
        self.stats.total_missions = len(game_map.mission_zones)
        self.stats._mission = self
        self.outcome = "running"
        self.completion_reason = ""
        self.completed_tick = None
        self._final_summary = None
        self.state: str = MISSION_RUNNING
        self.frame: int = 0
        self.seed = getattr(game_map, "seed", 0)
        self.analytics = MissionAnalytics()
        self.metrics = self.analytics.sample(self)
        self.metrics_logger = MetricsCsvLogger(self.seed, self.experiment)
        self.last_replay_path: str | None = None
        self.replay_player = None

        # Replay buffer
        self._replay_buffer: list[dict] = []
        self._replay_timer  = 0
        self._replay_world = replay.capture_world(self)
        self._replay_bytes = 0
        self._replay_truncated = False
        self._record_snapshot()

    @property
    def replay_playback_active(self):
        return self.replay_player is not None

    @property
    def frame(self):
        return self.clock.tick

    @frame.setter
    def frame(self, value):
        self.clock.tick = value

    @in_experiment
    def update(self):
        if self.replay_playback_active:
            self.replay_player.advance()
            return

        self.frame += 1

        self.swarm.accounting.tick = self.frame
        starts = {d.drone_id: (d.px,d.py) for d in self.swarm.drones}
        previous_weather = self.weather.current
        self.weather.update(self.frame)
        if previous_weather != self.weather.current:
            self.swarm.accounting.emit('weather_changed', subject=self.weather.current,
                                       reason=previous_weather)

        # Swarm update (passes weather to drones)
        self.swarm.update(self.frame, self.weather.current)
        self.analytics.observe(self, starts)
        reason = ('coverage_target' if self.game_map.exploration_pct() >= .98 else
                  'all_survivors_published' if self.game_map.mission_zones and
                  len(self.game_map.mission_found) >= len(self.game_map.mission_zones) else '')
        completed_now = bool(reason and self.state == MISSION_RUNNING)
        if completed_now:
            self.state = MISSION_COMPLETE
            self.outcome = 'success'
            self.completion_reason = reason
            self.completed_tick = self.frame
            self.swarm.accounting.emit('mission_completed', reason=reason)
            self.stats.complete()
            self.swarm.alerts.append("MISSION COMPLETE")
        self.metrics = self.analytics.sample(self)
        if completed_now:
            self._final_summary = self.summary()
        if self.frame % TICK_HZ == 0 or completed_now:
            self.metrics_logger.write(self.metrics)

        # Replay snapshot
        self._replay_timer += 1
        if self._replay_timer >= config.REPLAY_RECORD_INTERVAL:
            self._replay_timer = 0
            self._record_snapshot()

    def summary(self):
        """Detached final snapshot after completion, otherwise current metrics."""
        from dataclasses import asdict
        if self._final_summary is not None:
            return copy.deepcopy(self._final_summary)
        return dict(version=1, metrics=asdict(self.analytics.sample(self)),
                    accounting=self.swarm.accounting.snapshot())

    def _record_snapshot(self):
        """Capture a detached sampled state, with explicit bounded retention."""
        if self._replay_truncated:
            return
        if len(self._replay_buffer) >= min(config.REPLAY_MAX_FRAMES, replay.MAX_FRAMES):
            self._replay_truncated = True
            return
        snap = replay.capture_frame(self)
        size = len(replay.canonical(snap).encode())
        if self._replay_bytes + size > replay.MAX_FILE_BYTES // 2:
            self._replay_truncated = True
            return
        self._replay_buffer.append(snap)
        self._replay_bytes += size

    def get_replay(self) -> list[dict]:
        return copy.deepcopy(self._replay_buffer)

    @in_experiment
    def export_replay(self, path: str | None = None, *, overwrite=False) -> str:
        if self.replay_playback_active:
            raise ValueError("Playback is not a live recording; export the original file instead")
        if replay.capture_world(self) != self._replay_world:
            raise ValueError("World changed after recording began; start a new recording")
        if not self._replay_buffer:
            raise ValueError("No replay snapshots were recorded")
        frames = list(self._replay_buffer)
        # Preserve the exact export tick unless bounded recording already stopped.
        if (not self._replay_truncated and frames[-1]['frame'] != self.frame and
                len(frames) < min(config.REPLAY_MAX_FRAMES, replay.MAX_FRAMES) and
                self._replay_bytes < replay.MAX_FILE_BYTES // 2):
            frames.append(replay.capture_frame(self))
        if path is None:
            path = unique_path(config.REPLAY_EXPORT_DIR, f"mission_replay_seed{self.seed}", '.json')
        replay.save(path, replay.make_payload(self, frames, self._replay_world), overwrite=overwrite)
        self.last_replay_path = str(path)
        self.swarm.alerts.append(f"Replay exported: {path}")
        return str(path)

    def load_replay(self, path: str) -> int:
        payload = replay.load(path)
        player = replay.ReplayPlayer(payload)
        self.replay_player = player
        self.last_replay_path = str(path)
        return len(payload['frames'])

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
