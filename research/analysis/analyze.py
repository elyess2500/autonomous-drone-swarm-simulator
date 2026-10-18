"""Reproduce Step 15 paired summaries and figures from immutable raw runs."""
import argparse
import csv
import hashlib
import json
import platform
import importlib.metadata
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repository_path(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def validate_saved(path, manifest_hash, run_key, harness_hash):
    data = json.loads(path.read_text())
    if path.with_suffix('.sha256').read_text().strip() != file_hash(path):
        raise ValueError('Raw checksum mismatch: ' + path.name)
    if (data['status'] != 'complete' or data['manifest_hash'] != manifest_hash or
            data['run_key'] != run_key or data['harness_hash'] != harness_hash or
            data['metrics']['frame'] != data['ticks']):
        raise ValueError('Raw identity/status mismatch: ' + path.name)
    for rel, expected in data['artifacts'].items():
        if file_hash(ROOT / rel) != expected:
            raise ValueError('Artifact checksum mismatch: ' + rel)
    return data

CONDITIONS = ['range_90','reference','range_360','swarm_4','swarm_16']
CONTRASTS = ['range_90','range_360','swarm_4','swarm_16']


def bootstrap_difference(a, b, indices):
    delta = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    means = delta[indices].mean(axis=1)
    return dict(mean=float(delta.mean()), median=float(np.median(delta)),
                sd=float(delta.std(ddof=1)),
                ci95=np.quantile(means,[.025,.975]).tolist(),
                ci9875=np.quantile(means,[.00625,.99375]).tolist(),
                differences=delta.tolist())


def flatten(run):
    m, o = run['metrics'], run['observations']
    result = dict(seed=run['seed'],condition=run['condition'],**m,**{
        k:v for k,v in o.items() if k!='survivor_delays'})
    result.update(coverage_gain=m['coverage_pct']-run['initial_metrics']['coverage_pct'],
                  completion_fraction=m['task_completions']/m['task_awards'] if m['task_awards'] else None,
                  cancellation_fraction=m['task_cancellations']/m['task_awards'] if m['task_awards'] else None,
                  publication_fraction=m['survivors_published']/run['total_survivors'] if run['total_survivors'] else None)
    for boundary in ('inclusive','excluding_csv'):
        result.update({boundary+'_'+k:v for k,v in run['timing'][boundary].items()})
    result['update_total_seconds'] = sum(run['timing']['update_ms'])/1000
    result['csv_total_seconds'] = sum(run['timing']['csv_ms'])/1000
    result['observer_seconds'] = run['timing']['observation_seconds']
    return result


def table(path, rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def analyze(manifest_path, raw, output):
    manifest=json.loads(manifest_path.read_text());identity=digest(manifest)
    seeds=sorted({r['seed'] for r in manifest['runs']})
    runs={}
    for item in manifest['runs']:
        key=f"{item['condition']}_seed{item['seed']}"
        runs[(item['condition'],item['seed'])]=validate_saved(raw/(key+'.json'),identity,key,
                                                                manifest['runner_sha256'])
    for (condition,seed),run in runs.items():
        assert run['seed']==seed and run['condition']==condition
        assert run['ticks']==manifest['ticks']
        assert run['source_identity']==manifest['source_identity']
        assert run['experiment']['configuration']==manifest['conditions'][condition]
        assert run['experiment_identity']==digest(run['experiment'])
    assert {p.stem for p in raw.glob('*.json')}=={f'{c}_seed{s}' for c,s in runs}
    assert len(runs)==len(seeds)*len(CONDITIONS)
    for seed in seeds:
        assert len({runs[(c,seed)]['world_hash'] for c in CONDITIONS})==1,seed
    output.mkdir(parents=True,exist_ok=True)
    rows=[flatten(runs[(c,s)]) for c in CONDITIONS for s in seeds]
    table(output/'per_run.csv',rows)
    fields=['coverage_pct','coverage_gain','survivors_published','publication_fraction',
            'task_awards','task_completions','task_cancellations','completion_fraction','cancellation_fraction',
            'connectivity_exposure','majority_fraction','disconnected_agent_ticks',
            'pending_map_exposure','new_pending_map_entries','synchronized_map_cells',
            'offline_survivor_reports','synchronized_survivors','pending_survivor_exposure',
            'partitions','reconnects','lost_comm_entries','collision_waits','backoffs','field_contacts',
            'path_searches','energy_checks','energy_infeasible_checks','energy_returns',
            'charging_starts','charging_completions','relaunches','hardware_failures','stranded_transitions',
            'battery_consumed_points','battery_recharged_points',
            'inclusive_mean','inclusive_p50','inclusive_p95','inclusive_p99','inclusive_maximum',
            'excluding_csv_mean','update_total_seconds','csv_total_seconds']
    summaries=[]
    for c in CONDITIONS:
        for field in fields:
            values=np.array([r[field] for r in rows if r['condition']==c and r[field] is not None],dtype=float)
            summaries.append(dict(condition=c,metric=field,n=len(values),mean=float(values.mean()) if len(values) else None,
                median=float(np.median(values)) if len(values) else None,
                sd=float(values.std(ddof=1)) if len(values)>1 else None,
                q25=float(np.quantile(values,.25)) if len(values) else None,
                q75=float(np.quantile(values,.75)) if len(values) else None))
    table(output/'condition_summary.csv',summaries)
    indices=np.random.Generator(np.random.PCG64(1502026)).integers(0,len(seeds),size=(20000,len(seeds)))
    effects=[]
    lookup={(r['condition'],r['seed']):r for r in rows}
    for c in CONTRASTS:
        for field in fields:
            a=[lookup[c,s][field] for s in seeds];b=[lookup['reference',s][field] for s in seeds]
            if any(v is None for v in a+b):
                continue
            effect=bootstrap_difference(a,b,indices)
            low,high=effect['ci9875']
            effects.append(dict(condition=c,reference='reference',metric=field,n=len(seeds),
                primary=field=='coverage_pct',**effect,
                classification=('SUPPORTED difference' if low>0 or high<0 else 'UNSUPPORTED difference')
                    if field=='coverage_pct' else 'DESCRIPTIVE'))
    output.joinpath('effects.json').write_text(json.dumps(effects,indent=2)+'\n')
    table(output/'effects.csv',[{**{k:v for k,v in e.items() if k not in ('ci95','ci9875','differences')},
        'ci95_low':e['ci95'][0],'ci95_high':e['ci95'][1],
        'ci9875_low':e['ci9875'][0],'ci9875_high':e['ci9875'][1]} for e in effects])
    delay_rows=[]
    for (c,s),r in runs.items():
        for d in r['observations']['survivor_delays']:
            delay_rows.append(dict(condition=c,seed=s,**d))
    if delay_rows:table(output/'survivor_delays.csv',delay_rows)
    overview=dict(schema=1,manifest_hash=identity,analysis_seed=1502026,resamples=20000,
                  analysis_source_sha256=file_hash(__file__),
                  analysis_runtime=dict(python=platform.python_version(),numpy=np.__version__,
                                        matplotlib=importlib.metadata.version("matplotlib")),
                  method='paired percentile bootstrap; seed blocks; primary Bonferroni marginal 98.75%',
                  seeds=seeds,runs=len(runs),world_pairing=True,
                  raw_hashes={repository_path(p):file_hash(p) for p in sorted(raw.glob('*.json'))},
                  primary=[e for e in effects if e['primary']],
                  missing_runs=0,pilot_included=False,
                  total_update_seconds=sum(r['update_total_seconds'] for r in rows))
    output.joinpath('analysis.json').write_text(json.dumps(overview,indent=2)+'\n')
    return rows,effects,runs


def figures(rows,effects,runs,destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'svg.hashsalt':'adss-step15-v1','axes.spines.top':False,'axes.spines.right':False})
    destination.mkdir(parents=True,exist_ok=True)
    seeds=sorted({r['seed'] for r in rows})
    lookup={(r['condition'],r['seed']):r for r in rows}
    def paired(ax,conditions,field,labels,ylabel):
        x=np.arange(len(conditions))
        for s in seeds:
            ax.plot(x,[lookup[c,s][field] for c in conditions],color='#687784',alpha=.6,lw=.8,marker='o',ms=3)
        ax.plot(x,[np.mean([lookup[c,s][field] for s in seeds]) for c in conditions],
                color='#006c70',lw=2.5,marker='D',ms=6,label='Mean; thin lines = paired seeds')
        ax.set_xticks(x,labels);ax.set_ylabel(ylabel);ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2)
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    paired(axes[0,0],CONDITIONS[:3],'coverage_pct',['90','180','360'],'Published coverage (%)')
    paired(axes[0,1],CONDITIONS[:3],'connectivity_exposure',['90','180','360'],'Mean connected fraction')
    axes[0,1].set_ylim(0,1)
    for ax in axes[0]:ax.set_xlabel('Communication range (pixels); 8 drones')
    for ax,field,label in zip(axes[1],['coverage_pct','inclusive_mean'],['Published coverage (%)','Mean inclusive update (ms)']):
        paired(ax,['swarm_4','reference','swarm_16'],field,['4','8','16'],label);ax.set_xlabel('Drones; range 180 pixels')
    fig.suptitle('ADSS early search: 900 ticks, 8 paired seeds per condition\nRaw seed trajectories and means; no uncertainty bands on this figure')
    axes[0,0].legend(fontsize=8,loc='upper left')
    save(fig,destination/'paired_outcomes')
    fig,ax=plt.subplots(figsize=(9,4.5),layout='constrained')
    prim=[e for e in effects if e['primary']]
    for y,e in enumerate(prim):
        ax.scatter(e['differences'],[y]*len(seeds),marker='o',facecolors='none',edgecolors='#687784',s=28)
        lo,hi=e['ci9875'];ax.plot([lo,hi],[y,y],color='#006c70',lw=3)
        ax.plot(e['mean'],y,'D',color='#006c70',ms=7)
    ax.axvline(0,color='black',ls='--',lw=1)
    ax.set_yticks(range(4),['90 vs 180 px','360 vs 180 px','4 vs 8 drones','16 vs 8 drones'])
    ax.set_xlabel('Paired coverage difference (percentage points)')
    ax.set_title('Primary effects: 8 paired seeds; 20,000 bootstrap resamples\nDiamonds = means; lines = 98.75% marginal intervals; circles = seed differences')
    ax.grid(axis='x',alpha=.2)
    save(fig,destination/'coverage_effects')
    plt.close('all')


def save(fig,path):
    fig.savefig(path.with_suffix('.png'),dpi=180)
    fig.savefig(path.with_suffix('.svg'),metadata={'Date':None})
    fig.savefig(path.with_suffix('.pdf'),metadata={'CreationDate':None,'ModDate':None})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',default='research/manifests/main.json')
    parser.add_argument('--raw',default='research/raw/main')
    parser.add_argument('--output',default='research/processed')
    parser.add_argument('--figures',default='research/figures')
    args=parser.parse_args()
    values=analyze(Path(args.manifest),Path(args.raw),Path(args.output))
    figures(*values,Path(args.figures))
    print('PASS raw hashes, complete pairs, world equality, deterministic analysis and figures')
