"""Step 8 accounting validation layered on the unchanged Step 5/6 probes.

Timing uses the same instrumented Mission.update boundary as the Step 7 baseline.
Accounting extraction, hash comparison and presentation happen outside timing.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from benchmarks.step6 import measure as prior_measure, state, Presenter
from main import make_simulation
from core.mission import Mission


def measure(seed, ticks):
    original = Mission.update
    last = None
    def observed(mission):
        nonlocal last
        last = mission
        return original(mission)
    Mission.update = observed
    try:
        result = prior_measure(seed,ticks)
        result['metrics'] = asdict(last.analytics.sample(last))
        result['accounting'] = last.swarm.accounting.snapshot()
        result['summary'] = last.summary()
        result['checks'] = dict(
            paths=result['path_searches'] == result['metrics']['path_searches'],
            contacts=result['point_contact_pair_ticks'] == result['metrics']['field_contacts'],
            partitions=result['communication']['partition_events'] == result['metrics']['partitions'],
            reconnects=result['communication']['reconnect_events'] == result['metrics']['reconnects'],
            waits=result['execution_counters']['waits'] == result['metrics']['collision_waits'],
            backoffs=result['execution_counters']['recoveries'] == result['metrics']['backoffs'])
        assert all(result['checks'].values()), result['checks']
        return result
    finally:
        Mission.update = original


def matrix_run(seed, ticks, mode, fps):
    config.TARGET_FPS = fps
    m = make_simulation(seed)[2]
    presenter = Presenter(mode)
    for tick in range(ticks):
        m.update()
        presenter.draw(m,tick)
    return dict(mode=mode, fps=fps, **state(m), accounting=m.swarm.accounting.snapshot(),
                metrics=asdict(m.analytics.sample(m)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,nargs='+',default=[2026,2027,2031])
    parser.add_argument('--ticks',type=int,default=3600)
    parser.add_argument('--matrix',action='store_true')
    args=parser.parse_args()
    config.QUICK_DEMO_MODE=False; config.AUTONOMOUS_OFFLINE_MODE=True
    config.FAILURE_PROB_PER_FRAME=.003 if args.matrix else 0.
    if args.matrix: config.WEATHER_CHANGE_INTERVAL=30
    payload=dict(methodology='step8-accounting-v1; step5-physical-observation-v1',results=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='adss-step8-') as tmp:
        config.METRICS_LOG_DIR=tmp
        for seed in args.seeds:
            if args.matrix:
                for mode,fps in [('headless',60),('normal',60),('normal',30),('normal',144),
                                 ('reduced',60),('overlays_off',60),('noisy',60)]:
                    payload['results'].append(dict(seed=seed,**matrix_run(seed,args.ticks,mode,fps)))
            else:
                payload['results'].append(measure(seed,args.ticks))
            args.output.with_suffix('.partial.json').write_text(json.dumps(payload,indent=2)+'\n')
            print(f'completed seed={seed}',flush=True)
    args.output.write_text(json.dumps(payload,indent=2)+'\n')
