# Architecture

## Overview

The simulator is structured as a layered system with clear separation of concerns:

```
┌─────────────────────────────────────────┐
│               main.py                   │  ← Game loop, rendering pipeline, input
└────────────────┬────────────────────────┘
                 │
     ┌───────────┴───────────┐
     │                       │
┌────┴─────┐         ┌───────┴──────┐
│ core/    │         │ ui/          │
│ mission  │         │ dashboard    │
│ swarm    │         │ minimap      │
│ drone    │         └──────────────┘
│ map      │
│ pathfind │
│ battery  │
│ comms    │
│ utils    │
└──────────┘
```

## Module Responsibilities

### `config.py`
Single source of truth for all tunable parameters. Change values here to
adjust drone count, map size, battery drain rates, terrain density, etc.
No magic numbers elsewhere in the codebase.

### `core/map.py`
Owns the 2D grid array and all spatial data:
- Cell types (free, obstacle, no-fly, threat, wind, mission)
- Fog-of-war boolean array
- Scan-count heatmap
- Zone definitions (circular regions)
- Procedural terrain generation with cellular-automata smoothing
- Tile surface caching for efficient rendering

### `core/pathfinding.py`
Pure A* implementation with:
- Octile distance heuristic (better than Manhattan for 8-dir movement)
- Soft penalties for cells near other drones (collision avoidance)
- Goal-fallback to nearest passable cell when target is blocked
- Greedy string-pull path smoothing (line-of-sight optimization)

### `core/battery.py`
Per-drone power model. Activity-based drain rates plus storm/wind modifiers.
Alert system fires once per low/critical event per charge cycle.

### `core/communication.py`
Graph-based radio simulation:
- Direct-range matrix recomputed each sync interval
- BFS relay routing (drones act as repeaters)
- Fog-of-war merging between connected drones
- Signal quality metric (distance-attenuated)

### `core/drone.py`
Full autonomous agent with 7-state FSM:
```
IDLE → SCANNING → RETURNING → CHARGING → IDLE
            ↓           ↓
        AVOIDING    LOST_COMM
            ↓
          FAILED
```
Each state has a dedicated `_tick_*` method. Movement uses the pathfinding
module; scanning reveals the shared map; battery drain is delegated to Battery.

### `core/swarm.py`
Swarm intelligence coordinator:
- Divides map into `SECTOR_ROWS × SECTOR_COLS` sectors
- Assigns drones using nearest-sector heuristic
- Boustrophedon (lawnmower) scan order within each sector
- Dynamic rebalancing when drones fail or complete sectors

### `core/mission.py`
Top-level simulation state:
- Weather transitions (Clear → Cloudy → Windy → Stormy)
- Mission completion detection
- Statistics accumulation
- Lightweight replay buffer (positions + states every N frames)

### `ui/dashboard.py`
Stateless HUD renderer. Reads simulation state and draws:
- Drone status cards with battery bars
- Mission progress bar
- Rolling alert log
- Sector completion grid
- Controls legend

### `ui/minimap.py`
Overview thumbnail of the full map, rebuilt every 6 frames for performance.

## Data Flow

```
Mission.update()
  └── Weather.update()
  └── Swarm.update(frame, weather)
        └── CommManager.update(drones)      ← rebuild comms graph
        └── CommManager.broadcast(drones)   ← sync fog arrays
        └── for each drone: Drone.update()  ← state machine tick
        └── _rebalance()                    ← sector reassignment
```

## Rendering Pipeline (main.py)

```
1. game_map.get_tile_surface()     ← fog-of-war tiles (cached)
2. game_map.draw_heatmap_overlay() ← optional heatmap
3. game_map.draw_mission_zones()   ← rescue zone rings
4. game_map.draw_base()            ← base station marker
5. comm links (SRCALPHA overlay)   ← drone radio links
6. for drone in swarm.drones:
     drone.draw()                  ← trail, path, sensor ring, body
7. drone ID labels
8. weather effects (SRCALPHA)      ← streaks, vignette, lightning
9. particles                       ← discovery celebratory fx
10. minimap                        ← top-left overview
11. dashboard                      ← right-side HUD panel
12. mission-complete overlay        ← stats screen
```
