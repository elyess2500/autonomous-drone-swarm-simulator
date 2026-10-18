"""Step 5: physical delivery boundaries independent of delayed behavior state."""
import random
import numpy as np
import pytest
import config
from core.communication import CommManager
from core.drone import Drone, IDLE, SCANNING, LOST_COMM, FAILED, STRANDED, CHARGING
from core.map import Map, Zone, CELL_FREE, CELL_MISSION
from core.swarm import Swarm


@pytest.fixture
def world(monkeypatch):
    py, np_state = random.getstate(), np.random.get_state()
    monkeypatch.setattr(config, 'FAILURE_PROB_PER_FRAME', 0.0)
    monkeypatch.setattr(config, 'QUICK_DEMO_MODE', False)
    m = Map(2026)
    m.grid[:] = CELL_FREE
    m.fog[:] = False
    m.heatmap[:] = 0
    m.mission_found.clear()
    m.mission_zones = [Zone(30,15,1,CELL_MISSION),Zone(40,15,1,CELL_MISSION)]
    yield m
    random.setstate(py)
    np.random.set_state(np_state)


def agent(world, idx=0, cell=(30,15)):
    d = Drone(idx,world)
    d.px,d.py = world.cell_to_pixel(*cell)
    d.battery.level = 100
    d.has_safe_return_energy = lambda: True
    return d


def sensor_tick(d, frame=1):
    d._scan_timer = config.DRONE_SCAN_INTERVAL-1
    d._tick_scanning = lambda *args: None
    d._tick_lost_comm = lambda *args: None
    d.update(frame,'Clear',[d])


@pytest.mark.parametrize('elapsed',[1,config.SIGNAL_LOSS_FRAMES-1,config.SIGNAL_LOSS_FRAMES,config.SIGNAL_LOSS_FRAMES+100])
@pytest.mark.parametrize('offline_mode',[False,True])
def test_disconnection_gates_map_and_survivor_before_and_after_timeout(world,monkeypatch,elapsed,offline_mode):
    monkeypatch.setattr(config,'AUTONOMOUS_OFFLINE_MODE',offline_mode)
    d = agent(world)
    d.set_state(SCANNING)
    d.scan_queue = [(31,15)]
    d.comm.frames_since_contact = elapsed
    sensor_tick(d)
    assert (30,15) in d.map_known
    assert (30,15) in d.offline_known_cells
    assert 0 in d.offline_survivor_found
    assert not world.fog[15,30] and not world.mission_found
    assert (d.state == LOST_COMM) == (elapsed >= config.SIGNAL_LOSS_FRAMES)


def test_online_entry_point_cannot_bypass_disconnected_boundary(world):
    d = agent(world)
    d._scan_online(*d.cell)
    assert not world.fog.any() and not world.mission_found
    assert d.offline_known_cells and d.offline_survivor_found == {0}


def test_sync_cannot_publish_or_clear_data_while_disconnected(world):
    d = agent(world)
    d._scan_offline(*d.cell)
    pending = set(d.offline_known_cells)
    assert d._sync_offline_discoveries() == (0,0)
    assert d.offline_known_cells == pending and not world.fog.any()
    assert not world.mission_found


@pytest.mark.parametrize('lost',[False,True])
def test_reconnect_sync_is_immediate_independent_of_lost_comm(world,lost):
    d = agent(world)
    d._scan_offline(*d.cell)
    d.state = LOST_COMM if lost else IDLE
    d.comm.frames_since_contact = config.SIGNAL_LOSS_FRAMES if lost else 2
    d.px,d.py = d.base_px
    CommManager().update([d])
    d.update(1,'Clear',[d])
    assert world.fog[15,30] and world.mission_found == {0}
    assert not d.offline_known_cells and not d.offline_survivor_found
    assert d.offline_synced_cells == 29 and d.offline_synced_survivors == 1


def test_repeated_partition_rejoin_is_idempotent_locally_and_globally(world):
    d = agent(world)
    for _ in range(3):
        d.comm.connected_ids.clear()
        d._scan_offline(30,15)
        d.comm.connected_ids = {-1}
        d._sync_offline_discoveries()
    assert d.mission_found == [0]
    assert d.offline_synced_cells == 29 and d.offline_synced_survivors == 1
    assert world.heatmap[15,30] == 1


def test_disconnected_survivor_observation_does_not_read_global_found_filter(world):
    world.mission_found.add(0)
    d = agent(world)
    d._scan_offline(*d.cell)
    assert d.mission_found == [0] and d.offline_survivor_found == {0}


@pytest.mark.parametrize('same',[False,True])
def test_multiple_disconnected_observers_merge_once(world,same):
    ds = [agent(world,0),agent(world,1,(30,15) if same else (40,15))]
    for d in ds:
        d._scan_offline(*d.cell)
    assert not world.fog.any() and not world.mission_found
    for d in reversed(ds):
        d.comm.connected_ids = {-1}
        d._sync_offline_discoveries()
        assert d._sync_offline_discoveries() == (0,0)
    assert len(world.mission_found) == (1 if same else 2)
    assert sum(d.offline_synced_cells for d in ds) == (29 if same else 58)
    assert world.heatmap[15,30] == 1


def test_map_reveal_merge_is_idempotent_including_heatmap(world):
    cells = {(30,15),(31,15)}
    assert world.reveal_cells(cells) == 2
    heat = world.heatmap.copy()
    assert world.reveal_cells(cells) == 0
    assert np.array_equal(heat,world.heatmap)


def chain(world):
    ds = [agent(world,i) for i in range(3)]
    for i,d in enumerate(ds):
        d.px,d.py = d.base_px[0]+150*i,d.base_px[1]
    return ds


@pytest.mark.parametrize('state,enabled',[(FAILED,False),(STRANDED,False),(IDLE,True),(CHARGING,True)])
def test_radio_state_controls_relay_reachability(world,state,enabled):
    ds = chain(world)
    ds[1].state = state
    cm = CommManager(); cm.update(ds)
    assert ds[2].comm.is_connected == enabled
    assert ds[1].comm.is_connected == enabled


def test_relay_loss_restoration_gates_discovery_and_sync(world):
    ds = chain(world); cm = CommManager(); cm.update(ds)
    assert ds[2].comm.is_connected and -1 in ds[2].comm.relay_ids
    ds[1].set_state(FAILED); cm.update(ds)
    assert not ds[2].comm.is_connected
    ds[2]._scan_online(30,15)
    assert not world.fog[15,30]
    ds[1].set_state(IDLE); cm.update(ds)
    ds[2].update(1,'Clear',ds)
    assert world.fog[15,30] and world.mission_found == {0}


@pytest.mark.parametrize('state',[FAILED,STRANDED])
def test_disabled_radio_cannot_upload_even_with_stale_node_links(world,state):
    d = agent(world); d._scan_offline(*d.cell)
    d.set_state(state); d.comm.connected_ids = {-1}
    assert d._sync_offline_discoveries() == (0,0)
    assert not world.fog.any()


def test_docked_radio_syncs_on_base_power_at_zero_battery(world):
    d = agent(world); d._scan_offline(*d.cell)
    d.px,d.py = d.base_px; d._dock(); d.battery.level = 0
    CommManager().update([d]); d.update(1,'Clear',[d])
    assert d.comm.is_connected and world.mission_found == {0}


def test_disconnected_outbox_is_retained_until_rejoin(world):
    a,b = agent(world,0),agent(world,1,(3,3))
    a.comm.queue_message('observation',{'cell':(30,15)})
    cm = CommManager(); cm.update([a,b]); cm.broadcast([a,b])
    assert len(a.comm.outbox) == 1 and not cm.get_inbox(1)
    a.px,a.py = a.base_px
    cm.update([a,b]); cm.broadcast([a,b]); cm.broadcast([a,b])
    assert len(cm.get_inbox(1)) == 1 and not a.comm.outbox


def test_connected_component_knowledge_merge_is_order_independent(world):
    ds = chain(world); cm = CommManager(); cm.update(ds)
    for i,d in enumerate(ds):d.map_known = {(i,10)}
    cm.broadcast(ds)
    assert all(d.map_known == {(0,10),(1,10),(2,10)} for d in ds)


def test_disconnected_peers_do_not_share_a_base_knowledge_bus(world):
    ds = [agent(world,0),agent(world,1)]
    ds[0].map_known = {(30,15)}; ds[1].map_known = {(40,15)}
    cm = CommManager(); cm.update(ds); cm.broadcast(ds)
    assert ds[0].map_known == {(30,15)} and ds[1].map_known == {(40,15)}


@pytest.mark.parametrize('ratio',[0.0,1e-12,0.1])
def test_zero_and_near_zero_connectivity_are_not_healthy_defaults(world,monkeypatch,ratio):
    monkeypatch.setattr(Swarm,'_initial_assignment',lambda self:None)
    s = Swarm(world,8)
    s.last_comm_snapshot = {'connected_ratio':ratio,'weak':[]}
    risk = s._comm_risk_for_cell(s.drones[0],config.BASE_COL,config.BASE_ROW)
    assert risk == pytest.approx(max(0,config.COMM_MIN_CONNECTED_RATIO-ratio)*7)
    zero_count = s._relay_anchor_count()
    s.last_comm_snapshot['connected_ratio'] = 1e-12
    assert zero_count == s._relay_anchor_count()


def test_motion_across_radio_boundary_cannot_use_stale_pre_move_graph(world,monkeypatch):
    monkeypatch.setattr(Swarm,'_initial_assignment',lambda self:None)
    s = Swarm(world,1); d = s.drones[0]
    for name in ('_update_exploration_balance','_maintain_relay_anchors','_repair_comm_mesh',
                 '_negotiate_frontiers','_watch_coverage_stall','_assign_nearest_sector'):
        monkeypatch.setattr(s,name,lambda *args,**kwargs:None)
    d.px,d.py = d.base_px[0]+config.DRONE_COMM_RANGE-.5,d.base_px[1]
    d.set_state(SCANNING); d.scan_queue = [(30,3)]
    d.has_safe_return_energy = lambda:True
    d._tick_scanning = lambda *args:d._move_toward(d.px+10,d.py)
    d._scan_timer = config.DRONE_SCAN_INTERVAL-1
    s.update(1,'Clear')
    assert not d.comm.is_connected
    assert d.offline_known_cells and not world.fog.any()


def test_partition_rejoin_execution_is_repeatable(world):
    states=[]
    for _ in range(2):
        world.fog[:]=False;world.heatmap[:]=0;world.mission_found.clear()
        d=agent(world);cm=CommManager()
        for frame in range(1,5):
            d.px,d.py=world.cell_to_pixel(30,15) if frame%2 else d.base_px
            cm.update([d]);sensor_tick(d,frame)
        states.append((sorted(d.map_known),sorted(d.offline_known_cells),list(d.mission_found),
                       sorted(world.mission_found),world.fog.tobytes()))
    assert states[0]==states[1]


@pytest.mark.parametrize('lost',[False,True])
def test_buffer_upload_waits_for_post_motion_relay_graph(world,monkeypatch,lost):
    monkeypatch.setattr(Swarm,'_initial_assignment',lambda self:None)
    s=Swarm(world,2);relay,leaf=s.drones
    for name in ('_update_exploration_balance','_maintain_relay_anchors','_repair_comm_mesh',
                 '_negotiate_frontiers','_watch_coverage_stall','_assign_nearest_sector'):
        monkeypatch.setattr(s,name,lambda *args,**kwargs:None)
    relay.px,relay.py=relay.base_px[0]+config.DRONE_COMM_RANGE-.5,relay.base_px[1]
    leaf.px,leaf.py=leaf.base_px[0]+config.DRONE_COMM_RANGE+100,leaf.base_px[1]
    relay.state=SCANNING;relay.scan_queue=[(30,3)]
    relay._tick_scanning=lambda *args:relay._move_toward(relay.px+10,relay.py)
    leaf._scan_offline(30,15)
    leaf.state=LOST_COMM if lost else IDLE
    for d in s.drones:d.has_safe_return_energy=lambda:True
    s.update(1,'Clear')
    assert not leaf.comm.is_connected
    assert not world.fog[15,30] and not world.mission_found
    assert leaf.offline_known_cells and leaf.offline_survivor_found == {0}


def test_lost_state_does_not_recover_without_physical_link(world):
    d=agent(world);d.state=LOST_COMM;d.comm.frames_since_contact=1
    d._tick_lost_comm=lambda *args:None
    d.update(1,'Clear',[d])
    assert d.state==LOST_COMM


def test_delivery_graph_refresh_does_not_double_tick_timeout(world):
    d=agent(world);cm=CommManager()
    cm.update([d]);cm.update([d],advance_counters=False)
    assert d.comm.frames_since_contact==1


def test_disconnected_survivor_does_not_emit_a_global_alert_before_sync(world):
    d=agent(world);d._scan_offline(*d.cell)
    # Drone.alerts is drained unconditionally into Swarm.alerts by the simulator.
    assert not any('SURVIVOR' in alert for alert in d.alerts)
    d.comm.connected_ids={-1};d._sync_offline_discoveries()
    assert len([a for a in d.alerts if 'SYNCED SURVIVOR' in a])==1


def test_prolonged_partition_then_rejoin_preserves_29_cell_buffer(world):
    d=agent(world);cm=CommManager()
    for frame in range(1,config.SIGNAL_LOSS_FRAMES+31):
        cm.update([d]);sensor_tick(d,frame)
        assert not world.fog.any() and not world.mission_found
    assert d.state==LOST_COMM and len(d.offline_known_cells)==29
    d.px,d.py=d.base_px;cm.update([d]);d.update(1000,'Clear',[d])
    assert d.state!=LOST_COMM and d.offline_synced_cells==29
    assert d.offline_synced_survivors==1 and not d.offline_known_cells


def test_connected_scans_publish_and_keep_unique_local_survivors(world):
    d=agent(world);d.comm.connected_ids={-1}
    d._scan_online(*d.cell);d._scan_online(*d.cell)
    assert d.mission_found==[0] and world.mission_found=={0}
    assert not d.offline_known_cells and world.heatmap[15,30]==2
