"""Version 2 sampled-state playback. Not a simulation checkpoint or resume file."""
import base64
import bisect
import copy
from dataclasses import asdict
import json
import platform
import numpy as np
from core.experiment import Experiment, ExperimentConfig, TICK_HZ, RNG_VERSION
from core.persistence import write_json

VERSION = 2
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_CELLS = 262144
MAX_FRAMES = 18001
CAPABILITIES = {'playback': True, 'checkpoint': False, 'continuation': False}
STATES = {'idle','scanning','returning','charging','avoiding','lost_comm','stranded','failed'}
WEATHER = {'Clear','Cloudy','Windy','Stormy'}
DRONE_FIELDS = ('px','py','vx','vy','state','prev_state','path','waypoint_idx','scan_queue',
                'current_frontier_id','current_frontier_cell','assigned_sector','target_cell',
                'comm_role','relay_anchor_active','relay_anchor_cell','relay_anchor_until',
                'lost_comm_frames','offline_autonomous_active','offline_rtb_no_comms',
                'offline_synced_cells','offline_synced_survivors','stuck_recoveries',
                '_scan_timer','_fail_timer','_reroute_timer','_stuck_frames')
SWARM_FIELDS = ('frame_count','frontiers_assigned','frontiers_completed','task_cancellations',
                'comm_repair_events','full_comm_collapse_events','comm_risk_relaxation',
                'coverage_growth_per_min','emergency_recoveries')
STATS_FIELDS = ('num_drones','start_time','end_time','cells_scanned','missions_found',
                'total_missions','drone_failures','battery_returns','comm_losses','weather_events')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _bits(cells, rows, cols):
    data = np.zeros(rows*cols, dtype=np.uint8)
    for col,row in cells:
        data[row*cols+col] = 1
    return base64.b64encode(np.packbits(data, bitorder='little').tobytes()).decode('ascii')


def decode_bits(text, rows, cols):
    raw = base64.b64decode(text, validate=True)
    if len(raw) != (rows*cols+7)//8:
        raise ValueError('Invalid packed cell-mask length')
    return np.unpackbits(np.frombuffer(raw,dtype=np.uint8),bitorder='little')[:rows*cols].reshape(rows,cols).astype(bool)


def capture_world(mission):
    m=mission.game_map
    zone=lambda z:dict(col=z.col,row=z.row,radius=z.radius,zone_type=z.zone_type)
    return dict(rows=m.rows,cols=m.cols,grid=m.grid.tolist(),
                zones=[zone(z) for z in m.zones],survivors=[zone(z) for z in m.mission_zones])


def capture_frame(mission):
    m,s=mission.game_map,mission.swarm
    drones=[]
    for d in s.drones:
        item={key:copy.deepcopy(getattr(d,key)) for key in DRONE_FIELDS}
        item.update(id=d.drone_id,bat=d.battery.level,battery_max=d.battery.max,
                    energy=d.energy.snapshot(),
                    charging=d.battery.charging,
                    known_map=_bits(d.map_known,m.rows,m.cols),
                    pending_map=_bits(d.offline_known_cells,m.rows,m.cols),
                    local_survivors=list(d.mission_found),pending_survivors=sorted(d.offline_survivor_found),
                    pending_survivor_info=copy.deepcopy(d.offline_survivor_info),
                    comm=dict(direct=sorted(d.comm.connected_ids),relays=sorted(d.comm.relay_ids),
                              contact_age=d.comm.frames_since_contact,signal=d.comm.signal_quality))
        drones.append(item)
    swarm={key:copy.deepcopy(getattr(s,key)) for key in SWARM_FIELDS}
    swarm.update(assignments=[[i,*v] for i,v in sorted(s.assignments.items())],
                 sectors=[dict(id=x.idx,owner=x.assigned_drone,completed=x.completed,
                               bounds=[x.col_start,x.row_start,x.col_end,x.row_end]) for x in s.sectors],
                 frontiers=[asdict(f) for f in s.frontiers.frontiers],
                 reservations=dict(tick=s.reservations.frame,counters=dict(s.reservations.counters)))
    return dict(frame=mission.frame,weather=mission.weather.current,weather_timer=mission.weather._timer,
                fog=base64.b64encode(np.packbits(m.fog,bitorder='little').tobytes()).decode('ascii'),
                heatmap=base64.b64encode(m.heatmap.astype('<i2').tobytes()).decode('ascii'),
                found=sorted(m.mission_found),drones=drones,swarm=swarm,
                mission_state=mission.state,metrics=asdict(mission.analytics.sample(mission)),
                accounting=s.accounting.snapshot(),
                final_summary=mission.summary() if mission.completed_tick is not None else None,
                stats={key:getattr(mission.stats,key) for key in STATS_FIELDS})


def make_payload(mission, frames, world):
    experiment=json.loads(mission.experiment.canonical_json)
    experiment['identity']=mission.experiment.identity
    payload=dict(version=VERSION,kind='adss.sampled-playback',capabilities=dict(CAPABILITIES),
                 tick_hz=TICK_HZ,experiment=experiment,world=world,frames=frames,
                 recorded_through_tick=frames[-1]['frame'],export_tick=mission.frame,
                 runtime=dict(python=platform.python_version(),numpy=np.__version__),
                 sampling='hold-previous-snapshot')
    return payload


def _require(condition, message):
    if not condition: raise ValueError('Invalid replay: '+message)


def _integer(value, minimum=0, maximum=None):
    return type(value) is int and value>=minimum and (maximum is None or value<=maximum)


def validate(payload):
    """Validate before constructing a player or replacing an existing player."""
    try:
        _require(type(payload) is dict,'root must be an object')
        _require(type(payload['version']) is int and payload['version']==VERSION,
                 'unsupported version; legacy v1 lacks a self-contained world')
        _require(payload['kind']=='adss.sampled-playback','unsupported persistence kind')
        _require(canonical(payload['capabilities'])==canonical(CAPABILITIES),'unsupported capabilities')
        _require(payload['tick_hz']==TICK_HZ and type(payload['tick_hz']) is int,'tick rate')
        _require(payload['sampling']=='hold-previous-snapshot','sampling model')
        e=payload['experiment']
        cfg=ExperimentConfig.from_json(canonical(e['configuration']))
        experiment=Experiment(e['seed'],cfg)
        _require(e['rng']==RNG_VERSION and e['identity']==experiment.identity,'experiment identity/configuration mismatch')
        w=payload['world'];rows,cols=w['rows'],w['cols']
        _require(_integer(rows,1) and _integer(cols,1) and rows*cols<=MAX_CELLS,'world dimensions')
        _require(rows==cfg.settings['MAP_ROWS'] and cols==cfg.settings['MAP_COLS'],'world/config dimensions')
        _require(len(w['grid'])==rows and all(len(r)==cols and all(_integer(c,0,5) for c in r) for r in w['grid']),'world grid')
        for z in w['zones']+w['survivors']:
            _require(_integer(z['col'],0,cols-1) and _integer(z['row'],0,rows-1) and
                     _integer(z['radius'],0,max(rows,cols)) and _integer(z['zone_type'],0,5),'zone')
        _require(all(z['zone_type']==5 for z in w['survivors']),'survivor zones')
        n=cfg.settings['NUM_DRONES'];_require(_integer(n,1,1024),'drone count')
        _require(type(cfg.settings['CELL_SIZE']) in (int,float) and cfg.settings['CELL_SIZE']>0,'cell size')
        frames=payload['frames'];_require(type(frames) is list and 0<len(frames)<=MAX_FRAMES,'nonempty bounded frames array')
        previous=-1
        def cell(p):
            return type(p) in (list,tuple) and len(p)==2 and _integer(p[0],0,cols-1) and _integer(p[1],0,rows-1)
        def survivor_ids(ids):
            return type(ids) is list and len(ids)==len(set(ids)) and all(_integer(i,0,len(w['survivors'])-1) for i in ids)
        for f in frames:
            _require(_integer(f['frame']) and f['frame']>previous,'strictly increasing frame ticks')
            previous=f['frame']
            _require(f['weather'] in WEATHER and _integer(f['weather_timer']),'weather')
            decode_bits(f['fog'],rows,cols)
            _require(len(base64.b64decode(f['heatmap'],validate=True))==rows*cols*2,'heatmap length')
            _require(survivor_ids(f['found']),'global survivor IDs')
            _require(f['mission_state'] in ('running','complete'),'mission state')
            _require(type(f['metrics']) is dict and f['metrics']['frame']==f['frame'],'metrics frame')
            if 'accounting' in f:
                a = f['accounting']
                _require(a['version'] == 1, 'accounting version')
                _require(a['tick'] == f['frame'] and _integer(a['total_events']), 'accounting tick/count')
                _require(_integer(a['retention_limit'], 1) and
                         _integer(a['retained_events'], 0, min(a['total_events'], a['retention_limit'])), 'event retention')
                _require(type(a['counts']) is dict and all(type(k) is str and _integer(v)
                         for k,v in a['counts'].items()) and sum(a['counts'].values()) == a['total_events'], 'event counts')
                _require(type(a['event_hash']) is str and len(a['event_hash']) == 64 and
                         all(c in '0123456789abcdef' for c in a['event_hash']), 'event hash')
                _require(f['metrics']['event_hash'] == a['event_hash'] and
                         f['metrics']['event_count'] == a['total_events'], 'accounting metrics')
                from core.accounting import EVENT_METRICS
                _require(all(f['metrics'][field] == a['counts'].get(kind, 0)
                             for field,kind in EVENT_METRICS.items()), 'metric/event counts disagree')
                _require(f['metrics']['outcome'] in ('running','success'), 'mission outcome')
                final = f['final_summary']
                _require((final is None) == (f['metrics']['outcome'] == 'running'), 'final summary presence')
                if final is not None:
                    _require(final['version'] == 1 and final['metrics']['outcome'] == 'success' and
                             final['metrics']['completed_tick'] == f['metrics']['completed_tick'] and
                             _integer(final['metrics']['frame'], 0, f['frame']), 'final summary')
            _require(set(STATS_FIELDS)<=f['stats'].keys(),'mission statistics')
            _require(all(type(v) in (int,float) or (k=='end_time' and v is None) for k,v in f['stats'].items()),'statistics values')
            ds=f['drones'];_require(len(ds)==n and all(_integer(d['id'],0,n-1) for d in ds) and
                                   {d['id'] for d in ds}==set(range(n)),'drone identities')
            for d in ds:
                _require(set(DRONE_FIELDS)<=d.keys(),'drone fields')
                _require(d['state'] in STATES and d['prev_state'] in STATES,'drone state')
                _require(type(d['bat']) in (int,float) and type(d['battery_max']) in (int,float) and
                         0<=d['bat']<=d['battery_max'] and d['battery_max']>0,'battery range')
                _require(type(d['px']) in (int,float) and type(d['py']) in (int,float) and
                         0<=d['px']<=cols*cfg.settings['CELL_SIZE'] and 0<=d['py']<=rows*cfg.settings['CELL_SIZE'],'position')
                _require(type(d['charging']) is bool,'charging flag')
                if 'energy' in d:
                    energy = d['energy']
                    _require(type(energy) is dict and type(energy['version']) is int and energy['version'] == 1, 'energy extension version')
                    _require(all(_integer(energy[k]) for k in ('checks','rejections','route_searches')),
                             'energy diagnostic counts')
                    _require(type(energy['ready_at_base']) is bool, 'energy readiness')
                    _require(energy['last'] is None or type(energy['last']) is dict, 'energy decision')
                    _require(energy['rejections'] <= energy['checks'], 'energy rejection count')
                _require(type(d['path']) is list and type(d['scan_queue']) is list,'path/queue arrays')
                _require(all(cell(p) for p in d['path']+d['scan_queue']),'path/queue cells')
                _require(_integer(d['waypoint_idx']),'waypoint index')
                for key in ('vx','vy'):
                    _require(type(d[key]) in (int,float),'velocity')
                for key in ('current_frontier_cell','target_cell','relay_anchor_cell'):
                    _require(d[key] is None or cell(d[key]),key)
                for key in ('current_frontier_id','assigned_sector'):
                    _require(d[key] is None or _integer(d[key]),key)
                for key in ('relay_anchor_active','offline_autonomous_active','offline_rtb_no_comms'):
                    _require(type(d[key]) is bool,key)
                for key in ('relay_anchor_until','lost_comm_frames','offline_synced_cells','offline_synced_survivors',
                            'stuck_recoveries','_scan_timer','_fail_timer','_reroute_timer','_stuck_frames'):
                    _require(_integer(d[key]),key)
                _require(d['comm_role'] in ('explorer','relay'),'radio role')
                decode_bits(d['known_map'],rows,cols);decode_bits(d['pending_map'],rows,cols)
                _require(survivor_ids(d['local_survivors']) and survivor_ids(d['pending_survivors']),'local survivor IDs')
                _require(type(d['pending_survivor_info']) is dict,'pending survivor metadata')
                comm=d['comm']
                _require(_integer(comm['contact_age']) and 0<=comm['signal']<=1,'communication state')
                _require(all(_integer(i,-1,n-1) for i in comm['direct']+comm['relays']),'radio IDs')
            sw=f['swarm'];_require(set(SWARM_FIELDS)<=sw.keys(),'swarm fields')
            if any('energy' in d for d in f['drones']):
                _require(all('energy' in d for d in f['drones']), 'incomplete energy extension')
                for metric, field in (('energy_checks','checks'),('energy_infeasible_checks','rejections'),
                                      ('energy_route_searches','route_searches')):
                    _require(_integer(f['metrics'][metric]) and f['metrics'][metric] ==
                             sum(d['energy'][field] for d in f['drones']), 'energy metric disagreement')
                _require(_integer(f['metrics']['energy_returns']), 'energy return count')
                if 'accounting' in f:
                    _require(f['metrics']['energy_returns'] == f['accounting']['counts'].get('energy_return',0),
                             'energy return event disagreement')
            _require(sw['frame_count']==f['frame'],'swarm tick')
            _require(type(sw['assignments']) is list and type(sw['sectors']) is list and type(sw['frontiers']) is list,'ownership projections')
            _require(all(len(a)==3 and _integer(a[0],0,n-1) and a[1] in ('frontier','sector','relay') and _integer(a[2]) for a in sw['assignments']),'assignments')
            _require(len({a[0] for a in sw['assignments']})==len(sw['assignments']),'duplicate assignment owner')
            for sector in sw['sectors']:
                _require(_integer(sector['id']) and (sector['owner'] is None or _integer(sector['owner'],0,n-1)) and type(sector['completed']) is bool,'sector')
                _require(len(sector['bounds'])==4 and cell(sector['bounds'][:2]) and _integer(sector['bounds'][2],1,cols) and _integer(sector['bounds'][3],1,rows),'sector bounds')
            for frontier in sw['frontiers']:
                _require(_integer(frontier['frontier_id']) and cell([frontier['col'],frontier['row']]) and
                         (frontier['assigned_drone'] is None or _integer(frontier['assigned_drone'],0,n-1)),'frontier')
            _require(type(sw['reservations']['counters']) is dict,'reservation counters')
            _require(all(_integer(v) for v in sw['reservations']['counters'].values()),'reservation counter values')
        _require(frames[0]['frame']==0,'initial tick-zero snapshot required')
        _require(payload['recorded_through_tick']==frames[-1]['frame'] and
                 _integer(payload['export_tick'],frames[-1]['frame']),'recording extent')
        # Reject NaN/Infinity anywhere, including diagnostic fields.
        canonical(payload)
        return payload
    except (KeyError,TypeError,AttributeError,OverflowError,RecursionError) as exc:
        raise ValueError(f'Invalid replay structure: {exc}') from exc


def save(path,payload,*,overwrite=False):
    validate(payload)
    _require(len(canonical(payload).encode())<=MAX_FILE_BYTES,'file exceeds 128 MiB limit')
    write_json(path,payload,overwrite=overwrite)


def load(path):
    try:
        with open(path,'rb') as f:
            raw=f.read(MAX_FILE_BYTES+1)
        _require(len(raw)<=MAX_FILE_BYTES,'file exceeds 128 MiB limit')
        def pairs(items):
            result={}
            for k,v in items:
                _require(k not in result,'duplicate JSON key '+k)
                result[k]=v
            return result
        return validate(json.loads(raw,object_pairs_hook=pairs))
    except (UnicodeError,json.JSONDecodeError,RecursionError) as exc:
        raise ValueError(f'Invalid or truncated replay JSON: {exc}') from exc


class ReplayPlayer:
    """Detached read-only-by-API view. State between samples is held, not invented."""
    def __init__(self,payload):
        self._payload=copy.deepcopy(validate(payload))
        self._ticks=[f['frame'] for f in self._payload['frames']]
        self.tick=0
        self.status='completed' if self.end_tick==0 else 'playing'

    @property
    def seed(self):return self._payload['experiment']['seed']
    @property
    def identity(self):return self._payload['experiment']['identity']
    @property
    def end_tick(self):return self._ticks[-1]
    @property
    def export_tick(self):return self._payload['export_tick']
    @property
    def world(self):return copy.deepcopy(self._payload['world'])
    @property
    def configuration(self):return copy.deepcopy(self._payload['experiment']['configuration']['settings'])
    @property
    def current(self):return copy.deepcopy(self._payload['frames'][bisect.bisect_right(self._ticks,self.tick)-1])

    def advance(self):
        if self.status=='playing':self.seek(min(self.end_tick,self.tick+1))

    def seek(self,tick):
        if not _integer(tick,0,self.end_tick):raise ValueError('Replay seek tick is outside recording')
        self.tick=tick
        self.status='completed' if tick==self.end_tick else 'playing'

    def restore_checkpoint(self):
        raise NotImplementedError('Sampled playback is not a checkpoint; continuation is unsupported')

    def resume_live(self):
        raise NotImplementedError('Playback cannot resume live simulation; start a new mission explicitly')
