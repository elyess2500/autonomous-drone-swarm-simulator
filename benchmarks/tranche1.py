"""Reproduce tranche-1 metrics without rendering (run each stage sequentially).

python benchmarks/tranche1.py --label baseline --output /path/to/results.json
Timing includes normal Mission.update work, but excludes instrumentation checks.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import numpy as np
import config
import core.drone as drone_module
from core.drone import Drone
from core.swarm import Swarm
from main import make_simulation


def run(seed, ticks):
    counts = dict(path_searches=0, unfinished_task_replacements=0,
                  relay_task_conflicts=0, orphaned_ownership_ticks=0)
    search = drone_module.find_path
    accept = Drone.accept_frontier_task
    assign = Swarm._assign

    def counted_search(*args, **kwargs):
        counts["path_searches"] += 1
        return search(*args, **kwargs)

    def counted_accept(drone, *args, **kwargs):
        if drone.current_frontier_id is not None and drone.scan_queue:
            counts["unfinished_task_replacements"] += 1
        if drone.relay_anchor_active:
            counts["relay_task_conflicts"] += 1
        return accept(drone, *args, **kwargs)

    def counted_assign(swarm, drone, sector):
        if drone.relay_anchor_active:
            counts["relay_task_conflicts"] += 1
        return assign(swarm, drone, sector)

    drone_module.find_path = counted_search
    Drone.accept_frontier_task = counted_accept
    Swarm._assign = counted_assign
    try:
        game_map, swarm, mission, _ = make_simulation(seed)
        times, connectivity = [], []
        violations = 0
        for _ in range(ticks):
            t = time.perf_counter()
            mission.update()
            times.append((time.perf_counter() - t) * 1000)
            connectivity.append(sum(d.comm.is_connected for d in swarm.drones) / len(swarm.drones))
            violations += sum(d.battery.charging and not d.can_charge_here() for d in swarm.drones)
            by_id = {d.drone_id: d for d in swarm.drones}
            bad_sectors = sum(s.assigned_drone is not None and
                              by_id[s.assigned_drone].assigned_sector != s.idx for s in swarm.sectors)
            bad_frontiers = sum(f.assigned_drone is not None and
                                by_id[f.assigned_drone].current_frontier_id != f.frontier_id
                                for f in swarm.frontiers.frontiers)
            bad_drones = sum(d.current_frontier_id is not None and not any(
                f.frontier_id == d.current_frontier_id and f.assigned_drone == d.drone_id
                for f in swarm.frontiers.frontiers) for d in swarm.drones)
            counts["orphaned_ownership_ticks"] += bad_sectors + bad_frontiers + bad_drones
        state = dict(fog=game_map.fog.tolist(), found=sorted(game_map.mission_found),
                     weather=mission.weather.current, drones=[(d.px, d.py, d.state, d.battery.level,
                     d.path, d.scan_queue) for d in swarm.drones])
        return dict(seed=seed, ticks=ticks, **counts, frontier_awards=swarm.frontiers_assigned,
                    frontier_completions=swarm.frontiers_completed,
                    final_orphaned_ownership=bad_sectors + bad_frontiers + bad_drones,
                    coverage_pct=100*game_map.exploration_pct(), survivors=len(game_map.mission_found),
                    average_connectivity=float(np.mean(connectivity)), min_connectivity=min(connectivity),
                    field_charging_violations=violations, states=swarm.drone_state_counts(),
                    task_cancellations=getattr(swarm, "task_cancellations", {}),
                    mean_ms=float(np.mean(times)), p95_ms=float(np.percentile(times,95)),
                    p99_ms=float(np.percentile(times,99)),
                    state_hash=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest())
    finally:
        drone_module.find_path = search
        Drone.accept_frontier_task = accept
        Swarm._assign = assign


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[2026])
    parser.add_argument("--ticks", type=int, default=3600)
    args = parser.parse_args()
    config.FAILURE_PROB_PER_FRAME = 0.0
    config.QUICK_DEMO_MODE = False
    config.AUTONOMOUS_OFFLINE_MODE = True
    with tempfile.TemporaryDirectory(prefix="adss-benchmark-") as runtime:
        config.METRICS_LOG_DIR = runtime
        results = [run(seed, args.ticks) for seed in args.seeds]
    payload = dict(label=args.label, failure_probability=0, results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
