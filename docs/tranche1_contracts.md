# First-tranche behavioral contracts

## Motion and terrain

Navigation uses point agents on a grid; the displayed drone radius is not a
physical collision radius. A blocked cell is a closed square. Planning rejects
diagonals that touch blocked orthogonal neighbors. Smoothing and continuous
execution use the same supercover segment rule, including blocked corners and
edges. One-cell corridors remain traversable. Drone-to-drone collision handling
and reservation timing are unchanged in this tranche.

Waypoints and scan targets are reached at their exact cell centers. A movement
step is capped by the remaining distance and by the speed in the starting cell
(normal or wind). Nearby waypoints are not skipped. Invalid execution segments
stop the drone and invalidate its path for replanning.

The existing docking zone remains a special endpoint: charging is permitted
only after physically entering its radius; docking may then snap to the base
center. A final approach must have clear terrain or use a planned route. Empty
batteries away from the docking zone still strand rather than charge.

## A* and compatibility

`find_path` retains all legacy arguments and returns a list (empty on failure).
`find_path_result` exposes `status`, `path`, `requested_goal`, `resolved_goal`,
`cost`, and `expanded`. Status is found, invalid_input, unreachable, or
budget_exhausted. Invalid coordinates, blocked starts, out-of-bounds goals,
negative budgets, nonfinite/negative risk or variation, and nonpositive biased
base move costs are rejected. A blocked in-bounds goal uses the existing
deterministic cardinal BFS fallback within Manhattan radius six. This is the
nearest passable candidate, not necessarily reachable; the resolved endpoint
is explicit. No fallback returns unreachable with no resolved goal.

Static traversal costs are 1/cardinal or sqrt(2)/diagonal plus direction bias,
congestion and communication costs. Direction discounts are preserved, with
the octile (or four-neighbor Manhattan) heuristic scaled by the smallest
biased/base movement ratio, capped at one. This is a consistent lower bound
when all other costs are nonnegative and static. Every improved g label enters
the heap; stale entries are skipped. Randomness still scales congestion as
before. Seeded cell noise is a secondary tie key only, followed by insertion
order, and no longer perturbs f. Identical inputs/seeds are deterministic.

The expansion budget counts non-goal nodes, not stale heap entries. Start=goal
succeeds at zero cost with zero expansions even with budget zero. An exhausted
frontier proves unreachable; an unfinished search stopped by the budget does
not. The legacy reservation adapter still depends on accumulated cost rather
than physical arrival time. It is not covered by static optimality guarantees
and is deliberately left for Step 4. Smoothing preserves terrain validity but
does not promise preservation of weighted path costs.

## Assignment lifecycle

`Swarm.assignments` is the authoritative live contract per drone: a frontier ID,
sector ID, or relay role keyed by drone ID. Drone and frontier/sector fields are
compatibility projections maintained by shared claim/release operations. Invalid
or duplicate claims fail before changing ownership. Frontier refresh preserves
live objects and IDs, even when their discovery opportunity disappears.

Forced negotiation means run now, not preempt productive agents. A drone with
live work does not bid; explicit replacement (including promotion to relay),
return, charging, failure, stranding, lost-link recovery, and confirmed stalls
release the old contract. Cancellations are counted by reason. Offline autonomous
exploration retains ownership until completion or recovery. A communication
repair waypoint is a detour and retains the full remaining task queue.

The existing `COMM_MAX_OFFLINE_EXPLORERS` limit is held across live assignments,
including sector fallback, and released with the contract. Admission conservatively
classifies work outside base and connected, stationary relay safe ranges as
potentially offline; moving explorers cannot promise lasting radio coverage.
This intentionally changes the former per-auction risk counter into a task-lifetime
capacity constraint. It does not guarantee connectivity along every route or
under arbitrary relay failures.

Exhausting a frontier packet records completion synchronously and removes the
live contract exactly once, before reassignment. Finishing a sector releases it;
it is marked complete only if all scannable cells are observed. A relay holding
its anchor is still assigned and cannot receive exploration work. The existing
relay hold duration is a minimum, not an expiry: productive connected anchors
persist while needed. Reduced relay demand, disconnection, battery return or
recovery permits a role change. Held anchors are matched to target positions so
an outer anchor cannot silently consume the inner anchor's place.
New relay claims are limited to the safe radio range of base or an already
holding connected relay. Terrain fallback must meet the same requirement.
This validates the anchor destination; it is not a route-wide radio guarantee.

Stall detection accumulates displacement over frames, allowing slow wind motion
and obstacle detours. Stationary/pathless tasks retain reroute and cancellation
recovery. The coverage watchdog does not cancel agents merely because they are
travelling through already-observed terrain or are between waypoints.

These contracts assume the simulator's single-threaded update loop. They do not
add distributed consensus, task persistence across replay loads, or stronger
reservation/collision guarantees.
