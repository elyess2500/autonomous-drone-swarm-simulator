"""Read-only versioned Step 11 golden gate; reference reruns only on failure.

Normal CI uses 60 ticks. Release validation uses 3600 ticks and all three seeds.
This module never regenerates expected output or measures performance gates.
"""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT/'tests/golden/step11-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def load_bundle(directory=GOLDEN):
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest['schema'] != 1:
        raise ValueError('Unsupported golden schema; explicit review required')
    for name, expected in manifest['files'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('Golden file escapes its directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Golden integrity mismatch: {name}; do not regenerate automatically')
    actual = hashlib.sha256((ROOT/'benchmarks/step11.py').read_bytes()).hexdigest()
    # Line-ending-only checkout conversions are acceptable for the projector.
    with zipfile.ZipFile(directory/'reference.zip') as archive:
        expected_source = archive.read('benchmarks/step11.py').replace(b'\r\n', b'\n')
    if actual != manifest['projection_sha256'] and (ROOT/'benchmarks/step11.py').read_bytes().replace(b'\r\n', b'\n') != expected_source:
        raise ValueError('Differential projection changed; review/version the golden contract')
    return manifest


def require_reference_environment(manifest):
    actual = dict(platform=platform.system(), python=platform.python_version(),
                  numpy=importlib.metadata.version('numpy'),
                  pygame=importlib.metadata.version('pygame'))
    if any(actual[k] != manifest[k] for k in actual):
        raise RuntimeError(f'Golden platform mismatch: {actual}. Use --repeat-only for functional compatibility; do not claim cross-platform equality.')
    return actual


def reference_state(seed, tick, directory, bundle=GOLDEN):
    """Execute trusted repository reference code, never deserialize Python objects."""
    manifest = load_bundle(bundle)
    with tempfile.TemporaryDirectory(prefix='adss-approved-reference-') as tmp:
        checkout = Path(tmp)
        with zipfile.ZipFile(bundle/'reference.zip') as archive:
            for info in archive.infolist():
                target = (checkout/info.filename).resolve()
                if not target.is_relative_to(checkout.resolve()):
                    raise ValueError('Unsafe reference archive path')
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() != manifest['source_hashes'][info.filename]:
                    raise ValueError('Reference source integrity mismatch')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        with (directory/'reference.log').open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, 'benchmarks/step11.py', '--seeds', str(seed),
                            '--ticks', str(tick), '--dump-tick', str(tick), '--output', str(directory)],
                           cwd=checkout, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=7200)
    return json.loads((directory/f'dump_{seed}_{tick}.json').read_text(encoding='utf-8'))


def failure_evidence(seed, tick, expected_hash, actual_state, output, reference=None):
    from benchmarks.step11 import first_difference
    directory = (output/f'divergence_{seed}_{tick}_{uuid.uuid4().hex[:8]}').resolve()
    directory.mkdir(parents=True)
    (directory/'actual.json').write_text(json.dumps(actual_state, sort_keys=True), encoding='utf-8')
    detail = dict(seed=seed, first_divergent_tick=tick, expected_hash=expected_hash,
                  actual_hash=digest({k:digest(v) for k,v in actual_state.items()}))
    try:
        expected = reference if reference is not None else reference_state(seed, tick, directory)
        # Normalize tuples to JSON arrays before exact structural comparison.
        actual = json.loads(json.dumps(actual_state))
        detail['reference_hash'] = digest({k:digest(v) for k,v in expected.items()})
        detail['reference_matches_golden'] = detail['reference_hash'] == expected_hash
        detail['first_difference'] = first_difference(expected, actual)
        detail['first_divergent_group'] = next((k for k in sorted(set(expected)|set(actual))
                                                if expected.get(k) != actual.get(k)), None)
        (directory/'expected.json').write_text(json.dumps(expected, sort_keys=True), encoding='utf-8')
    except Exception as exc:
        detail['reference_diagnostic_error'] = str(exc)
    (directory/'failure.json').write_text(json.dumps(detail, indent=2)+'\n', encoding='utf-8')
    return directory


def run(seed, ticks, output, *, golden=True):
    import config
    from core.simulation import make_simulation
    from core.replay import make_payload, capture_world
    from benchmarks.step11 import projection
    from benchmarks.step9 import inspect
    manifest = load_bundle()
    if not 0 <= ticks <= manifest['ticks'] or str(seed) not in manifest['seeds']:
        raise ValueError('Golden supports seeds 2026/2027/2031 and ticks 0..3600')
    if golden:
        require_reference_environment(manifest)
    with gzip.open(GOLDEN/manifest['seeds'][str(seed)], 'rt', encoding='utf-8') as stream:
        expected = json.load(stream)
    settings = dict(manifest['config_overrides'])
    settings.update(METRICS_LOG_DIR=None, REPLAY_EXPORT_DIR=None)
    previous = {k:getattr(config,k) for k in settings}
    hashes = []
    try:
        with tempfile.TemporaryDirectory(prefix='adss-golden-') as tmp:
            settings.update(METRICS_LOG_DIR=tmp, REPLAY_EXPORT_DIR=tmp)
            for k,v in settings.items():setattr(config,k,v)
            mission = make_simulation(seed)[2]
            for tick in range(ticks+1):
                if tick:mission.update()
                state = projection(mission)
                current = digest({k:digest(v) for k,v in state.items()})
                hashes.append(current)
                if golden and current != expected['tick_hashes'][tick]:
                    evidence = failure_evidence(seed,tick,expected['tick_hashes'][tick],state,output)
                    raise AssertionError(f'FIRST divergence seed={seed} tick={tick}; evidence: {evidence}')
            result = dict(seed=seed, ticks=ticks, tick_trace_hash=digest(hashes), authoritative=inspect(mission),
                          replay_hash=digest(make_payload(mission,mission.get_replay(),capture_world(mission))),
                          csv_hash=hashlib.sha256(Path(mission.metrics_logger.path).read_bytes()).hexdigest())
            if golden and ticks == manifest['ticks']:
                for key in ('authoritative','replay_hash','csv_hash'):
                    if result[key] != expected['final'][key]:
                        output.mkdir(parents=True, exist_ok=True)
                        (output/f'final_mismatch_{seed}.json').write_text(json.dumps(dict(key=key,expected=expected['final'][key],actual=result[key]),indent=2))
                        raise AssertionError(f'Final {key} mismatch seed={seed}')
            return result
    finally:
        for k,v in previous.items():setattr(config,k,v)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticks', type=int, default=60)
    parser.add_argument('--seeds', nargs='+', type=int, default=[2026])
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/differential')
    parser.add_argument('--repeat', action='store_true')
    parser.add_argument('--repeat-only', action='store_true')
    args = parser.parse_args()
    results = []
    for seed in args.seeds:
        result = run(seed,args.ticks,args.output,golden=not args.repeat_only)
        if args.repeat or args.repeat_only:
            repeated = run(seed,args.ticks,args.output,golden=not args.repeat_only)
            if result != repeated:
                args.output.mkdir(parents=True,exist_ok=True)
                (args.output/f'repeat_mismatch_{seed}.json').write_text(json.dumps(dict(first=result,second=repeated),indent=2))
                raise AssertionError(f'Repeat mismatch seed={seed}')
        results.append(result)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'result.json').write_text(json.dumps(dict(golden=not args.repeat_only,repeat=args.repeat or args.repeat_only,results=results),indent=2)+'\n')
    print(f'PASS: {len(results)} seed(s), {args.ticks} ticks, exact '+('repeat' if args.repeat_only else 'golden'))


if __name__ == '__main__':
    main()
