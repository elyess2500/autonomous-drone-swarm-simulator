"""Step 10: retain Step 8 contact/radio/lifecycle probes and update timing.

Energy and full final state extraction happen after timed updates. The seven
presentation conditions use Step 9's independent observer checks.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from core.mission import Mission
from benchmarks.step9 import inspect, presentation


def measure(seed, ticks):
    from benchmarks.step8 import measure as prior_measure
    from core.drone import Drone
    original = Mission.update
    cancellation_count = 0
    originals = {name: getattr(Drone, name) for name in
                 ('_energy_return', '_switch_lost_comm_recovery')}
    def observe_return(method):
        def observed(drone, *args, **kwargs):
            nonlocal cancellation_count
            ledger = drone._task_owner.accounting
            returns = ledger.count('energy_return')
            cancelled = ledger.count('task_cancelled')
            result = method(drone, *args, **kwargs)
            if ledger.count('energy_return') > returns:
                cancellation_count += ledger.count('task_cancelled') - cancelled
            return result
        return observed
    for name, method in originals.items():
        setattr(Drone, name, observe_return(method))
    last = None
    def capture(mission):
        nonlocal last
        last = mission
        return original(mission)
    Mission.update = capture
    try:
        result = prior_measure(seed, ticks)
        result['energy'] = [d.energy.snapshot() for d in last.swarm.drones]
        result['authoritative'] = inspect(last)
        result['energy_task_cancellations'] = cancellation_count
        return result
    finally:
        Mission.update = original
        for name, method in originals.items():
            setattr(Drone, name, method)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seeds', type=int, nargs='+', default=[2026,2027,2031])
    p.add_argument('--ticks', type=int, default=3600)
    p.add_argument('--matrix', action='store_true')
    args = p.parse_args()
    config.QUICK_DEMO_MODE=False;config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=.003 if args.matrix else 0.
    if args.matrix:config.WEATHER_CHANGE_INTERVAL=30
    payload=dict(methodology='step10-energy-v1; step8-accounting-v1; step5-physical-observation-v1', results=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='adss-step10-') as tmp:
        config.METRICS_LOG_DIR=tmp
        for seed in args.seeds:
            if args.matrix:
                for mode,fps in [('headless',60),('normal',60),('normal',30),('normal',144),
                                 ('reduced',60),('overlays_off',60),('noisy',60)]:
                    payload['results'].append(presentation(seed,args.ticks,mode,fps))
            else:
                payload['results'].append(measure(seed,args.ticks))
            args.output.with_suffix('.partial.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
            print('completed seed',seed,flush=True)
    args.output.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
