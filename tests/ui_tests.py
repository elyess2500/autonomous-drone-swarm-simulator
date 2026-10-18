"""Step 13 semantic presentation contracts, not pixel-perfect goldens."""
import inspect
import ast
import pytest
import pygame
import config

pytestmark = [pytest.mark.standard, pytest.mark.graphical]


@pytest.fixture
def mission():
    from core.simulation import make_simulation
    pygame.font.init()
    return make_simulation(2026)[2]


def test_settings_display_and_controller_share_order(monkeypatch):
    import main
    import ui.presentation as p
    # Step 12's controller used dict insertion order, unlike its drawn list.
    if hasattr(p, 'SETTINGS'):
        assert main.SETTINGS is p.SETTINGS
        keys = [key for label,key in p.SETTINGS]
    else:
        node = ast.parse(inspect.getsource(main.run_app))
        flags = next(n.value for n in ast.walk(node) if isinstance(n,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='flags' for t in n.targets))
        keys = [k.value for k in flags.keys]
    pygame.font.init()
    texts=[]
    monkeypatch.setattr(p,'draw_text',lambda surf,text,*a,**kw:texts.append(text))
    flags={k:False for k in keys};flags[keys[0]]=True
    p.draw_settings_screen(pygame.Surface((1400,850)),0,flags,p.Camera(),0)
    first=next(t for t in texts if t.startswith('1.'))
    assert 'ON' in first, first


def test_operational_view_hides_unpublished_survivor(mission,monkeypatch):
    from ui.presentation import Camera, render_simulation_frame
    from ui.dashboard import Dashboard
    from ui.minimap import Minimap
    zone=mission.game_map.mission_zones[0]
    mission.game_map.fog[zone.row,zone.col]=True
    center=mission.game_map.cell_to_pixel(zone.col,zone.row)
    calls=[];original=pygame.draw.circle
    def circle(surf,color,pos,radius,*a,**kw):
        if tuple(pos)==center and tuple(color)==(255,200,0):calls.append(pos)
        return original(surf,color,pos,radius,*a,**kw)
    monkeypatch.setattr(pygame.draw,'circle',circle)
    flags={k:False for k in ('show_heatmap','show_frontiers','show_reservations','show_decisions',
                            'show_comm','show_sensor','show_trail')}
    render_simulation_frame(pygame.Surface((1400,850)),pygame.Surface((config.MAP_PIXEL_W,config.MAP_PIXEL_H)),
        Camera(),mission.game_map,mission.swarm,mission,Dashboard(),Minimap(),[],flags,60,0,2026,False)
    assert not calls, 'Revealed terrain must not publish a survivor marker'


def test_replay_hides_unpublished_survivor(mission,monkeypatch):
    from core.replay import ReplayPlayer,capture_frame,capture_world,make_payload
    from ui.replay_view import draw_replay
    mission.game_map.fog[:]=True
    player=ReplayPlayer(make_payload(mission,[capture_frame(mission)],capture_world(mission)))
    calls=[];original=pygame.draw.circle
    def circle(surf,color,*a,**kw):
        if tuple(color)==(255,200,0):calls.append(color)
        return original(surf,color,*a,**kw)
    monkeypatch.setattr(pygame.draw,'circle',circle)
    draw_replay(pygame.Surface((1400,850)),player)
    assert not calls,'Detached playback must use publication, not terrain visibility'


@pytest.mark.parametrize('size',[(1100,760),(1400,850),(1920,1080)])
def test_layout_containment_and_separation(size):
    from ui.console import Layout
    for dash in (False,True):
        for events in (False,True):
            layout=Layout.for_size(size,dash,events);window=pygame.Rect((0,0),size)
            assert window.contains(layout.viewport)
            assert window.contains(layout.footer)
            if dash:
                assert window.contains(layout.sidebar)
                assert not layout.sidebar.colliderect(layout.viewport)
            if events:assert not layout.events.colliderect(layout.viewport)


@pytest.mark.parametrize('zoom',[.75,1.,1.37,2.2])
def test_camera_transform_selection_and_reset(mission,zoom):
    from ui.console import Layout,world_to_view,view_to_world,select_at
    from ui.presentation import Camera
    camera=Camera();camera.zoom=zoom;camera.x=64;camera.y=29
    rect=Layout.for_size((1400,850)).viewport
    point=(330.,250.)
    assert view_to_world(world_to_view(point,camera,rect),camera,rect)==pytest.approx(point)
    d=mission.swarm.drones[0];d.px,d.py=point
    assert select_at(world_to_view(point,camera,rect),[d],camera,rect)==d.drone_id
    assert select_at((-100,-100),[d],camera,rect) is None
    camera.reset();assert (camera.x,camera.y,camera.zoom)==(0,0,1)


def test_survivor_publication_adapter_and_debug(mission):
    from ui.console import visible_survivors
    zones=mission.game_map.mission_zones
    assert visible_survivors(zones,set())==[]
    assert visible_survivors(zones,{1})==[(1,zones[1])]
    assert len(visible_survivors(zones,set(),True))==len(zones)


def test_state_mapping_energy_formatting_and_no_estimate_query(mission,monkeypatch):
    from ui.console import style,drone_details,STATE_STYLE
    d=mission.swarm.drones[0]
    for state in ('idle','scanning','returning','charging','lost_comm','failed','stranded','avoiding'):
        d.state=state
        assert style(d)==STATE_STYLE[state]
    d.state='idle';d._ready_at_base=True
    assert style(d)[0]=='READY'
    d._ready_at_base=False;d.relay_anchor_active=True
    assert style(d)[0]=='RELAY'
    monkeypatch.setattr(d.energy,'estimate',lambda *a,**kw:pytest.fail('Inspector ran policy estimate'))
    d.battery.max=200;d.battery.level=100
    d.energy.last={'margin':None,'reason':'route unavailable','estimate':{'total':None,'reserve':12}}
    rows=dict(drone_details(d))
    assert rows['Battery']=='50%';assert rows['Est. charge / reserve']=='No valid route'


def test_event_feed_is_bounded_filtered_nonconsuming(mission):
    from ui.console import recent_events
    ledger=mission.swarm.accounting
    for i in range(20):
        ledger.emit('survivor_local',actor=0,subject=i)
        ledger.emit('collision_wait',actor=0)
        ledger.emit('reconnect',actor=0)
    before=ledger.snapshot();records=ledger.records
    assert len(recent_events(ledger,3))==3
    assert all(e.kind=='reconnect' for e in recent_events(ledger,3))
    assert ledger.snapshot()==before and ledger.records==records


def test_replay_seek_controls_do_not_touch_live_state(mission):
    from core.replay import ReplayPlayer,capture_frame,capture_world,make_payload
    from ui.replay_view import handle_replay_input,timeline_rect,draw_replay
    from benchmarks.step9 import inspect as snapshot
    frames=[capture_frame(mission)]
    for _ in range(12):mission.update()
    frames.append(capture_frame(mission))
    player=ReplayPlayer(make_payload(mission,frames,capture_world(mission)))
    before=snapshot(mission)
    assert handle_replay_input(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RIGHT),player,(1400,850))
    assert player.status=='completed'
    draw_replay(pygame.Surface((1400,850)),player)
    assert player.tick==12
    handle_replay_input(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_HOME),player,(1400,850))
    assert player.tick==0
    rect=timeline_rect((1400,850))
    handle_replay_input(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=rect.center),player,(1400,850))
    assert player.tick==6 and snapshot(mission)==before


@pytest.mark.parametrize('size',[(1100,760),(1400,850),(1920,1080)])
def test_all_overlays_inspector_and_camera_are_observers(mission,size):
    from benchmarks.step11 import projection
    from ui.presentation import Camera,render_simulation_frame,SETTINGS
    from ui.dashboard import Dashboard
    from ui.minimap import Minimap
    for _ in range(6):mission.update()
    camera=Camera();camera.zoom=1.6;camera.x=100;camera.y=30
    dashboard=Dashboard();dashboard.selected_id=0
    flags={k:True for _,k in SETTINGS}
    screen=pygame.Surface(size);surface=pygame.Surface((config.MAP_PIXEL_W,config.MAP_PIXEL_H))
    before=projection(mission)
    render_simulation_frame(screen,surface,camera,mission.game_map,mission.swarm,mission,
                            dashboard,Minimap(),[],flags,144,90,2026,False)
    assert projection(mission)==before
    assert 0 in dashboard.drone_rects


def test_settings_toggles_are_presentation_only():
    from ui.console import SETTINGS
    assert len({key for _,key in SETTINGS})==len(SETTINGS)
    assert all(key.startswith('show_') for _,key in SETTINGS)


def test_main_compatibility_uses_supported_controller(monkeypatch):
    import main
    called=[];monkeypatch.setattr(main,'run_app',lambda:called.append(True))
    main.main();assert called==[True]


def test_controller_pause_resize_and_quit_do_not_step(mission,monkeypatch):
    import main
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    monkeypatch.setattr(main,'make_simulation',lambda *a,**kw:(mission.game_map,mission.swarm,mission,2026))
    events=iter([
        [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_1)],
        [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_p),
         pygame.event.Event(pygame.VIDEORESIZE,w=900,h=600)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    monkeypatch.setattr(pygame.event,'get',lambda:next(events))
    with pytest.raises(SystemExit):main.run_app()
    assert mission.frame==1


@pytest.mark.parametrize('size',[(1100,760),(1400,850),(1920,1080)])
def test_menu_labels_center_rendered_rects_in_all_states(mission,monkeypatch,size):
    import ui.presentation as presentation
    from benchmarks.step11 import projection
    recorded={};draw_text=presentation.draw_text
    def record(surf,value,*args,**kwargs):
        rect=draw_text(surf,value,*args,**kwargs)
        if value[:1] in '12345' and value[1:3]=='. ':recorded[value]=rect.copy()
        return rect
    monkeypatch.setattr(presentation,'draw_text',record)
    screen=pygame.Surface(size);before=projection(mission)
    # There is no separate hover style: selected controls the highlight. Test
    # every highlight and the unhighlighted state, preserving actual font bounds.
    for selected in (-1,0,1,2,3,4):
        recorded.clear()
        buttons=presentation.draw_menu_screen(screen,selected,0)
        assert len(buttons)==len(recorded)==5
        for index,(label,button) in enumerate(buttons):
            rect=recorded[f'{index+1}. {label}']
            assert button==pygame.Rect(size[0]//2-170,275+index*52,340,38)
            assert rect.center==button.center
            assert button.contains(rect)
    assert projection(mission)==before
