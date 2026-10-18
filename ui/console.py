"""Operator presentation. All derived values are read-only; UI state stays here.

Drone telemetry is simulator instrumentation, including disconnected agents.
Terrain/survivor display uses published knowledge unless DEBUG is explicit.
"""
from dataclasses import dataclass
import math
import pygame
import config
from core.utils import get_font

BG = (12, 18, 27)
PANEL = (21, 30, 42)
LINE = (52, 68, 85)
TEXT = (231, 239, 246)
MUTED = (160, 178, 194)
ACCENT = (103, 216, 207)
WARN = (243, 193, 112)
DANGER = (242, 137, 144)
MIN_SIZE = (1100, 760)
SETTINGS = (
    ('Communication tree', 'show_comm'), ('Sensor rings', 'show_sensor'),
    ('All routes', 'show_trail'), ('Frontiers / sectors', 'show_frontiers'),
    ('Reservation occupancy', 'show_reservations'), ('Decision labels', 'show_decisions'),
    ('Published scan heatmap', 'show_heatmap'), ('Dashboard', 'show_dashboard'),
    ('Recent events', 'show_events'), ('Navigation minimap', 'show_minimap'),
    ('DEBUG / ground truth', 'show_truth'),
)
STATE_STYLE = {
    'idle': ('IDLE', MUTED, 'circle'), 'scanning': ('SCAN', ACCENT, 'diamond'),
    'returning': ('RETURN', WARN, 'triangle'), 'charging': ('CHARGE', (145, 182, 249), 'square'),
    'lost_comm': ('LOST', WARN, 'diamond'), 'failed': ('FAILED', DANGER, 'cross'),
    'stranded': ('STRANDED', DANGER, 'square'), 'avoiding': ('AVOID', (199, 170, 241), 'triangle'),
    'relay': ('RELAY', (164, 182, 246), 'square'), 'ready': ('READY', (145, 182, 249), 'square'),
}
EVENT_LABELS = {
    'survivor_published': 'Survivor published', 'task_completed': 'Task completed',
    'task_cancelled': 'Task cancelled', 'energy_return': 'Energy return',
    'charging_started': 'Charging started', 'charging_completed': 'Departure ready',
    'relaunch': 'Departed base', 'partition': 'Radio disconnected', 'reconnect': 'Radio reconnected',
    'lost_comm_entry': 'Recovery mode entered', 'hardware_failure': 'Hardware failure',
    'stranded': 'Stranded', 'backoff_initiated': 'Traffic backoff',
    'backoff_exhausted': 'Traffic blocked', 'mission_completed': 'Mission completed',
}


def text(surf, value, x, y, size=14, color=TEXT, bold=False, width=None):
    font = get_font(size, bold=bold)
    value = str(value)
    if width is not None:
        original = value
        while value and font.size(value)[0] > width: value = value[:-1]
        if value != original:
            value = value[:-3] + '...' if len(value) > 3 else ''
    surf.blit(font.render(value, True, color), (int(x), int(y)))


def duration(tick):
    seconds = int(tick) // 60
    return f'{seconds//60:02d}:{seconds%60:02d}'


def style(drone):
    key = drone.state
    if key == 'idle' and getattr(drone, '_ready_at_base', False): key = 'ready'
    elif key not in ('failed','stranded','lost_comm','returning','charging') and drone.relay_anchor_active: key = 'relay'
    return STATE_STYLE.get(key, (key.upper(), MUTED, 'circle'))


def visible_survivors(zones, found, truth=False):
    return [(i,z) for i,z in enumerate(zones) if truth or i in found]


def recent_events(ledger, limit=4):
    # No consumption, new counters, local survivor locations, or synthetic events.
    chosen = [e for e in ledger.records if e.kind in EVENT_LABELS]
    return tuple(chosen[-limit:])


@dataclass(frozen=True)
class Layout:
    viewport: pygame.Rect
    sidebar: pygame.Rect
    footer: pygame.Rect
    events: pygame.Rect

    @classmethod
    def for_size(cls, size, dashboard=True, events=True):
        w,h = size
        side = 340 if dashboard else 0
        area = pygame.Rect(20, 118, w-40-side-(16 if side else 0), h-166-(102 if events else 0))
        ratio = config.MAP_PIXEL_W/config.MAP_PIXEL_H
        width = min(area.w, int(area.h*ratio)); height = int(width/ratio)
        viewport = pygame.Rect(area.x+(area.w-width)//2, area.y+(area.h-height)//2, width, height)
        return cls(viewport, pygame.Rect(w-side-20,118,side,h-166),
                   pygame.Rect(20,h-34,w-40,26), pygame.Rect(20,h-142,area.w,92))


def world_to_view(point, camera, rect):
    w,h = config.MAP_PIXEL_W,config.MAP_PIXEL_H
    if camera.zoom < .99:
        sw,sh = int(w*camera.zoom),int(h*camera.zoom)
        x=point[0]*sw/w+(w-sw)//2; y=point[1]*sh/h+(h-sh)//2
    else:
        zoom=max(1.,camera.zoom);cw,ch=max(1,int(w/zoom)),max(1,int(h/zoom))
        x=(point[0]-int(max(0,min(camera.x,w-cw))))*w/cw
        y=(point[1]-int(max(0,min(camera.y,h-ch))))*h/ch
    return rect.x+x*rect.w/w,rect.y+y*rect.h/h


def view_to_world(point, camera, rect):
    origin=world_to_view((0,0),camera,rect);unit=world_to_view((1,1),camera,rect)
    return ((point[0]-origin[0])/(unit[0]-origin[0]),(point[1]-origin[1])/(unit[1]-origin[1]))


def select_at(point, drones, camera, rect):
    if not rect.collidepoint(point): return None
    distances = [(math.dist(point,world_to_view((d.px,d.py),camera,rect)),d.drone_id) for d in drones]
    distance,ident = min(distances,default=(math.inf,None))
    return ident if distance <= 18 else None


def glyph(surf, point, shape, color, size=6):
    x,y = map(int,point)
    if shape == 'diamond':pygame.draw.polygon(surf,color,[(x,y-size),(x+size,y),(x,y+size),(x-size,y)],2)
    elif shape == 'triangle':pygame.draw.polygon(surf,color,[(x,y-size),(x+size,y+size),(x-size,y+size)],2)
    elif shape == 'square':pygame.draw.rect(surf,color,(x-size,y-size,size*2,size*2),2)
    elif shape == 'cross':
        pygame.draw.line(surf,color,(x-size,y-size),(x+size,y+size),2)
        pygame.draw.line(surf,color,(x-size,y+size),(x+size,y-size),2)
    else:pygame.draw.circle(surf,color,(x,y),size,2)


def draw_world(surface, world, swarm, flags, selected):
    cell = config.CELL_SIZE
    truth = flags.get('show_truth',False)
    palette = ((31,46,58),(82,92,105),(108,55,65),(115,87,55),(40,76,105),(31,46,58))
    surface.fill((13,21,31))
    heatmax=max(1,int(world.heatmap.max())) if flags.get('show_heatmap') else 1
    for r in range(world.rows):
        for c in range(world.cols):
            if not truth and not world.fog[r,c]:continue
            ct=int(world.grid[r,c]);rect=pygame.Rect(c*cell,r*cell,cell,cell)
            color=palette[ct]
            if flags.get('show_heatmap') and world.fog[r,c] and world.heatmap[r,c]:
                t=min(1,world.heatmap[r,c]/heatmax);color=(int(40+100*t),int(70+50*t),90)
            pygame.draw.rect(surface,color,rect)
            if ct == 2:pygame.draw.line(surface,(150,105,110),rect.topleft,rect.bottomright,1)
    for i,z in visible_survivors(world.mission_zones,world.mission_found,truth):
        pos=world.cell_to_pixel(z.col,z.row);color=ACCENT if i in world.mission_found else WARN
        glyph(surface,pos,'diamond',color,8)
        text(surface,f'S{i} '+('PUBLISHED' if i in world.mission_found else 'TRUTH'),pos[0]+11,pos[1]-7,12,color)
    base=world.cell_to_pixel(config.BASE_COL,config.BASE_ROW)
    pygame.draw.circle(surface,LINE,base,config.BASE_DOCKING_RADIUS_PX,1)
    glyph(surface,base,'square',TEXT,9);text(surface,'BASE',base[0]+12,base[1]+10,12,TEXT)
    if flags.get('show_frontiers'):
        for sector in swarm.sectors:
            if sector.assigned_drone is None:continue
            pygame.draw.rect(surface,LINE,(sector.col_start*cell,sector.row_start*cell,
                (sector.col_end-sector.col_start)*cell,(sector.row_end-sector.row_start)*cell),1)
        for f in swarm.frontiers.frontiers:
            if f.assigned_drone is not None:glyph(surface,world.cell_to_pixel(f.col,f.row),'circle',MUTED,3)
    if flags.get('show_reservations'):
        for c,r,tick in swarm.reservations.debug_cells():
            pygame.draw.rect(surface,(92,65,98),(c*cell,r*cell,cell,cell),1)
    if flags.get('show_comm'):
        by_id={d.drone_id:d for d in swarm.drones}
        for d in swarm.drones:
            if -1 in d.comm.connected_ids:pygame.draw.line(surface,(59,110,112),base,(d.px,d.py),1)
        manager=swarm.comm_manager()
        for child,parent in getattr(manager,'relay_links',()):
            if child in by_id and parent in by_id:
                a,b=by_id[child],by_id[parent]
                pygame.draw.line(surface,(76,104,145),(a.px,a.py),(b.px,b.py),1)
    for d in swarm.drones:
        label,color,shape=style(d);chosen=d.drone_id==selected
        if chosen or flags.get('show_trail'):
            route=[(d.px,d.py)]+[world.cell_to_pixel(*p) for p in d.path[d.waypoint_idx:]]
            if len(route)>1:pygame.draw.lines(surface,color,False,route,2 if chosen else 1)
            if d.target_cell:glyph(surface,world.cell_to_pixel(*d.target_cell),'square',color,5)
        if flags.get('show_sensor'):pygame.draw.circle(surface,LINE,(int(d.px),int(d.py)),config.DRONE_SENSOR_RADIUS*cell,1)
        if chosen:pygame.draw.circle(surface,TEXT,(int(d.px),int(d.py)),13,2)
        glyph(surface,(d.px,d.py),shape,color)
        if flags.get('show_decisions'):text(surface,d.decision,d.px+9,d.py+4,11,MUTED,width=210)


def drone_details(d):
    last=d.energy.last or {};estimate=last.get('estimate',{})
    margin=last.get('margin')
    task=f'Frontier {d.current_frontier_id}' if d.current_frontier_id is not None else (
        f'Sector {d.assigned_sector}' if d.assigned_sector is not None else 'No exploration task')
    return [
        ('State',style(d)[0]),('Battery',f'{100*d.battery.pct:.0f}%'),
        ('Physical radio','CONNECTED' if d.comm.is_connected else 'DISCONNECTED'),
        ('Role','Relay anchor' if d.relay_anchor_active else 'Explorer'),('Work',task),
        ('Target',str(d.target_cell) if d.target_cell else '--'),
        ('Next waypoint',str(d.path[d.waypoint_idx]) if d.waypoint_idx<len(d.path) else '--'),
        ('Relay anchor',str(d.relay_anchor_cell) if d.relay_anchor_active else '--'),
        ('Route / queued work',f'{max(0,len(d.path)-d.waypoint_idx)} / {len(d.scan_queue)}'),
        ('Last energy decision',last.get('reason','Not assessed')),
        ('Est. charge / reserve',f"{estimate['total']:.1f} / {estimate['reserve']:.1f}" if estimate.get('total') is not None else 'No valid route' if estimate else '--'),
        ('Decision margin',f'{margin:+.1f} charge' if margin is not None else '--'),
        ('Traffic','WAIT' if getattr(d,'_collision_waiting',False) else ('BACKOFF' if getattr(d,'_yield_target',None) else 'Clear')),
        ('Private pending',f'{len(d.offline_known_cells)} cells / {len(d.offline_survivor_found)} reports'),
    ]


def draw_sidebar(screen, rect, mission, selected, holder):
    pygame.draw.rect(screen,PANEL,rect,border_radius=8)
    x,y,w=rect.x+16,rect.y+16,rect.w-32
    metrics=mission.analytics.sample(mission);swarm=mission.swarm
    text(screen,'MISSION OVERVIEW',x,y,13,ACCENT,True);y+=26
    text(screen,f'{metrics.coverage_pct:.1f}%',x,y,32,TEXT,True)
    text(screen,'COVERAGE',x+155,y+15,12,MUTED);y+=48
    connected=sum(d.comm.is_connected for d in swarm.drones)
    rows=[('Survivors published',f'{metrics.survivors_published} / {len(mission.game_map.mission_zones)}'),
          ('Physical connectivity',f'{connected} / {len(swarm.drones)}'),
          ('Tasks completed',str(metrics.task_completions)),
          ('Charging / unavailable',f'{sum(d.state=="charging" for d in swarm.drones)} / {metrics.failed_drones+metrics.stranded_drones}')]
    for label,value in rows:
        text(screen,label,x,y,13,MUTED);text(screen,value,x+w-64,y,13,TEXT);y+=22
    y+=12;pygame.draw.line(screen,LINE,(x,y),(x+w,y));y+=14
    text(screen,'FLEET  /  CLICK TO INSPECT',x,y,12,ACCENT,True);y+=24
    holder.drone_rects={}
    # Pagination keeps large swarms inspectable without pushing inspector out.
    page=getattr(holder,'fleet_page',0);drones=swarm.drones[page*8:page*8+8]
    for i,d in enumerate(drones):
        tile=pygame.Rect(x+(i%2)*(w//2+2),y+(i//2)*37,w//2-4,32)
        holder.drone_rects[d.drone_id]=tile
        pygame.draw.rect(screen,(33,48,61),tile,border_radius=4)
        label,color,shape=style(d)
        if d.drone_id==selected:pygame.draw.rect(screen,ACCENT,tile,2,border_radius=4)
        glyph(screen,(tile.x+12,tile.centery),shape,color,4)
        text(screen,f'D{d.drone_id} {label}',tile.x+23,tile.y+3,11,color,width=tile.w-26)
        text(screen,f'{100*d.battery.pct:.0f}% '+('LINK' if d.comm.is_connected else 'OFFLINE'),tile.x+23,tile.y+17,10,MUTED)
    y+=148
    if len(swarm.drones)>8:text(screen,f'[ / ] Fleet page {page+1}',x,y,11,MUTED);y+=16
    y+=6;pygame.draw.line(screen,LINE,(x,y),(x+w,y));y+=12
    d=next((d for d in swarm.drones if d.drone_id==selected),None)
    text(screen,f'D{selected} / SIMULATOR INSPECTOR' if d else 'SELECT A DRONE',x,y,12,ACCENT,True);y+=23
    if d:
        available=max(1,(rect.bottom-y-30)//19)
        details=drone_details(d)
        start=min(getattr(holder,'detail_scroll',0),max(0,len(details)-available))
        for label,value in details[start:start+available]:
            text(screen,label,x,y,12,MUTED,width=150)
            text(screen,value,x+151,y,12,TEXT,width=w-151);y+=19
        if available<len(details):text(screen,'Wheel over panel for more details',x,rect.bottom-16,10,MUTED)
    else:
        text(screen,'Select on map or fleet list.',x,y,13,MUTED)
        text(screen,'Telemetry includes offline agents.',x,y+24,11,MUTED,width=w)


def draw_console(screen, map_surf, camera, world, swarm, mission, dashboard, flags, fps, seed):
    layout=Layout.for_size(screen.get_size(),flags.get('show_dashboard',True),flags.get('show_events',True))
    selected=getattr(dashboard,'selected_id',None)
    screen.fill(BG)
    text(screen,'ADSS',20,17,28,ACCENT,True)
    text(screen,'AUTONOMOUS SYSTEMS / MISSION CONTROL',112,24,13,TEXT)
    state=getattr(dashboard,'app_status','LIVE')
    text(screen,f'{state}   |   {mission.outcome.upper()}   |   {duration(mission.frame)}   T{mission.frame}',20,59,15,TEXT)
    text(screen,f'Seed {seed}  /  {mission.experiment.identity[:12]}  /  {mission.weather.current}',screen.get_width()-475,24,13,MUTED)
    text(screen,f'1 tick/update = 1/60 s  |  Display {fps} FPS  |  Zoom {camera.zoom:.2f}',screen.get_width()-475,58,12,MUTED)
    pygame.draw.line(screen,LINE,(20,88),(screen.get_width()-20,88))
    truth=flags.get('show_truth',False)
    text(screen,'DEBUG / GROUND TRUTH' if truth else 'PUBLISHED MAP  /  SIMULATOR TELEMETRY',20,97,12,WARN if truth else MUTED)
    draw_world(map_surf,world,swarm,flags,selected)
    transformed=camera.render(map_surf)
    screen.blit(pygame.transform.smoothscale(transformed,layout.viewport.size),layout.viewport)
    pygame.draw.rect(screen,LINE,layout.viewport,1)
    # Constant-size text remains legible when the world is scaled down. Crowded
    # glyphs stay exact; only their optional labels may be suppressed.
    occupied=[]
    for d in sorted(swarm.drones,key=lambda d:(d.drone_id!=selected,d.drone_id)):
        pos=world_to_view((d.px,d.py),camera,layout.viewport)
        if not layout.viewport.collidepoint(pos):continue
        label,color,_=style(d)
        caption=f'D{d.drone_id}' + (' '+label if d.drone_id==selected or label not in ('SCAN','IDLE') else '')
        if not d.comm.is_connected:caption+=' !'
        width,height=get_font(13).size(caption)
        for dx,dy in ((12,-17),(12,3),(-width-12,-17),(-width-12,3),(12,21)):
            rect=pygame.Rect(pos[0]+dx,pos[1]+dy,width+4,height+2)
            if layout.viewport.contains(rect) and not any(rect.colliderect(old) for old in occupied):
                pygame.draw.rect(screen,BG,rect,border_radius=3)
                text(screen,caption,rect.x+2,rect.y,13,color)
                occupied.append(rect);break
    if flags.get('show_minimap',True) and camera.zoom>1.01:
        mini=pygame.Rect(layout.viewport.right-148,layout.viewport.bottom-116,140,102)
        # Navigation overview uses the same knowledge-filtered layer.
        screen.blit(pygame.transform.smoothscale(map_surf,mini.size),mini)
        pygame.draw.rect(screen,MUTED,mini,1)
        viewport=pygame.Rect(mini.x+camera.x/config.MAP_PIXEL_W*mini.w,mini.y+camera.y/config.MAP_PIXEL_H*mini.h,
                             mini.w/max(1,camera.zoom),mini.h/max(1,camera.zoom))
        pygame.draw.rect(screen,ACCENT,viewport,1)
        dashboard.minimap_rect=mini
    else:dashboard.minimap_rect=None
    if flags.get('show_dashboard',True):draw_sidebar(screen,layout.sidebar,mission,selected,dashboard)
    else:dashboard.drone_rects={}
    if flags.get('show_events',True):
        box=layout.events;pygame.draw.rect(screen,PANEL,box,border_radius=6)
        text(screen,'RECENT EVENTS',box.x+12,box.y+9,11,ACCENT,True)
        events=recent_events(swarm.accounting,3)
        for i,e in enumerate(reversed(events)):
            actor=f'D{e.actor}  ' if e.actor is not None else ''
            text(screen,f'{duration(e.tick)}  {actor}{EVENT_LABELS[e.kind]}',box.x+145,box.y+9+i*23,12,TEXT,width=box.w-155)
        if not events:text(screen,'No selected events yet',box.x+145,box.y+9,12,MUTED)
    text(screen,'P Pause   +/- Zoom   Arrows Pan   Space Follow   Q Reset   C Links   F Work   ? Help',20,layout.footer.y,12,MUTED)
    if getattr(dashboard,'help_visible',False):draw_help(screen)
    message=getattr(dashboard,'message','')
    if message:
        pygame.draw.rect(screen,PANEL,(20,screen.get_height()-67,screen.get_width()-40,28))
        text(screen,message,30,screen.get_height()-62,12,WARN,width=screen.get_width()-60)


def draw_help(screen):
    box=pygame.Rect(0,0,740,540);box.center=screen.get_rect().center
    pygame.draw.rect(screen,PANEL,box,border_radius=10);pygame.draw.rect(screen,ACCENT,box,1,border_radius=10)
    x,y=box.x+28,box.y+24
    text(screen,'OPERATOR GUIDE',x,y,22,ACCENT,True);y+=42
    lines=[
        'Map: published terrain only. Diamond S = published survivor.',
        'Square BASE = shared docking. Stripes = no-fly. Blue = wind.',
        'Dark = unknown. DEBUG ground truth is an explicit presentation mode.',
        'Drone glyph + text identifies state; ! means radio disconnected.',
        'Telemetry is simulator instrumentation, not a received radio feed.',
        'Click drone/card: inspect. Right click: clear. Wheel: zoom.',
        'Arrows / WASD: pan. +/-: zoom. Space: follow. Q: reset camera.',
        'P: pause. R: new mission. E: export. L: load latest replay.',
        'C: links. T: all routes. F: work. S: sensors. H: heatmap.',
        'V: reservations. D: decisions. B: dashboard. N: minimap.',
        'J: events. G: DEBUG ground truth. I: full experiment identity.',
        'Y: explicit operator rescue (changes live state). M: menu.',
        'Replay: P pause; Home restart; Left/Right seek 1 second.',
        'Click replay timeline to seek. Replay cannot resume live.',
        'Charge is abstract, not joules. Energy values are last decisions.',
        '? / F1: close help. Settings affect presentation only.',
    ]
    for line in lines:text(screen,line,x,y,13,TEXT,width=box.w-56);y+=26
