"""Run the established presentation matrix and enforce its final-state equality."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('state_hash','knowledge_hash','rng_hash','experiment_identity','accounting',
        'metrics','summary','outcome','completion_reason')


def verify(payload):
    rows = payload['results']
    expected_modes = [('headless',60),('normal',60),('normal',30),('normal',144),
                      ('reduced',60),('overlays_off',60),('noisy',60)]
    if [(r['mode'],r['fps']) for r in rows] != expected_modes:
        raise AssertionError('Presentation matrix missing a required condition')
    baseline = {k:rows[0][k] for k in KEYS}
    for row in rows[1:]:
        for key in KEYS:
            if row[key] != baseline[key]:
                raise AssertionError(f"Presentation mismatch: {row['mode']} fps={row['fps']} field={key}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ticks',type=int,default=180)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/presentation.json')
    args = p.parse_args()
    output = args.output.resolve()
    subprocess.run([sys.executable,'benchmarks/step9.py','--matrix','--seeds','2026',
                    '--ticks',str(args.ticks),'--output',str(output)],cwd=ROOT,check=True)
    verify(json.loads(output.read_text(encoding='utf-8')))
    print('PASS: all seven presentation conditions match all nine authoritative groups')
