"""Manifest-driven Step 15 research; observation and output stay outside policy."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
from core.experiment import ExperimentConfig
from core.simulation import make_simulation
from core.persistence import write_json
from core.replay import capture_world
from benchmarks.step11 import projection, digest


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_manifest(path):
    data = json.loads(Path(path).read_text())
    assert data['schema'] == 1 and data['ticks'] > 0
    for rel, checksum in data['protected_inputs'].items():
        if file_hash(ROOT / rel) != checksum:
            raise ValueError('Frozen source mismatch: ' + rel)
    return data, digest(data)


def summary(values):
    import numpy as np
    return dict(mean=float(np.mean(values)), p50=float(np.percentile(values, 50)),
                p95=float(np.percentile(values, 95)), p99=float(np.percentile(values, 99)),
                maximum=float(max(values)))


def validate_saved(path, manifest_hash, run_key, harness_hash):
    data = json.loads(path.read_text())
    checksum = path.with_suffix('.sha256')
    if not checksum.exists() or checksum.read_text().strip() != file_hash(path):
        raise ValueError('Invalid/missing raw checksum: ' + str(path))
    if (data['status'] != 'complete' or data['manifest_hash'] != manifest_hash or
            data['run_key'] != run_key or data['harness_hash'] != harness_hash or
            data['metrics']['frame'] != data['ticks']):
        raise ValueError('Incompatible completed run: ' + str(path))
    for rel, value in data['artifacts'].items():
        if file_hash(ROOT / rel) != value:
            raise ValueError('Artifact checksum mismatch: ' + rel)
    return data


def run_one(manifest, manifest_hash, item, output, measure_csv=True):
    seed, condition = item['seed'], item['condition']
    run_key = f'{condition}_seed{seed}'
    path = output / (run_key + '.json')
    harness_hash = file_hash(__file__)
    if path.exists():
        return validate_saved(path, manifest_hash, run_key, harness_hash), True
    attempt = output / (run_key + '_files')
    if attempt.exists():
        raise ValueError('Incomplete prior attempt retained; use a new output directory: ' + str(attempt))
    attempt.mkdir(parents=True)
    original_paths = config.METRICS_LOG_DIR, config.REPLAY_EXPORT_DIR
    config.METRICS_LOG_DIR = config.REPLAY_EXPORT_DIR = str(attempt)
    mission = None
    wall_start = time.perf_counter()
    try:
        conf = ExperimentConfig.from_json(canonical(manifest['conditions'][condition]))
        start = time.perf_counter()
        world, swarm, mission, _ = make_simulation(seed, experiment_config=conf)
        construction = time.perf_counter() - start
        world_hash = digest(capture_world(mission))
        initial = asdict(mission.analytics.sample(mission))
        io = [0.]
        logger = mission.metrics_logger.write
        def timed_write(metrics):
            started = time.perf_counter()
            try:
                return logger(metrics)
            finally:
                io[0] += time.perf_counter() - started
        if measure_csv:
            mission.metrics_logger.write = timed_write
        updates = []
        csv_times = []
        observer_seconds = 0.
        connected = majority = disconnected = pending_sum = pending_survivors = new_pending = 0
        cursor = 0
        local = {}
        published = {}
        disconnected_reports = 0
        previous_pending = {d.drone_id: set(d.offline_known_cells) for d in swarm.drones}
        series = []
        threshold_tick = 0 if initial['coverage_pct'] >= 10 else None
        for tick in range(1, manifest['ticks'] + 1):
            io_before = io[0]
            start = time.perf_counter()
            mission.update()
            elapsed = time.perf_counter() - start
            updates.append(elapsed * 1000)
            csv_times.append((io[0] - io_before) * 1000)
            start = time.perf_counter()
            count = sum(d.comm.is_connected for d in swarm.drones)
            connected += count / len(swarm.drones)
            majority += count > len(swarm.drones) / 2
            disconnected += len(swarm.drones) - count
            pending_sum += sum(len(d.offline_known_cells) for d in swarm.drones)
            pending_survivors += sum(len(d.offline_survivor_found) for d in swarm.drones)
            for d in swarm.drones:
                new_pending += len(d.offline_known_cells - previous_pending[d.drone_id])
                previous_pending[d.drone_id] = set(d.offline_known_cells)
            events = [e for e in swarm.accounting.records if e.sequence >= cursor]
            if events:
                if events[0].sequence != cursor:
                    raise ValueError('Accounting retention overran observation cursor')
                for event in events:
                    if event.kind == 'survivor_local':
                        local.setdefault(event.subject, event.tick)
                        disconnected_reports += event.reason == 'disconnected'
                    if event.kind == 'survivor_published':
                        published.setdefault(event.subject, event.tick)
                cursor = events[-1].sequence + 1
            if cursor != swarm.accounting.sequence:
                raise ValueError('Missing accounting events')
            if threshold_tick is None and mission.metrics.coverage_pct >= 10:
                threshold_tick = tick
            if tick % 60 == 0 or tick == manifest['ticks']:
                series.append(dict(tick=tick, coverage=mission.metrics.coverage_pct,
                                   survivors=mission.metrics.survivors_published,
                                   connected=count / len(swarm.drones),
                                   waits=mission.metrics.collision_waits))
            observer_seconds += time.perf_counter() - start
        metrics = asdict(mission.analytics.sample(mission))
        n_ticks = manifest['ticks']
        observations = dict(connectivity_exposure=connected / n_ticks,
            majority_fraction=majority / n_ticks, disconnected_agent_ticks=disconnected,
            pending_map_exposure=pending_sum / n_ticks,
            pending_survivor_exposure=pending_survivors / n_ticks,
            new_pending_map_entries=new_pending, offline_survivor_reports=disconnected_reports,
            synchronized_map_cells=sum(d.offline_synced_cells for d in swarm.drones),
            synchronized_survivors=sum(d.offline_synced_survivors for d in swarm.drones),
            first_publication_tick=min(published.values()) if published else None,
            coverage_10pct_tick=threshold_tick, survivor_delays=[
                dict(survivor=s, first_local_tick=t, published_tick=published.get(s),
                     delay_ticks=published[s]-t if s in published else None,
                     censored=s not in published)
                for s, t in sorted(local.items())])
        groups = projection(mission)
        io_free = [a-b for a,b in zip(updates, csv_times)]
        if any(v < 0 for v in io_free):
            raise ValueError('Invalid nested timing')
        result = dict(schema=1, status='complete', run_key=run_key, study=manifest['study'],
            condition=condition, seed=seed, ticks=n_ticks, manifest_hash=manifest_hash,
            source_identity=manifest['source_identity'], harness_hash=harness_hash,
            experiment=json.loads(mission.experiment.canonical_json),
            experiment_identity=mission.experiment.identity,
            runtime=manifest['runtime'], world_hash=world_hash, initial_metrics=initial,
            metrics=metrics, accounting=swarm.accounting.snapshot(), outcome=mission.outcome,
            final_summary=mission.summary(), observations=observations, series=series,
            final_group_hashes={k:digest(v) for k,v in sorted(groups.items())},
            total_survivors=len(world.mission_zones),
            energy_diagnostics=[d.energy.snapshot() for d in swarm.drones],
            timing=dict(construction_seconds=construction, update_ms=updates, csv_ms=csv_times,
                inclusive=summary(updates), excluding_csv=summary(io_free),
                observation_seconds=observer_seconds, elapsed_before_raw_write_seconds=time.perf_counter()-wall_start),
            artifacts={p.relative_to(ROOT).as_posix():file_hash(p) for p in sorted(attempt.iterdir()) if p.is_file()})
        # The fixed input schema and finite numbers are checked before publishing.
        canonical(result)
        start = time.perf_counter()
        write_json(path, result)
        checksum = file_hash(path)
        path.with_suffix('.sha256').write_text(checksum + '\n')
        write_json(attempt / 'research_write_timing.json',
                   dict(seconds=time.perf_counter()-start, raw_sha256=checksum))
        return result, False
    except Exception as exc:
        failure = dict(status='failed', seed=seed, condition=condition,
                       manifest_hash=manifest_hash, harness_hash=harness_hash,
                       tick=mission.frame if mission else None, error=repr(exc),
                       traceback=traceback.format_exc(), partial_artifacts='retained in attempt directory')
        write_json(attempt / ('failure_' + uuid.uuid4().hex + '.json'), failure)
        raise
    finally:
        config.METRICS_LOG_DIR, config.REPLAY_EXPORT_DIR = original_paths


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--only', help='Exact condition_seedN run key; all by default')
    args = p.parse_args()
    manifest, identity = checked_manifest(args.manifest)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for item in manifest['runs']:
        key = f"{item['condition']}_seed{item['seed']}"
        if args.only and args.only != key:
            continue
        result, resumed = run_one(manifest, identity, item, output)
        print(canonical(dict(run=key,resumed=resumed,coverage=result['metrics']['coverage_pct'],
                             survivors=result['metrics']['survivors_published'],
                             mean_ms=result['timing']['inclusive']['mean'])), flush=True)


if __name__ == '__main__':
    main()
