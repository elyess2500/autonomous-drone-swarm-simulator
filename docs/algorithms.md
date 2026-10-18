# Algorithms and model contracts

These are the implemented contracts, not guarantees for real aircraft. Source and regression links are collected in [Claims and evidence](claims_and_evidence.md).

## Grid planning and motion

`find_path_result` in [pathfinding.py](../core/pathfinding.py) searches four or eight neighbors. Cardinal cost is 1 and diagonal cost is √2, plus direction bias and nonnegative congestion/communication penalties. Biased base moves must remain strictly positive. A scaled Manhattan/octile lower bound accounts for permitted discounts. Obstacles and no-fly cells are impassable; diagonal moves cannot cut blocked corners.

Every improved label is pushed to the heap; stale queued costs are discarded. Seeded cell variation breaks equal-`f` ties rather than perturbing `f`. Results distinguish found, invalid input, unreachable and iteration-budget exhaustion, retaining requested/resolved goals and cost. A blocked goal can resolve to a nearby passable fallback; callers needing the exact destination, including energy admission, must check it. The compatibility `find_path` API returns a path list.

The budget counts expanded non-goal nodes, not stale heap entries. The planner uses a static spatial reservation penalty, **not A* cost as arrival time** and not a space-time search. Its deterministic cost behavior has Dijkstra-reference tests; this does not make the entire multi-agent stack globally optimal.

Smoothing removes intermediate waypoints only when shared geometry predicates accept the segment. Capped movement avoids overshoot and adjacent-waypoint stalls. Wind changes execution speed/drain; terrain influences passability and wind exposure rather than being a general physical traversal-cost model. Smoothing/variation and greedy coordination do not guarantee minimum total mission distance.

## Frontier, sector and relay work

[Swarm](../core/swarm.py) performs **centralized Contract-Net-inspired task allocation**. Frontier tasks represent unexplored boundaries; bids combine useful work with travel, energy, spread and communication considerations. Sector fallback uses personalized lawnmower-style queues over remaining cells. This ordering supplies work, not a proof of 100% coverage or deadlock-free exploration.

The swarm owns the assignment lifecycle and mirrors it into drone/frontier/sector fields. Claim/release/complete operations maintain one live owner and clear stale ownership. Productive tasks are retained through ordinary negotiation and collision waits. Relay roles are ongoing assignments and exclude exploration work; holding an anchor is not task completion. Explicit cancellation/recovery policy remains available for failures, returns and genuine stalls.

## Point-agent collision/deconfliction

[ReservationTable](../core/intelligence.py) stores absolute simulation-tick forecasts with multiple owners visible at a cell/time. Forecasts follow executable sparse-path geometry, including swept intermediate cells, capped movement and wind. Stationary idle, failed, stranded and charging agents occupy their positions; returning drones occupy their actual trajectories.

Reservations guide planning but are not an exclusive route lease. The execution gate checks proposed simultaneous point trajectories in deterministic priority order. Coincident tick-boundary centers are vertex conflicts; head-on swaps and diagonal crossings conflict when agents reach the same point **at the same time**. Geometric intersection at different times is not contact.

Unsafe motion waits without consuming its waypoint. A bounded sidestep/retreat may retain work; backoff is limited to two attempts per goal/state, then blockage/waiting remains possible. The physical docking zone explicitly permits shared occupancy. No finite-body clearance, corridor completeness or deadlock-free MAPF guarantee follows from this model. Zero contacts in measured probes is evidence for those runs, not a universal collision-free claim.

## Radio and discovery knowledge

[CommManager](../core/communication.py) builds an idealized symmetric range-based graph with a fixed base node. Sorted BFS finds base reachability through eligible drone relays. Any eligible drone can relay; a selected relay role is a coordination policy to improve placement, not a different radio protocol.

FAILED and STRANDED drones do not relay; charging/docked drones have radio power. RETURNING and LOST_COMM states do not themselves disable a radio. Signal quality is a distance-derived heuristic; zero means zero, never a truthiness default to healthy connectivity. There is no terrain RF attenuation, packet loss, bandwidth, interference or modeled transport delay.

Physical disconnection gates map and survivor publication from the **first disconnected tick**. LOST_COMM is a delayed behavioral transition after a grace interval, not permission to publish during that interval. Sensors retain local/pending discoveries; normal rendering uses the published fog/survivor set. On a restored base path, the post-motion synchronization phase merges buffered cells and survivor IDs immediately and idempotently. This is an abstract upload, not network queue simulation or decentralized SLAM. Disconnected peers do not obtain a separate modeled delivery mechanism merely by being near one another.

## Route-aware abstract energy

[Battery](../core/battery.py) charges/drains abstract units per tick; [EnergyPolicy](../core/energy.py) reuses that rate function for forecasts. The decision checks:

```text
outbound route charge + return route charge + expected work charge
+ uncertainty allowance + configured reserve <= current usable charge
```

The outbound estimate prioritizes the existing executable route to the **next intended work waypoint**, including an active sidestep before replanning. It does not forecast an entire sector. Otherwise a terrain route is searched; unreachable or fallback-only destinations are infeasible. Return estimates price the base approach lane and center conservatively, except when already within the physical docking disk.

Each segment uses at least one tick, otherwise ceiling(distance/speed), and the drain rate for its expected activity. A mixed-wind segment uses the slower speed/higher rate over its whole length. Work normally budgets one scan interval; relay holding can use explicit idle-duration overhead. `BATTERY_PATH_INEFFICIENCY` supplies the uncertainty multiplier; `BATTERY_TASK_RESERVE` is an explicit abstract-charge reserve. Storm drain uses current weather. Future weather, traffic waits and communication detours are unknown.

Admission applies to frontier, sector and relay work, including fallback paths. Sector checks use the intended first work cell, not a potentially blocked centroid. Controlled reassessment reacts to route/weather/state changes and elapsed intervals; an energy-triggered return releases work through the existing ownership lifecycle. Collision waiting still consumes activity/time energy; backoff remains part of forecast geometry. Reconnection cannot manufacture charge or bypass reserve policy.

Charging progresses from dock/charge to departure-ready waiting at base. Readiness is separate from physical relaunch, so an idle ready drone does not repeatedly manufacture new charging cycles. Actual departure remains an observable movement event. Emergency recovery and impossible/external disruptions can still strand drones. A windy-detour fixture showed the policy rejecting a task that previously stranded at tick 2,531 and remaining safe at base through 6,000 ticks; it does not establish that stranding is eliminated.

## Pure computation reuse

The Step 11 optimization caches **route-energy geometry**, not policy decisions. Each drone has a bounded 1,024-entry FIFO pure-cost cache; exact route/start/activity/weather keys are checked inside a terrain/dimensions/speed/drain/helper context. Custom map geometry bypasses it. Queries may read but do not populate caches. Battery, reserve, uncertainty, work and decision/accounting effects remain evaluated outside the cached calculation. A separate bounded route cache retains terrain routes. [Performance and validity evidence](performance.md)
