"""
core/analytics.py - Mission metrics, CSV logging, and replay persistence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
import os
import io
from core.persistence import atomic_write, unique_path, write_json

from core.experiment import Experiment, TICK_HZ, settings as config
from core.drone import FAILED, STRANDED, CHARGING
from core.accounting import EVENT_METRICS


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

    outcome: str = "running"
    completion_reason: str = ""
    completed_tick: int | None = None
    simulation_seconds: float = 0.0
    survivors_local: int = 0
    survivor_local_observations: int = 0
    survivors_published: int = 0
    survivors_rescued: int | None = None  # No survivor-rescue mechanic exists.
    task_awards: int = 0
    task_completions: int = 0
    task_cancellations: int = 0
    path_searches: int = 0
    partitions: int = 0
    reconnects: int = 0
    lost_comm_entries: int = 0
    discovery_uploads: int = 0
    collision_rejections: int = 0
    collision_waits: int = 0
    backoff_attempts: int = 0
    backoffs: int = 0
    exhausted_backoffs: int = 0
    field_contacts: int = 0
    charging_starts: int = 0
    charging_completions: int = 0
    relaunches: int = 0
    hardware_failures: int = 0
    stranded_transitions: int = 0
    stranded_drones: int = 0
    connected_fraction: float = 0.0
    distance_travelled_px: float = 0.0
    battery_consumed_points: float = 0.0
    battery_recharged_points: float = 0.0
    event_count: int = 0
    event_hash: str = ""
    energy_checks: int = 0
    energy_infeasible_checks: int = 0
    energy_route_searches: int = 0
    energy_returns: int = 0

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
        self._connected = {}
        self._observed_tick = None

    def sample(self, mission) -> MissionMetrics:
        swarm = mission.swarm
        drones = swarm.drones
        count = max(1, len(drones))
        coverage_pct = mission.game_map.exploration_pct() * 100.0
        failed = sum(1 for d in drones if d.state == FAILED)
        active = sum(1 for d in drones if d.state not in (FAILED, STRANDED, CHARGING))
        avg_battery = 100.0 * sum(d.battery.pct for d in drones) / count
        comm_health = sum(d.comm.signal_quality for d in drones) / count
        frontier_rate = self._frontier_completion_rate(swarm)
        stuck_recoveries = sum(getattr(d, "stuck_recoveries", 0) for d in drones)
        efficiency = self._efficiency_score(
            coverage_pct, avg_battery, comm_health, frontier_rate,
            self.near_miss_count, stuck_recoveries, failed,
        )
        a = swarm.accounting
        return MissionMetrics(
            **{field: a.count(kind) for field,kind in EVENT_METRICS.items()},
            outcome=mission.outcome, completion_reason=mission.completion_reason,
            completed_tick=mission.completed_tick, simulation_seconds=mission.clock.seconds,
            survivors_local=len(set().union(*(set(d.mission_found) for d in drones))),
            survivor_local_observations=a.count('survivor_local'),
            survivors_published=len(mission.game_map.mission_found),
            stranded_drones=sum(d.state == STRANDED for d in drones),
            connected_fraction=sum(d.comm.is_connected for d in drones)/count,
            distance_travelled_px=sum(getattr(d,'distance_travelled_px',0.) for d in drones),
            battery_consumed_points=sum(d.battery.consumed for d in drones),
            battery_recharged_points=sum(d.battery.recharged for d in drones),
            event_count=a.sequence, event_hash=a.snapshot()['event_hash'],
            energy_checks=sum(d.energy.checks for d in drones),
            energy_infeasible_checks=sum(d.energy.rejections for d in drones),
            energy_route_searches=sum(d.energy.searches for d in drones),
            energy_returns=a.count('energy_return'),
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

    def observe(self, mission, starts):
        """Exactly one post-update observation; sample() is a pure query."""
        if self._observed_tick == mission.frame:
            return
        self._observed_tick = mission.frame
        drones = mission.swarm.drones
        a = mission.swarm.accounting
        from core.geometry import trajectories_contact
        for i, d in enumerate(drones):
            connected = d.comm.is_connected
            previous = self._connected.get(d.drone_id, True)
            if connected != previous:
                a.emit('reconnect' if connected else 'partition', d.drone_id)
            self._connected[d.drone_id] = connected
            for other in drones[i+1:]:
                if trajectories_contact(starts[d.drone_id], (d.px,d.py),
                        starts[other.drone_id], (other.px,other.py), d.base_px):
                    a.emit('field_contact', d.drone_id, other.drone_id,
                           'continuous point contact during tick')
        self._update_near_misses(drones, a)

    def _update_near_misses(self, drones, accounting):
        threshold = config.CELL_SIZE * 0.85
        active_now: set[tuple[int, int]] = set()
        for i, da in enumerate(drones):
            for db in drones[i + 1:]:
                pair = (min(da.drone_id, db.drone_id), max(da.drone_id, db.drone_id))
                dist = math.hypot(da.px - db.px, da.py - db.py)
                if dist <= threshold and not (da.is_in_docking_zone() and db.is_in_docking_zone()):
                    active_now.add(pair)
                    if pair not in self._near_miss_active:
                        self.near_miss_count += 1
                        accounting.emit("proximity_entered", pair[0], pair[1])
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

    def __init__(self, seed: int, experiment=None):
        self.path = unique_path(config.METRICS_LOG_DIR, f"mission_metrics_seed{seed}", ".csv")
        self._fieldnames = list(MissionMetrics().__dict__.keys())
        def header(f):
            csv.DictWriter(f, fieldnames=self._fieldnames).writeheader()
        atomic_write(self.path, header)
        experiment = experiment if experiment is not None else Experiment(seed)
        try:
            write_json(self.path + '.metadata.json', dict(
                version=2, accounting_version=1, kind='adss.metrics-metadata', tick_hz=TICK_HZ,
                experiment=json.loads(experiment.canonical_json), identity=experiment.identity,
                csv=os.path.basename(self.path)))
        except Exception:
            os.unlink(self.path)  # Only this instance's exclusively created header.
            raise

    def write(self, metrics: MissionMetrics):
        # A single writer owns each unique run file. Publish complete row updates.
        with open(self.path, 'r', newline='', encoding='utf-8') as f:
            previous = f.read()
        row = io.StringIO(newline='')
        csv.DictWriter(row, fieldnames=self._fieldnames).writerow(metrics.csv_row())
        atomic_write(self.path, lambda f: f.write(previous + row.getvalue()), overwrite=True)


def export_replay(path, seed, replay, metrics):
    raise ValueError("Legacy v1 export lacks world/configuration; use Mission.export_replay")


def load_replay(path: str) -> dict:
    from core.replay import load
    return load(path)
