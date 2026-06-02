"""
core/analytics.py - Mission metrics, CSV logging, and replay persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
import os
import time

import config
from core.drone import FAILED, STRANDED, CHARGING


@dataclass
class MissionMetrics:
    frame: int = 0
    elapsed_sec: float = 0.0
    coverage_pct: float = 0.0
    active_drones: int = 0
    failed_drones: int = 0
    average_battery: float = 0.0
    communication_health: float = 0.0
    frontier_completion_rate: float = 0.0
    collision_near_misses: int = 0
    stuck_recoveries: int = 0
    mission_efficiency: float = 0.0

    def csv_row(self) -> dict:
        row = asdict(self)
        row["elapsed_sec"] = round(self.elapsed_sec, 2)
        row["coverage_pct"] = round(self.coverage_pct, 3)
        row["average_battery"] = round(self.average_battery, 2)
        row["communication_health"] = round(self.communication_health, 3)
        row["frontier_completion_rate"] = round(self.frontier_completion_rate, 3)
        row["mission_efficiency"] = round(self.mission_efficiency, 3)
        return row


class MissionAnalytics:
    """Compute cumulative mission-grade metrics from live simulator state."""

    def __init__(self):
        self.near_miss_count = 0
        self._near_miss_active: set[tuple[int, int]] = set()

    def sample(self, mission) -> MissionMetrics:
        swarm = mission.swarm
        drones = swarm.drones
        count = max(1, len(drones))
        coverage_pct = mission.game_map.exploration_pct() * 100.0
        failed = sum(1 for d in drones if d.state in (FAILED, STRANDED))
        active = sum(1 for d in drones if d.state not in (FAILED, STRANDED, CHARGING))
        avg_battery = sum(d.battery.level for d in drones) / count
        comm_health = sum(d.comm.signal_quality for d in drones) / count
        frontier_rate = self._frontier_completion_rate(swarm)
        stuck_recoveries = sum(getattr(d, "stuck_recoveries", 0) for d in drones)
        self._update_near_misses(drones)
        efficiency = self._efficiency_score(
            coverage_pct, avg_battery, comm_health, frontier_rate,
            self.near_miss_count, stuck_recoveries, failed,
        )
        return MissionMetrics(
            frame=mission.frame,
            elapsed_sec=mission.stats.elapsed_seconds(),
            coverage_pct=coverage_pct,
            active_drones=active,
            failed_drones=failed,
            average_battery=avg_battery,
            communication_health=comm_health,
            frontier_completion_rate=frontier_rate,
            collision_near_misses=self.near_miss_count,
            stuck_recoveries=stuck_recoveries,
            mission_efficiency=efficiency,
        )

    def _update_near_misses(self, drones):
        threshold = config.CELL_SIZE * 0.85
        active_now: set[tuple[int, int]] = set()
        for i, da in enumerate(drones):
            for db in drones[i + 1:]:
                pair = (min(da.drone_id, db.drone_id), max(da.drone_id, db.drone_id))
                dist = math.hypot(da.px - db.px, da.py - db.py)
                if dist <= threshold:
                    active_now.add(pair)
                    if pair not in self._near_miss_active:
                        self.near_miss_count += 1
        self._near_miss_active = active_now

    def _frontier_completion_rate(self, swarm) -> float:
        completed = getattr(swarm, "frontiers_completed", 0)
        assigned = getattr(swarm, "frontiers_assigned", 0)
        if assigned <= 0:
            return 0.0
        return min(1.0, completed / assigned)

    def _efficiency_score(
        self,
        coverage_pct: float,
        avg_battery: float,
        comm_health: float,
        frontier_rate: float,
        near_misses: int,
        stuck_recoveries: int,
        failed: int,
    ) -> float:
        score = (
            coverage_pct * 0.45 +
            avg_battery * 0.20 +
            comm_health * 100.0 * 0.15 +
            frontier_rate * 100.0 * 0.20
        )
        score -= min(25.0, near_misses * 1.5)
        score -= min(20.0, stuck_recoveries * 2.0)
        score -= failed * 8.0
        return max(0.0, min(100.0, score))


class MetricsCsvLogger:
    """Append one metrics sample per second to a timestamped CSV file."""

    def __init__(self, seed: int):
        os.makedirs(config.METRICS_LOG_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(config.METRICS_LOG_DIR, f"mission_metrics_{stamp}_seed{seed}.csv")
        self._fieldnames = list(MissionMetrics().__dict__.keys())
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames)
            writer.writeheader()

    def write(self, metrics: MissionMetrics):
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames)
            writer.writerow(metrics.csv_row())


def export_replay(path: str, seed: int, replay: list[dict], metrics: MissionMetrics):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "version": 1,
        "seed": seed,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metrics": metrics.csv_row(),
        "frames": replay,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_replay(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or "frames" not in payload:
        raise ValueError("Replay file is missing a frames array")
    return payload
