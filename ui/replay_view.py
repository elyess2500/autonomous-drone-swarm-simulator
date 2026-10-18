"""Detached sampled playback presentation; no live engine references."""
import pygame
from core.replay import decode_bits
from ui.console import (BG, PANEL, LINE, TEXT, MUTED, ACCENT, WARN, STATE_STYLE,
                        text, glyph, duration, visible_survivors)


def timeline_rect(size):
    return pygame.Rect(24, size[1]-52, size[0]-48, 14)


def handle_replay_input(event, player, size):
    """Explicit seek changes only the detached player's playhead."""
    target = None
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_HOME: target = 0
        elif event.key == pygame.K_LEFT: target = max(0,player.tick-60)
        elif event.key == pygame.K_RIGHT: target = min(player.end_tick,player.tick+60)
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        rect = timeline_rect(size)
        if rect.inflate(0,16).collidepoint(event.pos):
            target = round(max(0,min(1,(event.pos[0]-rect.x)/rect.w))*player.end_tick)
    if target is None:return False
    player.seek(target)
    return True


def draw_replay(screen, player, paused=False):
    screen.fill(BG)
    world=player.world;state=player.current;cfg=player.configuration
    w,h=screen.get_size();rows,cols=world['rows'],world['cols']
    scale=min((w-382)/cols,(h-190)/rows)
    origin=(24,120)
    fog=decode_bits(state['fog'],rows,cols)
    colors=((31,46,58),(82,92,105),(108,55,65),(115,87,55),(40,76,105),(31,46,58))
    for row in range(rows):
        for col in range(cols):
            color=colors[world['grid'][row][col]] if fog[row,col] else (13,21,31)
            pygame.draw.rect(screen,color,(origin[0]+col*scale,origin[1]+row*scale,scale+1,scale+1))
    def point(px,py):return (int(origin[0]+px/cfg['CELL_SIZE']*scale),int(origin[1]+py/cfg['CELL_SIZE']*scale))
    for idx,z in visible_survivors(world['survivors'],state['found']):
        pos=point((z['col']+.5)*cfg['CELL_SIZE'],(z['row']+.5)*cfg['CELL_SIZE'])
        glyph(screen,pos,'diamond',ACCENT,7);text(screen,f'S{idx}',pos[0]+10,pos[1]-8,12,ACCENT)
    glyph(screen,point((cfg['BASE_COL']+.5)*cfg['CELL_SIZE'],(cfg['BASE_ROW']+.5)*cfg['CELL_SIZE']),'square',TEXT,8)
    panel=pygame.Rect(w-330,120,306,h-194);pygame.draw.rect(screen,PANEL,panel,border_radius=8)
    text(screen,'RECORDED SNAPSHOT',panel.x+16,panel.y+16,14,ACCENT,True)
    text(screen,f'Tick {state["frame"]} / {state["weather"]}',panel.x+16,panel.y+44,13,TEXT)
    text(screen,f'Published survivors: {len(state["found"])}',panel.x+16,panel.y+70,13,TEXT)
    for i,d in enumerate(state['drones']):
        label,color,shape=STATE_STYLE.get(d['state'],(d['state'].upper(),MUTED,'circle'))
        pos=point(d['px'],d['py']);glyph(screen,pos,shape,color)
        text(screen,f'D{d["id"]}',pos[0]+9,pos[1]-8,12,color)
        y=panel.y+110+i*30
        if y < panel.bottom-36:
            glyph(screen,(panel.x+23,y+7),shape,color,4)
            text(screen,f'D{d["id"]}  {label:<8} {100*d["bat"]/d["battery_max"]:.0f}%',panel.x+40,y,13,color)
    if len(state['drones'])>max(0,(panel.h-146)//30):
        text(screen,'Additional drones visible on map',panel.x+16,panel.bottom-28,11,MUTED)
    status='paused' if paused and player.status!='completed' else player.status
    text(screen,'ADSS / PLAYBACK',24,18,26,ACCENT,True)
    text(screen,f'{status.upper()}   {duration(player.tick)}   Tick {player.tick} / {player.end_tick}',24,59,15,TEXT)
    text(screen,f'Seed {player.seed} / {player.identity[:12]}',w-360,28,13,MUTED)
    text(screen,'SAMPLED RECORDING / PUBLISHED MAP / NO LIVE RESUME',24,93,12,WARN)
    rect=timeline_rect(screen.get_size());pygame.draw.rect(screen,LINE,rect,border_radius=4)
    filled=rect.copy();filled.w=round(rect.w*player.tick/max(1,player.end_tick))
    if filled.w:pygame.draw.rect(screen,ACCENT,filled,border_radius=4)
    text(screen,'P Play/pause   Home Restart playback   Left/Right Seek 1s   Click timeline   R New mission   M Menu',24,h-27,12,MUTED)
    extent=f'Prefix ends T{player.end_tick}; export T{player.export_tick}. ' if player.export_tick>player.end_tick else ''
    text(screen,extent+'Snapshot held between recorded samples.',24,h-76,12,MUTED,width=w-48)
