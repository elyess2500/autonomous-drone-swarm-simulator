# Autonomous Drone Swarm Simulator

A Python/Pygame simulation of coordinated autonomous drones performing
real-time reconnaissance, mapping, and search-and-rescue over a procedurally
generated grid.

## What It Does

- Runs 8 autonomous drones with independent state machines.
- Generates seeded terrain with obstacles, no-fly zones, wind zones, threat
  zones, fog of war, and survivor zones.
- Uses A* pathfinding with octile distance, smoothing, route variation, and
  soft congestion/reservation penalties.
- Coordinates the swarm with frontier exploration, sector fallback assignment,
  relay-anchor roles, and battery-aware task bidding.
- Simulates radio range, relay routing, lost-communication recovery, offline
  exploration, and sync after reconnection.
- Models battery drain, low/critical return-to-base behavior, physical docking,
  recharge, relaunch, and stranded drones.
- Renders a live Pygame UI with menu, demo mode, pause/end screens, dashboard,
  minimap, camera pan/zoom/follow, trails, sensor rings, comm links, frontier
  overlays, and replay controls.
- Writes mission metrics CSV files and can export/load replay JSON files.

## Performance

The simulator targets 60 FPS. In an audit run on this machine, simulation
updates ran at about 573 FPS equivalent without rendering; a full-overlay
software render probe ran at about 41 FPS equivalent. Actual FPS depends on
hardware, display driver, active overlays, and capture tools.

## Requirements

- Python 3.10+
- pip
- Pygame and NumPy, installed from `requirements.txt`

## Setup

```bash
# Clone or download this repository, then enter the project directory.
cd drone_swarm_simulator

# Optional but recommended:
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The app opens to a main menu with Start Mission, Demo Mode, Replay Viewer,
Settings, and Quit.

## Test

```bash
python -m pytest -q
python -m compileall .
python tests/gameplay_smoke.py
python tests/battery_docking_tests.py
```

The smoke tests create runtime metrics under `logs/`; replay exports are written
under `replays/` when triggered. These generated directories are intentionally
ignored by git.

## Controls

| Key | Action |
|-----|--------|
| `1-5` | Main menu shortcuts |
| `H` | Toggle heatmap overlay |
| `C` | Toggle communication links |
| `S` | Toggle sensor rings |
| `T` | Toggle drone trails |
| `F` | Toggle frontier overlay |
| `V` | Toggle reservation overlay |
| `D` | Toggle drone decision labels |
| `P` | Pause / resume |
| `+` / `-` | Zoom camera in / out |
| Arrow keys or `WASD` | Pan camera |
| `Space` | Cycle follow-drone camera |
| `Q` | Reset camera follow/zoom |
| `M` | Return to main menu |
| `R` | Restart with a new random map |
| `Y` | Manually rescue stranded drones |
| `E` | Export replay JSON |
| `L` | Load latest replay JSON |
| `ESC` | Quit or return to menu |

## Project Structure

```text
drone_swarm_simulator/
|-- main.py              # Entry point, app loop, menu, rendering pipeline
|-- config.py            # Tunable simulation parameters
|-- requirements.txt     # Runtime dependencies
|-- README.md
|-- LICENSE
|-- core/
|   |-- analytics.py     # Metrics, CSV logging, replay persistence
|   |-- battery.py       # Battery drain/recharge model
|   |-- communication.py # Radio range, relay routing, fog sync
|   |-- drone.py         # Individual drone agent and state machine
|   |-- intelligence.py  # Frontier map and reservation table
|   |-- map.py           # Terrain, fog of war, survivor placement
|   |-- mission.py       # Mission state, weather, replay playback
|   |-- pathfinding.py   # A* and path smoothing
|   `-- swarm.py         # Swarm coordination and task negotiation
|-- ui/
|   |-- dashboard.py     # Telemetry and mission dashboard
|   `-- minimap.py       # Overview map
|-- docs/
|   |-- architecture.md
|   `-- algorithms.md
`-- tests/
    |-- battery_docking_tests.py
    `-- gameplay_smoke.py
```

## Configuration

All primary settings live in `config.py`, including map size, drone count,
sensor range, battery thresholds, communication range, weather intervals,
frontier negotiation, reservation penalties, analytics paths, and replay paths.

## Documentation

- `docs/architecture.md` describes module responsibilities and data flow.
- `docs/algorithms.md` explains pathfinding, coverage planning, swarm
  assignment, communication routing, battery behavior, and the drone FSM.


## License

MIT. See `LICENSE`.
