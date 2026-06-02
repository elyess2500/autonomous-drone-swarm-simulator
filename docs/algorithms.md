# Algorithms & AI Techniques

## 1. A* Pathfinding

**File:** `core/pathfinding.py`

Standard A* with the **octile distance** heuristic, which correctly accounts
for diagonal movement:

```
h(n) = max(Δx, Δy) + (√2 − 1) × min(Δx, Δy)
```

This is admissible and more accurate than Manhattan distance for 8-directional
grids, producing shorter and more natural-looking paths.

**Collision softening:** other drones' cells are penalised (+2.0 cost) but not
hard-blocked, allowing pass-through in tight corridors.

**Goal fallback:** if the target cell is blocked (e.g. an obstacle was placed
there), a BFS fan-out finds the nearest passable alternative.

**Path smoothing (string-pull):** a greedy line-of-sight pass removes redundant
intermediate waypoints.  Only waypoints where LoS fails are kept, reducing
the number of sharp turns and saving movement overhead.

---

## 2. Cellular-Automata Terrain Generation

**File:** `core/map.py → Map._generate()`

1. Randomly fill grid with obstacles at density `OBSTACLE_DENSITY`.
2. Run 3 smoothing iterations:
   - A cell survives as an obstacle if it has ≥2 obstacle neighbours.
   - A free cell becomes an obstacle if it has ≥3 obstacle neighbours.
3. Guarantee a clear area around the base station.
4. Stamp circular zones (no-fly, threat, wind, mission) using a radius test.

This produces organic-looking clusters rather than random scatter.

---

## 3. Boustrophedon Coverage Planning

**File:** `core/swarm.py → Sector.build_scan_queue()`

Each sector is scanned in a lawnmower (boustrophedon) pattern:
- Iterate rows top-to-bottom.
- Alternate direction each row (left→right, right→left, …).
- Skip impassable cells.

This guarantees 100% coverage with minimum redundant traversal and no
dead-ends.  Combined with path smoothing, drones follow near-optimal
coverage routes.

---

## 4. Swarm Sector Assignment

**File:** `core/swarm.py → Swarm._assign_nearest_sector()`

Greedy nearest-sector heuristic:
```python
nearest = min(unassigned_sectors, key=lambda s: dist(drone.cell, s.centre))
```

This distributes drones evenly across the map without explicit negotiation.
When combined with the rebalancer, drones that finish early are redirected to
uncovered regions, preventing idle time.

**Dynamic rebalancing** (every `REBALANCE_INTERVAL` frames):
- Failed drones release their sector for reassignment.
- Idle charged drones are assigned the nearest remaining sector.

---

## 5. Communication Relay Routing

**File:** `core/communication.py → CommManager.update()`

BFS from the base station through the drone graph finds all reachable nodes:

```
Base ── D0 ── D2 ── D5
         └── D3
              └── D6  ← reachable via relay even if out of direct range
```

Drones outside the connected component increment `frames_since_contact`; after
`SIGNAL_LOSS_FRAMES` frames they transition to `LOST_COMM` state and operate
autonomously until contact is restored.

**Fog synchronisation:** connected drone pairs share explored cells via bitwise
OR of their `map_known` sets, simulating real-time data relay.

---

## 6. Battery Management

**File:** `core/battery.py`

Activity-based drain model:

| Activity  | Drain/frame |
|-----------|-------------|
| Idle      | 0.008       |
| Moving    | 0.030       |
| Scanning  | 0.012       |
| Charging  | +0.350      |

Storm weather adds a flat +0.015/frame.  Wind zones add 15% of movement drain.

The `should_return()` trigger fires when battery ≤ `BATTERY_LOW_THRESH` (25%),
giving drones enough energy to return before exhaustion.  The threshold is
intentionally conservative to account for longer-than-expected return paths.

---

## 7. State Machine

**File:** `core/drone.py`

```
          ┌────────────────────────────────────┐
          │              IDLE                   │
          └──────────────┬─────────────────────┘
         assign sector   │
                         ▼
          ┌────────────────────────────────────┐
    ┌────►│            SCANNING                 │◄────┐
    │     └───┬──────────────────┬─────────────┘     │
    │  batt   │ obstacle         │ scan done          │
    │  ok     ▼                  ▼                    │
    │  ┌──────────┐     ┌─────────────────┐           │
    │  │ AVOIDING │     │   RETURNING     │           │
    │  └──────────┘     └────────┬────────┘           │
    │        │                   │ at base             │
    │   path │                   ▼                    │
    │   clear│          ┌────────────────┐            │
    └────────┘          │   CHARGING     ├────────────┘
                        └────────────────┘
                                                (battery full → IDLE)

    Any state → FAILED  (random hardware failure)
    Any state → LOST_COMM  (radio range exceeded)
```

Transitions are evaluated in priority order each frame:
1. Battery critical → RETURNING (highest priority)
2. Comm lost → LOST_COMM
3. Random failure → FAILED
4. Normal state machine transitions

---

## 8. Particle System

**File:** `main.py → Particle`

Simple Euler-integrated 2D particles with gravity, used as celebratory
feedback when a survivor is discovered.  Each particle has randomised:
- Initial angle and speed
- Lifetime (30–70 frames)
- Color (green, gold, cyan, white)

Alpha-fades linearly with remaining lifetime.
