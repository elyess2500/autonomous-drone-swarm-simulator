# Autonomous Drone Swarm Simulator

A real-time autonomous drone swarm simulation built with Python and Pygame.

The project simulates coordinated reconnaissance and search-and-rescue missions across procedurally generated environments using autonomous multi-agent drone behavior, communication-aware exploration, and realistic battery/docking systems.

---

## Features

### Autonomous Drone AI

* Independent drone finite-state machines
* Frontier-based exploration
* Battery-aware task planning
* Autonomous offline operation during communication loss
* Lost-communication recovery and synchronization
* Dynamic relay-anchor roles for mesh networking

### Swarm Coordination

* Multi-drone frontier negotiation
* Sector fallback assignment
* Communication-aware path planning
* Reservation-aware congestion avoidance
* Adaptive exploration vs relay balancing

### Environment Simulation

* Procedurally generated terrain
* Obstacles and no-fly zones
* Fog of war
* Weather and wind systems
* Survivor placement and search zones

### Realistic Systems

* Physical docking and charging only at base
* Battery drain, recharge, relaunch, and stranded states
* Relay mesh communication network
* Offline autonomy with delayed synchronization

### Visualization & Replay

* Real-time Pygame dashboard and minimap
* Camera pan, zoom, and follow modes
* Drone trails, sensor rings, and communication links
* Replay export/load system
* CSV mission analytics logging
* Cinematic demo mode

---

## Tech Stack

* Python
* Pygame
* NumPy
* Pytest

---

## Demo

### Main Simulation

<img width="1747" height="1012" alt="image" src="https://github.com/user-attachments/assets/1477e0f2-3b75-4378-92e2-cba416d44776" />


### Replay / Analytics System

(Add replay or metrics screenshot here)

---

## Installation

```bash
git clone https://github.com/elyess2500/autonomous-drone-swarm-simulator.git
cd autonomous-drone-swarm-simulator

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Run

```bash
python main.py
```

---

## Tests

```bash
python -m pytest -q
python -m compileall .
python tests/gameplay_smoke.py
python tests/battery_docking_tests.py
```

---

## Controls

| Key           | Action                     |
| ------------- | -------------------------- |
| H             | Toggle heatmap             |
| C             | Toggle communication links |
| S             | Toggle sensor rings        |
| T             | Toggle drone trails        |
| F             | Toggle frontier overlay    |
| V             | Toggle reservation overlay |
| D             | Toggle AI decision labels  |
| P             | Pause / resume             |
| +/-           | Zoom camera                |
| WASD / Arrows | Pan camera                 |
| Space         | Follow next drone          |
| Q             | Reset camera               |
| R             | Restart mission            |
| E             | Export replay              |
| L             | Load replay                |
| ESC           | Quit                       |

---

## Project Structure

```text
core/
    analytics.py
    battery.py
    communication.py
    drone.py
    intelligence.py
    map.py
    mission.py
    pathfinding.py
    swarm.py

ui/
    dashboard.py
    minimap.py

tests/
    gameplay_smoke.py
    battery_docking_tests.py
```

Additional implementation details:

* `docs/architecture.md`
* `docs/algorithms.md`

---

## Current Status

The simulator includes:

* autonomous exploration,
* relay mesh communication,
* offline drone autonomy,
* replay/analytics systems,
* realistic docking and battery behavior,
* and cinematic visualization tools.

The project is actively being refined for performance optimization, additional mission behaviors, and expanded AI coordination systems.

---

## License

MIT License.
