"""Step 7 replay identity, isolation, timing and publication regressions."""
import json
import time
from pathlib import Path
import pytest
import config
from main import make_simulation
from core.analytics import MetricsCsvLogger, MissionMetrics, load_replay
from benchmarks.step6 import state


@pytest.fixture
def recorded(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path/'csv'))
    monkeypatch.setattr(config,'REPLAY_EXPORT_DIR',str(tmp_path/'replay'))
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',0.)
    source=make_simulation(2026)[2]
    for _ in range(12):source.update()
    path=source.export_replay(str(tmp_path/'source.json'))
    return source,Path(path)


def test_different_world_load_uses_persisted_world(recorded):
    source,path=recorded;target=make_simulation(999)[2]
    target.load_replay(str(path))
    player=getattr(target,'replay_player',None)
    assert (player.seed if player else target.game_map.seed)==2026
    assert player.world['grid']==source.game_map.grid.tolist()


def test_playback_does_not_mutate_live_mission(recorded):
    _,path=recorded;target=make_simulation(999)[2];before=state(target)
    target.load_replay(str(path))
    for _ in range(30):target.update()
    assert state(target)==before


def test_playback_one_tick_not_one_sparse_sample(recorded):
    _,path=recorded;target=make_simulation(999)[2];target.load_replay(str(path))
    target.update()
    player=getattr(target,'replay_player',None)
    assert (player.tick if player else target.frame)==1


def test_replay_end_cannot_resume_live(recorded):
    _,path=recorded;target=make_simulation(999)[2];target.load_replay(str(path))
    for _ in range(30):target.update()
    assert target.replay_playback_active
    assert target.replay_player.status=='completed'
    assert target.replay_player.tick==12


def test_embedded_identity_and_private_state(recorded):
    source,path=recorded;payload=load_replay(str(path))
    assert payload['version']==2
    assert payload['experiment']['identity']==source.experiment.identity
    last=payload['frames'][-1]
    assert last['drones'][0]['path']==[list(p) for p in source.swarm.drones[0].path]
    assert 'pending_map' in last['drones'][0]
    assert 'fog' in last and 'heatmap' in last


def test_same_seed_same_second_csv_is_not_truncated(recorded,monkeypatch):
    monkeypatch.setattr(time,'strftime',lambda *a:'same-second')
    a=MetricsCsvLogger(2026);a.write(MissionMetrics(frame=1))
    old=Path(a.path).read_bytes();b=MetricsCsvLogger(2026)
    assert a.path!=b.path
    assert Path(a.path).read_bytes()==old


def test_repeated_default_exports_are_unique(recorded,monkeypatch):
    source,_=recorded;monkeypatch.setattr(time,'strftime',lambda *a:'same-second')
    a=source.export_replay();b=source.export_replay()
    assert a!=b


def test_explicit_path_requires_explicit_overwrite(recorded):
    source,path=recorded;old=path.read_bytes()
    with pytest.raises(FileExistsError):source.export_replay(str(path))
    assert path.read_bytes()==old


@pytest.mark.parametrize('payload',[{'version':999,'frames':[]}, {'version':2,'frames':'bad'}, {'frames':[]}])
def test_incomplete_or_unknown_formats_rejected(tmp_path,payload):
    p=tmp_path/'bad.json';p.write_text(json.dumps(payload))
    with pytest.raises(ValueError):load_replay(str(p))


def test_failed_serialization_has_no_partial_final(recorded,monkeypatch,tmp_path):
    source,_=recorded;path=tmp_path/'failed.json'
    def broken_dump(value,f,*args,**kwargs):
        f.write('{partial');raise OSError('simulated disk failure')
    monkeypatch.setattr(json,'dump',broken_dump)
    with pytest.raises(OSError):source.export_replay(str(path))
    assert not path.exists()


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(version=1),
    lambda p:p['experiment'].update(seed=999),
    lambda p:p['experiment']['configuration']['settings'].update(DRONE_SPEED=99),
    lambda p:p['frames'][0]['drones'][0].update(bat=-1),
    lambda p:p['frames'][0]['drones'][0].update(px=float('nan')),
    lambda p:p['frames'][0]['drones'][0].update(state='unknown'),
    lambda p:p['frames'][0]['drones'][0].pop('pending_map'),
    lambda p:p['frames'][0].update(fog='AAAA'),
    lambda p:p['world'].update(rows=0),
    lambda p:p['frames'][1].update(frame=0),
    lambda p:p.update(kind='adss.checkpoint'),
    lambda p:p['capabilities'].update(continuation=True),
    lambda p:p['frames'][0]['drones'][0].update(id=False),
])
def test_nested_schema_validation(recorded,tmp_path,mutation):
    _,path=recorded;p=json.loads(path.read_text());mutation(p)
    bad=tmp_path/'invalid.json';bad.write_text(json.dumps(p))
    with pytest.raises(ValueError):load_replay(str(bad))


@pytest.mark.parametrize('data',['{','null','{"version":2,"version":2}', '{"frames":'])
def test_malformed_truncated_duplicate_json(tmp_path,data):
    path=tmp_path/'invalid.json';path.write_text(data)
    with pytest.raises(ValueError):load_replay(str(path))


def test_private_state_roundtrip_and_detached_seek(recorded,tmp_path):
    from core.replay import capture_frame,canonical,decode_bits
    source,_=recorded;source.update();d=source.swarm.drones[0]
    d.map_known.add((20,20));d.offline_known_cells.add((20,20))
    d.mission_found=[1];d.offline_survivor_found={1}
    d.offline_survivor_info={1:{'col':20,'row':20}}
    source.game_map.fog[25,25]=True;source.game_map.heatmap[25,25]=4
    source.game_map.mission_found.add(2)
    source.weather.current='Windy'
    expected=capture_frame(source)
    path=source.export_replay(str(tmp_path/'private.json'))
    target=make_simulation(999)[2];target.load_replay(path);p=target.replay_player
    p.seek(13)
    assert canonical(p.current)==canonical(expected)
    assert decode_bits(p.current['fog'],52,72)[25,25]
    assert decode_bits(p.current['drones'][0]['pending_map'],52,72)[20,20]
    assert p.current['drones'][0]['pending_survivors']==[1]
    assert 1 not in p.current['found'] and 2 in p.current['found']
    view=p.current;view['drones'][0]['bat']=-50
    assert p.current['drones'][0]['bat']>=0
    p.seek(0);assert p.current['frame']==0
    with pytest.raises(ValueError):p.seek(14)
    with pytest.raises(NotImplementedError):p.restore_checkpoint()
    with pytest.raises(NotImplementedError):p.resume_live()


def test_snapshot_buffers_do_not_alias_live_objects(recorded):
    source,_=recorded
    frame=source.get_replay()[-1];frame['drones'][0]['path'].append([0,0])
    assert source.get_replay()[-1]!=frame


def test_atomic_publish_failure_retains_existing_file(recorded,monkeypatch,tmp_path):
    import os
    source,path=recorded;old=path.read_bytes()
    monkeypatch.setattr(os,'replace',lambda *a: (_ for _ in ()).throw(OSError('replace failed')))
    with pytest.raises(OSError):source.export_replay(str(path),overwrite=True)
    assert path.read_bytes()==old
    assert not list(tmp_path.glob('*.tmp'))


def test_atomic_csv_row_failure_retains_previous_rows(recorded,monkeypatch):
    import os
    source,_=recorded;path=Path(source.metrics_logger.path);old=path.read_bytes()
    monkeypatch.setattr(os,'replace',lambda *a: (_ for _ in ()).throw(OSError('replace failed')))
    with pytest.raises(OSError):source.metrics_logger.write(MissionMetrics(frame=60))
    assert path.read_bytes()==old


def test_explicit_overwrite_and_parent_creation(recorded,tmp_path):
    source,path=recorded
    source.export_replay(str(path),overwrite=True)
    assert load_replay(str(path))['version']==2
    target=tmp_path/'nested'/'new.json';source.export_replay(str(target))
    assert target.exists()


def test_failed_reload_does_not_replace_current_player(recorded,tmp_path):
    _,path=recorded;target=make_simulation(999)[2];target.load_replay(str(path))
    player=target.replay_player;player.advance()
    invalid=tmp_path/'invalid.json';invalid.write_text('{')
    with pytest.raises(ValueError):target.load_replay(str(invalid))
    assert target.replay_player is player and player.tick==1
    target.load_replay(str(path));assert target.replay_player.tick==0


@pytest.mark.parametrize('fps,frequency',[(60,0),(60,1),(30,1),(144,1),(60,7)])
def test_rendering_and_playback_timeline_are_independent(recorded,monkeypatch,fps,frequency):
    import pygame
    from ui.replay_view import draw_replay
    from core.replay import canonical
    _,path=recorded;target=make_simulation(999)[2];before=state(target)
    target.load_replay(str(path));player=target.replay_player
    monkeypatch.setattr(config,'TARGET_FPS',fps)
    pygame.font.init();screen=pygame.Surface((1400,850))
    frames=load_replay(str(path))['frames']
    for tick in range(1,17):
        target.update()
        if frequency and tick%frequency==0:draw_replay(screen,player)
        assert player.tick==min(tick,12)
        expected=max((f for f in frames if f['frame']<=player.tick),key=lambda f:f['frame'])
        assert canonical(player.current)==canonical(expected)
    assert state(target)==before


def test_live_export_forbidden_during_playback(recorded):
    source,path=recorded;source.load_replay(str(path))
    with pytest.raises(ValueError):source.export_replay()


def test_loading_replaces_prior_player_world_and_uses_saved_configuration(recorded,monkeypatch,tmp_path):
    source,path=recorded
    monkeypatch.setattr(config,'DRONE_SPEED',3.5)
    other=make_simulation(999)[2]
    other_path=other.export_replay(str(tmp_path/'other.json'))
    other.load_replay(str(path))
    assert other.replay_player.identity==source.experiment.identity
    assert other.replay_player.configuration['DRONE_SPEED']!=3.5
    other.load_replay(other_path)
    assert other.replay_player.seed==999
    assert other.replay_player.configuration['DRONE_SPEED']==3.5
    assert other.replay_player.world['grid']==other.game_map.grid.tolist()
    assert other.replay_player.current['found']==[]


def test_live_rng_states_untouched_by_load_seek_and_playback(recorded):
    _,path=recorded;target=make_simulation(999)[2]
    def rng_state():
        return ({k:v.getstate() for k,v in target.experiment._streams.items()},
                [d.ai_rng.getstate() for d in target.swarm.drones])
    before=rng_state();target.load_replay(str(path));target.replay_player.seek(6)
    for _ in range(15):target.update()
    assert rng_state()==before


def test_bounded_recording_is_explicit_and_does_not_invent_final_state(monkeypatch,tmp_path):
    from core.replay import ReplayPlayer
    monkeypatch.setattr(config,'REPLAY_MAX_FRAMES',2)
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    m=make_simulation(2026)[2]
    for _ in range(12):m.update()
    p=load_replay(m.export_replay(str(tmp_path/'bounded.json')))
    assert p['recorded_through_tick']==6 and p['export_tick']==12
    assert ReplayPlayer(p).end_tick==6


def test_byte_retention_limit_does_not_append_a_later_unrecorded_tail(recorded,monkeypatch,tmp_path):
    from core import replay
    source,_=recorded
    monkeypatch.setattr(replay,'MAX_FILE_BYTES',(source._replay_bytes+1)*2)
    for _ in range(6):source.update()
    payload=load_replay(source.export_replay(str(tmp_path/'limited.json')))
    assert payload['recorded_through_tick']==12
    assert payload['export_tick']==18
