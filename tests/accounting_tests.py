"""Step 8 hand-calculated accounting and outcome fixtures."""
import pytest
import config
from main import make_simulation, is_mission_failed
from core.drone import FAILED


@pytest.fixture
def mission(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'METRICS_LOG_DIR', str(tmp_path))
    monkeypatch.setattr(config, 'FAILURE_PROB_PER_FRAME', 0.)
    return make_simulation(2026)[2]


def test_failure_summary_counts_once(mission):
    d = mission.swarm.drones[0]
    d._trigger_failure()
    d._trigger_failure()
    assert mission.stats.drone_failures == 1


def test_permitted_shared_base_is_not_near_miss(mission):
    assert mission.analytics.sample(mission).collision_near_misses == 0


def test_sampling_does_not_count_events(mission):
    before = mission.analytics.near_miss_count
    ds = mission.swarm.drones
    for i, d in enumerate(ds):
        d.px, d.py = 100 + 60*i, 100
    mission.analytics.sample(mission)
    ds[1].px, ds[1].py = ds[0].px, ds[0].py
    mission.analytics.sample(mission)
    assert mission.analytics.near_miss_count == before


def test_no_survivors_does_not_vacuously_complete(mission):
    mission.game_map.mission_zones.clear()
    mission.update()
    assert mission.state == 'running'


def test_temporary_all_failed_is_not_terminal_failure(mission):
    for d in mission.swarm.drones:
        d.set_state(FAILED)
    assert not is_mission_failed(mission.swarm, mission)


def test_complete_is_idempotent(mission):
    mission.frame = 60
    mission.stats.complete()
    mission.frame = 120
    mission.stats.complete()
    assert mission.stats.elapsed_seconds() == 1


def test_emergency_charge_accounting(mission):
    d = mission.swarm.drones[0]
    d.battery.level = 84
    d._dock()
    before = d.battery.level
    mission.swarm._emergency_recover_swarm()
    assert d.battery.recharged == pytest.approx(d.battery.level - before)
    assert mission.swarm.accounting.count('charging_completed') == 1
    assert d._relaunch_pending


def test_replay_contains_versioned_accounting(mission):
    from core.replay import capture_frame
    snap = capture_frame(mission)
    assert snap['accounting'] == mission.swarm.accounting.snapshot()


def test_award_complete_cancel_reassignment_are_exact(mission):
    s = mission.swarm
    d = s.drones[0]
    s._release_assignment(d, 'fixture')
    sector = next(x for x in s.sectors if x.assigned_drone is None)
    a = s.accounting
    before = {k: a.count(k) for k in ('task_awarded','task_completed','task_cancelled')}
    s._claim_assignment(d, 'sector', sector.idx)
    s._claim_assignment(d, 'sector', sector.idx)  # Retention is not a new award.
    assert a.count('task_awarded') - before['task_awarded'] == 1
    s._complete_assignment(d)
    s._complete_assignment(d)  # Cannot complete an absent task.
    assert a.count('task_completed') - before['task_completed'] == 1
    s._claim_assignment(d, 'sector', sector.idx)
    s._release_assignment(d, 'fixture cancellation')
    s._release_assignment(d, 'fixture cancellation')
    assert a.count('task_awarded') - before['task_awarded'] == 2
    assert a.count('task_cancelled') - before['task_cancelled'] == 1


@pytest.mark.parametrize('same_survivor', [True, False])
def test_disconnected_discovery_publication_duplicates(mission, same_survivor):
    from core.map import Zone, CELL_MISSION, CELL_FREE
    m, s = mission.game_map, mission.swarm
    m.grid[:] = CELL_FREE
    m.fog[:] = False
    m.mission_found.clear()
    m.mission_zones = [Zone(30,15,1,CELL_MISSION), Zone(40,15,1,CELL_MISSION)]
    a, b = s.drones[:2]
    for d, cell in ((a,(30,15)), (b,(30 if same_survivor else 40,15))):
        d.comm.connected_ids.clear()
        d.comm.relay_ids.clear()
        d._scan_offline(*cell)
        d._scan_offline(*cell)
    assert s.accounting.count('survivor_local') == 2
    assert not m.mission_found and not m.fog.any()
    assert mission.analytics.sample(mission).survivors_local == (1 if same_survivor else 2)
    for d in (a,b):
        d.comm.connected_ids = {-1}
        d._sync_offline_discoveries()
        d._sync_offline_discoveries()
    assert s.accounting.count('survivor_published') == (1 if same_survivor else 2)
    assert s.accounting.count('discovery_upload') == 2
    assert a.offline_synced_cells == 29
    assert b.offline_synced_cells == (0 if same_survivor else 29)
    assert mission.analytics.sample(mission).survivors_rescued is None
    assert s.accounting.count('survivor_rescued') == 0


@pytest.mark.parametrize('lost', [False, True])
def test_partition_reconnect_and_grace_counts(mission, lost):
    from core.drone import LOST_COMM, IDLE
    d = mission.swarm.drones[0]
    a = mission.swarm.accounting
    # All peers remain connected; change one delivery-boundary radio sample.
    for peer in mission.swarm.drones:
        peer.comm.connected_ids = {-1}
    starts = {x.drone_id:(x.px,x.py) for x in mission.swarm.drones}
    d.comm.connected_ids.clear()
    for tick in (1,2):
        mission.frame = a.tick = tick
        mission.analytics.observe(mission, starts)
    assert a.count('partition') == 1 and a.count('lost_comm_entry') == 0
    if lost:
        d.set_state(LOST_COMM)
        d.set_state(LOST_COMM)
    d.comm.connected_ids = {-1}
    if lost:
        d.set_state(IDLE)
    for tick in (3,4):
        mission.frame = a.tick = tick
        mission.analytics.observe(mission, starts)
    assert a.count('reconnect') == 1
    assert a.count('lost_comm_entry') == int(lost)
    assert a.count('lost_comm_recovery') == int(lost)


def test_collision_rejection_wait_backoff_and_retained_task(mission):
    from core.map import CELL_FREE
    from core.drone import IDLE
    s = mission.swarm
    s.game_map.grid[:] = CELL_FREE
    d, obstacle = s.drones[:2]
    d.px,d.py = s.game_map.cell_to_pixel(30,15)
    obstacle.px,obstacle.py = d.px+1,d.py
    obstacle.set_state(IDLE)
    table = s.reservations
    table.wait_limit = 1
    goal = s.assignments.get(d.drone_id)
    completed = s.accounting.count('task_completed')
    for tick in (1,2,3,4):
        s.accounting.tick = tick
        d._yield_target = None  # Model the end of each bounded sidestep.
        table.begin_tick(tick,s.drones)
        assert not table.try_move(d,(obstacle.px,obstacle.py))
    a = s.accounting
    assert a.count('collision_rejected') == a.count('collision_wait') == 4
    assert a.count('backoff_attempt') == a.count('backoff_initiated') == 2
    assert a.count('backoff_exhausted') == 1
    assert s.assignments.get(d.drone_id) == goal
    assert a.count('task_completed') == completed
    assert a.count('field_contact') == 0


def test_battery_consumption_clamps_and_charging_relaunch(mission):
    from core.drone import CHARGING
    from core.map import CELL_FREE
    d = mission.swarm.drones[0]
    mission.game_map.grid[:] = CELL_FREE
    d.battery.level = .01
    d.battery.update('moving')
    assert d.battery.consumed == pytest.approx(.01)
    d.battery.level = 84
    assert d._dock()
    assert d._dock()  # No duplicate charging entry.
    for _ in range(20):
        if d.state == CHARGING:
            d._tick_charging()
    a = mission.swarm.accounting
    assert a.count('charging_started') == a.count('charging_completed') == 1
    assert d.battery.recharged == pytest.approx(d.battery.level-84)
    assert a.count('relaunch') == 0  # Readiness alone is not departure.
    for _ in range(2):
        d._move_toward(d.px+1,d.py)
    assert a.count('relaunch') == 1
    assert d.distance_travelled_px == 2


def test_stranding_and_manual_drone_rescue_are_not_survivor_rescue(mission):
    d = mission.swarm.drones[0]
    d._strand('fixture')
    d._strand('fixture')
    assert mission.swarm.accounting.count('stranded') == 1
    assert mission.swarm.rescue_stranded_to_base() == 1
    assert mission.swarm.rescue_stranded_to_base() == 0
    assert mission.swarm.accounting.count('drone_rescued') == 1
    assert mission.analytics.sample(mission).survivors_rescued is None


def test_completion_csv_replay_summary_and_time_agree(mission):
    import csv
    from dataclasses import asdict
    from core.replay import capture_frame
    mission.game_map.mission_found = set(range(len(mission.game_map.mission_zones)))
    mission.update()
    assert mission.outcome == 'success' and mission.completed_tick == 1
    assert mission.completion_reason == 'all_survivors_published'
    assert mission.metrics.elapsed_sec == 1/60
    assert mission.summary()['metrics'] == asdict(mission.metrics)
    snap = capture_frame(mission)
    assert snap['metrics'] == asdict(mission.metrics)
    with open(mission.metrics_logger.path, newline='') as stream:
        row = list(csv.DictReader(stream))[-1]
    assert row == {k:'' if v is None else str(v) for k,v in mission.metrics.csv_row().items()}
    frozen = mission.summary()
    for _ in range(3): mission.update()
    assert mission.summary() == frozen
    assert mission.metrics.simulation_seconds == 4/60
    assert mission.metrics.elapsed_sec == 1/60
    assert mission.swarm.accounting.count('mission_completed') == 1


def test_coverage_success_does_not_claim_all_survivors_or_rescue(mission):
    mission.game_map.fog[:] = True
    mission.update()
    assert mission.completion_reason == 'coverage_target'
    assert mission.metrics.survivors_published < len(mission.game_map.mission_zones)
    assert mission.metrics.survivors_rescued is None


def test_event_retention_order_immutability_and_query():
    from dataclasses import FrozenInstanceError
    from core.accounting import Accounting
    a = Accounting(limit=2)
    for i in range(5):
        a.tick = i//2
        a.emit('test', subject=i, data=[i])
    snap = a.snapshot()
    assert snap['total_events'] == a.count('test') == 5
    assert [e.sequence for e in a.records] == [3,4]
    assert [e.tick for e in a.records] == [1,2]
    with pytest.raises(FrozenInstanceError): a.records[0].kind = 'mutated'
    snap['counts']['test'] = 99
    assert a.count('test') == 5 and len(a.records) == 2


def test_fresh_mission_resets_accounting(mission):
    mission.swarm.drones[0]._trigger_failure()
    new = make_simulation(2026)[2]
    assert new.swarm.accounting.count('hardware_failure') == 0
    assert new.swarm.accounting.count('task_awarded') == len(new.swarm.assignments)


def test_state_instantaneous_failed_distinct_from_stranded(mission):
    mission.swarm.drones[0]._trigger_failure()
    mission.swarm.drones[1]._strand('fixture')
    metrics = mission.analytics.sample(mission)
    assert metrics.failed_drones == metrics.stranded_drones == 1
    assert metrics.hardware_failures == metrics.stranded_transitions == 1


@pytest.mark.parametrize('damage', ['version','count','hash','tick'])
def test_replay_rejects_corrupt_accounting(mission, damage):
    from core.replay import capture_frame, capture_world, make_payload, validate
    snap = capture_frame(mission)
    payload = make_payload(mission,[snap],capture_world(mission))
    if damage == 'version': snap['accounting']['version'] = 999
    if damage == 'count': snap['accounting']['counts']['made_up'] = 1
    if damage == 'hash': snap['accounting']['event_hash'] = 'bad'
    if damage == 'tick': snap['accounting']['tick'] = 1
    with pytest.raises(ValueError): validate(payload)


def test_legacy_step7_frame_remains_loadable(mission):
    from core.replay import capture_frame, capture_world, make_payload, validate
    snap = capture_frame(mission)
    del snap['accounting']; del snap['final_summary']
    assert validate(make_payload(mission,[snap],capture_world(mission)))


def test_weather_return_and_coverage_summary_sources(mission):
    from core.drone import RETURNING
    from core.map import CELL_OBSTACLE
    d = mission.swarm.drones[0]
    d.set_state(RETURNING); d.set_state(RETURNING)
    assert mission.stats.battery_returns == 1  # Legacy name: all return entries.
    mission.weather._timer = mission.weather._change_interval-1
    mission.update()
    assert mission.stats.weather_events == 1
    m = mission.game_map
    assert mission.stats.cells_scanned == int((m.fog & (m.grid != CELL_OBSTACLE)).sum())
    assert mission.stats.missions_found == len(m.mission_found)


def test_actual_contact_monitor_counts_pair_ticks_not_rejections(mission):
    s = mission.swarm
    a,b = s.drones[:2]
    a.px=a.py=b.px=b.py=400
    for tick in (1,2):
        mission.frame = s.accounting.tick = tick
        starts = {d.drone_id:(d.px,d.py) for d in s.drones}
        mission.analytics.observe(mission,starts)
        mission.analytics.observe(mission,starts)  # Idempotent within tick.
    assert s.accounting.count('field_contact') == 2
    assert s.accounting.count('proximity_entered') == 1
    assert s.accounting.count('collision_rejected') == 0


def test_playback_does_not_generate_live_accounting(mission,tmp_path):
    for _ in range(6): mission.update()
    path = mission.export_replay(str(tmp_path/'replay.json'))
    before = mission.swarm.accounting.snapshot()
    mission.load_replay(path)
    for _ in range(12): mission.update()
    assert mission.swarm.accounting.snapshot() == before
    assert mission.replay_player.current['accounting'] == before


def test_event_order_and_metrics_independent_of_presentation(monkeypatch,tmp_path):
    from benchmarks.step8 import matrix_run
    monkeypatch.setattr(config,'METRICS_LOG_DIR',str(tmp_path))
    monkeypatch.setattr(config,'FAILURE_PROB_PER_FRAME',.003)
    monkeypatch.setattr(config,'TARGET_FPS',60)
    a = matrix_run(2026,24,'headless',60)
    b = matrix_run(2026,24,'noisy',144)
    for key in ('state_hash','knowledge_hash','experiment_hash','metrics','accounting'):
        assert a[key] == b[key], key


def test_average_battery_is_percent_of_capacity(mission):
    for d in mission.swarm.drones:
        d.battery.max = 200
        d.battery.level = 100
    assert mission.analytics.sample(mission).average_battery == 50


def test_replay_rejects_metric_event_count_disagreement(mission):
    from core.replay import capture_frame, capture_world, make_payload, validate
    snap = capture_frame(mission)
    snap['metrics']['task_awards'] += 1
    with pytest.raises(ValueError):
        validate(make_payload(mission,[snap],capture_world(mission)))


def test_drone_card_percent_matches_battery_capacity(mission,monkeypatch):
    import pygame
    import ui.dashboard as dashboard
    text = []
    monkeypatch.setattr(dashboard,'draw_text',lambda surface,value,*a,**kw:text.append(value))
    for d in mission.swarm.drones:
        d.battery.max = 200
        d.battery.level = 100
    pygame.font.init()
    dashboard.Dashboard()._draw_drone_cards(pygame.Surface((500,500)),0,0,400,mission.swarm,0)
    assert sum(value.strip() == '50%' for value in text) == len(mission.swarm.drones)
