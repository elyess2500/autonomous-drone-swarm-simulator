# Phase 1 final engineering report — Steps 1–3

Closed from the existing working state on 2026-09-19. Validation artifacts were
completed on 2026-09-18. No production code was changed during this final closure.
The audit and completed tests/benchmarks were not restarted.

## 1. Executive summary

**The approved correctness tranche is complete.** The final full suite passed
**51 tests**. The final three-seed benchmark and the seed-2026 repeat also
completed; every recorded non-timing field and the final-state hash matched in
the repeated run. The original five tests and their thresholds remain unchanged.

Motion now reaches targets consistently, static A* matches an independent
Dijkstra oracle, and task ownership survives refresh, completion, cancellation,
relay changes and reassignment. Across the three 3,600-tick benchmarks, unfinished
frontier replacements, relay/exploration conflicts and ownership inconsistencies
were all zero. Coverage and survivor discoveries increased over the original
baseline for all three seeds.

There are two material qualifications. Average connectivity remains below the
original baseline, although final communication acceptance checks pass and the
long-run majority-connected fraction improved. Mean update latency is **higher
than the original baseline on all three seeds**; fewer path searches did not
translate into lower total update time. This is a correctness improvement, not
a claim of universal performance improvement or research-grade autonomy.

**Step 4 and later work remain unimplemented.**

## 2. Step 1 — Motion

**Confirmed bugs/root causes.** The executor considered a waypoint reached inside
a one-cell distance threshold, but the scan queue still expected arrival. An
adjacent target could therefore be skipped and replanned indefinitely. Planning,
smoothing and execution also disagreed about touching blocked corners, and
continuous movement/final approaches lacked a common terrain-validity check.

**Fixes.** Movement is capped by both speed and remaining distance, reaches the
exact endpoint, and consumes ordinary waypoints/scan targets at cell centers.
Planning rejects diagonals with blocked orthogonal neighbors. Smoothing and
execution share a supercover segment predicate that includes blocked edges and
corners. Final docking approach requires clear terrain or a planned route.
Existing docking-radius, snap, charging and away-from-base stranding safeguards
remain intact.

**Tests/behavior.** The first six focused cases produced five failures and one
pass before correction; docking was already working. The final file contains
**8 cases**: adjacent target, ordinary and wind-speed arrival, blocked corners,
a narrow L-shaped corridor, physical docking, bidirectional grid-edge validity,
and an obstructed final approach. Ordinary arrival intentionally changed to exact
centers. Agents remain geometric points; rendered radius is not a collision body.

## 3. Step 2 — A*

**Confirmed bugs/root causes.** Updating g without pushing an improved heap entry
left stale priorities in the queue and could return a suboptimal goal. Direction
discounts and additive random f perturbations also invalidated the unscaled
heuristic's lower-bound assumptions. The old empty-list interface did not explain
why a search failed or identify a substituted fallback goal.

**Fixes and oracle evidence.** Every improved label is pushed; stale labels are
ignored when popped. The heuristic is octile for eight neighbors or Manhattan
for four, scaled by the minimum positive biased/base move-cost ratio, capped at
one. Seeded variation is a secondary tie key, followed by insertion order; it no
longer changes f. The audit counterexample is retained. Because Step 1 changed
its corner topology, a second counterexample isolates stale priorities under the
new rule: **16.4068542495 before, 15.8210678119 after and in Dijkstra**.
The tests compare A* against an independent Dijkstra implementation on **160
small generated maps**, covering four/eight neighbors, congestion, discounted
direction costs and seeded variation. All comparisons pass.

**Result contract.** The legacy `find_path` signature still returns a list and
its callers were preserved. `find_path_result` additionally returns status, path,
requested/resolved goals, cost and expansions:

- `found`: successful search, including start=goal at zero cost/expansions.
- `invalid_input`: rejected coordinates/budget or invalid numeric cost settings.
- `unreachable`: exhausted search, or no passable blocked-goal fallback.
- `budget_exhausted`: search stopped before proving reachability/unreachability.

Traversal assumes cardinal cost 1 or diagonal sqrt(2), direction bias leaving
strictly positive base moves, and nonnegative congestion/communication penalties.
The expansion budget counts non-goal expansions, excluding stale heap entries.
A blocked in-bounds goal uses the existing deterministic cardinal BFS fallback
within Manhattan radius six; the resolved candidate is explicit and is not
promised reachable. Smoothing preserves terrain validity, not weighted cost
optimality. Static optimality does not extend to the legacy cost-indexed
reservation adapter.

The initial Step 2 run had **8 failures / 4 passes**, plus the separately failing
strict-corner counterexample. The final planner file has **13 cases**, including
invalid inputs, unreachable/budget/fallback outcomes, compatibility and repeated
seeded results. Full details are in `tranche1_contracts.md`.

## 4. Step 3 — Task lifecycle

**Confirmed bugs/root causes.** Forced auctions repeatedly replaced productive
work. Frontier refresh regenerated live identities. Ownership was independently
cleared on drones and tasks, leaving stale claims. Completion acknowledgement
could be overwritten by reassignment. Idle/holding relays could receive sector
work. Wind movement below the per-frame progress threshold and legitimate
obstacle detours could trigger false stall recovery.

**Ownership fixes/invariants.** `Swarm.assignments` is authoritative for one live
contract per drone and one owner per task. Shared claim/release operations keep
drone and frontier/sector projections consistent. Invalid/duplicate claims fail
before mutating the previous assignment. Live frontier identities survive map
refresh. Completion removes/counts a contract once before another award; a sector
is marked complete only when all scannable cells are observed. Return, charging,
failure, stranding, explicit replacement, lost-link recovery and confirmed stalls
release ownership. Offline autonomous exploration retains ownership until
completion or recovery. Mesh-repair detours retain the complete remaining queue.

Forced negotiation means run now, not preempt productive agents. Active contracts
and relay roles are excluded from exploration allocation. Stall detection now
accumulates displacement across frames, retaining stationary/pathless reroute and
reassignment while tolerating slow wind movement and obstacle detours.

**Relay/capacity corrections.** The existing relay hold duration is a minimum,
not a mandatory expiry. Needed connected anchors persist; reduced demand,
disconnection, battery or recovery permits a change. Held anchors are matched to
target positions so an outer anchor does not displace an inner one. New anchor
destinations, including terrain/fallback choices, must connect to base or an
already holding connected relay. This is destination validation, not a guarantee
of radio coverage throughout travel.

`COMM_MAX_OFFLINE_EXPLORERS` now belongs to live exploration contracts across
auctions and sector fallback. Admission conservatively classifies work outside
base/connected holding-relay safe ranges as potentially offline; moving explorers
cannot promise lasting coverage. Capacity is released with ownership. This is an
intentional policy correction exposed by persistent task execution, not a new
path planner or a change to radio thresholds.

Step 3 began with **11 failing lifecycle cases**, plus the separately failing
wind-progress regression. Further focused failures identified watchdog cancellation
between waypoints, invalid-claim non-atomicity, relay-slot displacement, unnecessary
retargeting, cross-auction over-allocation and disconnected relay claims. The final
file contains **25 cases**. An integration case checks registry/projection and
capacity invariants through 400 updates, refreshes, failure and reassignment.

## 5. Files changed


| File(s) | Purpose |
| --- | --- |
| `core/drone.py` | Exact movement, terrain checks, lifecycle callbacks, offline completion/cancellation, accumulated stall progress. |
| `core/pathfinding.py` | Correct queue/heuristic, explicit result API, corner policy and shared smoothing visibility. |
| `core/geometry.py` (new) | Shared continuous point-agent terrain predicate. |
| `core/swarm.py` | Assignment/capacity ownership, completion/cancellation, persistent valid relays, non-preemptive allocation. |
| `core/intelligence.py` | Preserve live frontier identities. ReservationTable is unchanged. |
| `tests/motion_tests.py` (new) | 8 motion/geometry/docking cases. |
| `tests/pathfinding_tests.py` (new) | 13 planner cases, including the 160-map oracle comparison. |
| `tests/task_lifecycle_tests.py` (new) | 25 lifecycle/capacity/relay cases. |
| `benchmarks/tranche1.py` (new) | Headless behavioral counters, update latency and final-state hashing. |
| `benchmarks/README.md` (new) | Reproduction commands, metric definitions and interpretation limits. |
| `benchmarks/results/tranche1/*.json` (new) | Original/intermediate/final measurements, repeated run, historical audit observations and reproducibility/source-hash check. |
| `benchmarks/results/tranche1/*.txt` (new) | Saved Step 1/2/final full-suite results and original Step 2/3 failing regressions. |
| `docs/tranche1_contracts.md` (new) | Explicit motion, planner and assignment contracts. |
| `docs/phase1_engineering_report.md` (new) | This final report. |



## 6. Test results

| Stage | Focused evidence | Full suite |
| --- | --- | --- |
| Original audit | Existing safeguards established | 5 passed, 36.39 s |
| Step 1 | Initial 5 failures/1 pass; corrected motion/docking checks passed | 11 passed, 375.44 s |
| Step 2 | 25 passed: planner, motion and docking | 26 passed, 488.57 s |
| Final Step 3 | Latest standalone focused run: 49 passed, 1.56 s; one additional fallback parameter case included in final full suite | **51 passed, 141.39 s** |

The final suite contains 46 new cases plus the original five tests. Two extra
motion cases were added after Step 1 full-suite collection; later complete suites
include them. The final full run includes all current focused cases and the
10,800-tick smoke test. Source/test file timestamps precede that final run. Its
saved output is `benchmarks/results/tranche1/full_suite.txt`; it did not need to
be rerun after the interruption. The only warning concerns pygame's upstream
`pkg_resources` deprecation.

Intermediate Step 3 smoke failures were investigated and corrected without
changing acceptance thresholds. The final smoke found 4/5 survivors, completed
recharge/relaunch, had no final stranded or empty-battery returning drones and no
full radio collapse. Two drones ended temporarily in LOST_COMM, within the
configured maximum of three. Maximum normal-run lost streak was 540 ticks.
Forced recovery succeeded with a maximum 655-frame lost streak. Offline tests
buffered 29 cells without early global visibility, synchronized them on reconnect,
and synchronized a survivor; no field charging occurred. The explicit recharge
scenario manually places a drone at base, so it is not proof of a complete natural
sortie/recharge cycle by every drone.

## 7. Before/after behavioral metrics

**Comparable tranche harness:** eight drones, 3,600 ticks, no rendering, failures
disabled, demo mode off, offline autonomy on; weather, battery, radio, analytics
and replay sampling remain active. Timing wraps Mission.update; post-update
invariant checks are outside it. Step 1/2 intermediate measurements exist only
for seed 2026. Baseline production code was `b400109`.

Seed 2026 across all stages:


| Metric | Original | Step 1 | Step 2 | Final Step 3 |
| --- | --- | --- | --- | --- |
| Coverage (%) | 8.76 | 23.96 | 32.45 | 28.09 |
| Survivors found | 0 | 1 | 3 | 2 |
| Average connectivity (%) | 100.00 | 97.92 | 93.55 | 85.93 |
| Minimum connectivity (%) | 100.0 | 75.0 | 50.0 | 25.0 |
| Frontier awards | 14,050 | 16,808 | 14,520 | 25 |
| Unfinished-task replacements | 14,010 | 16,751 | 14,468 | 0 |
| Frontier completions | 0 | 0 | 0 | 13 |
| Path searches | 21,516 | 21,776 | 19,663 | 2,204 |
| Relay/exploration conflicts | 56 | 3,019 | 2,732 | 0 |
| Ownership inconsistencies, summed over ticks | 15,698 | 49,991 | 51,621 | 0 |
| Final ownership inconsistencies | 8 | 24 | 22 | 0 |
| Field-charging violation drone-ticks | 0 | 0 | 0 | 0 |



Other saved seeds, at the same 3,600-tick horizon:


| Metric | 2027 original | 2027 final | 2031 original | 2031 final |
| --- | --- | --- | --- | --- |
| Coverage (%) | 9.37 | 26.06 | 6.20 | 22.59 |
| Survivors found | 1 | 2 | 1 | 3 |
| Average connectivity (%) | 100.00 | 82.64 | 100.00 | 80.41 |
| Minimum connectivity (%) | 100.0 | 50.0 | 100.0 | 37.5 |
| Frontier awards | 15,625 | 22 | 19,098 | 23 |
| Unfinished-task replacements | 15,575 | 0 | 19,053 | 0 |
| Frontier completions | 0 | 13 | 0 | 13 |
| Path searches | 25,864 | 2,806 | 25,217 | 1,150 |
| Relay/exploration conflicts | 1,206 | 0 | 285 | 0 |
| Ownership inconsistencies, summed over ticks | 25,081 | 0 | 14,612 | 0 |
| Final ownership inconsistencies | 4 | 0 | 4 | 0 |
| Field-charging violation drone-ticks | 0 | 0 | 0 | 0 |



Full-collapse ticks are **zero for every run in these tables**, derived from each
recorded minimum connectivity being positive. Final stranded count is zero in
each saved state histogram; all-tick stranding counts were not recorded by this
harness. Majority-connected fractions were not recorded at this short horizon.

Ownership inconsistency/orphan counts above are the **same metric**, not two
independent improvements. The cumulative count sums inconsistent projections over
ticks, not distinct tasks; the final count is a snapshot. Tests separately check
both projection directions against the registry. Zero unfinished replacements
means acceptance did not overwrite a still-live frontier with pending work;
explicit cancellations before a later award are separate and still occur.

Final cancellation counts by reason:


| Reason | 2026 | 2027 | 2031 |
| --- | --- | --- | --- |
| offline timeout/battery | 1 | 2 | 1 |
| relay lease ended | 7 | 4 | 4 |
| replace with relay | 8 | 5 | 6 |
| returning | 1 | 0 | 0 |



These include necessary promotion to relay, release of relay roles, battery return
and offline recovery. Frontier completion means exhausting its local scan packet,
not completing the whole mission.

**Separate longer smoke comparison:** seed 2026, 10,800 ticks, normal mode,
failures disabled. Values below come from smoke output/audit, not the short-horizon
benchmark. The original long-run figures are saved in the prior audit.

| Metric | Original | Step 1 | Step 2 | Final Step 3 |
| --- | --- | --- | --- | --- |
| Coverage (%) | 40.38 | 48.68 | 43.88 | 47.14 |
| Survivors found | 4/5 | 4/5 | 4/5 | 4/5 |
| Average connectivity (%) | 88.3 | 86.8 | 93.0 | 79.7 |
| Majority-connected fraction (%) | 89.2 | 100.0 | 99.1 | 99.8 |
| Full-collapse ticks | 0 | 0 | 0 | 0 |
| Final stranded drones | 0 | 0 | 0 | 0 |
| Final empty-battery returning drones | 0 | 0 | 0 | 0 |
| Forced recovery maximum lost streak (ticks) | 790 | 799 | 788 | 655 |

Long-run lifecycle counters and per-update latency distributions were not saved
by the smoke test; short-run counters must not be presented as 10,800-tick values.

## 8. Before/after performance metrics

All entries below are milliseconds from the comparable 3,600-tick tranche
harness. Full-suite wall times above are not isolated performance benchmarks.


| Seed / stage | Mean ms | p95 ms | p99 ms | Maximum ms |
| --- | --- | --- | --- | --- |
| 2026 original | 3.418 | 7.867 | 10.503 | Not recorded |
| 2026 Step 1 | 18.346 | 65.831 | 100.894 | Not recorded |
| 2026 Step 2 | 20.103 | 70.632 | 98.586 | Not recorded |
| 2026 final Step 3 | 8.984 | 17.296 | 19.061 | Not recorded |
| 2027 original | 6.270 | 23.017 | 33.017 | Not recorded |
| 2027 final Step 3 | 9.098 | 17.757 | 19.172 | Not recorded |
| 2031 original | 5.390 | 17.059 | 34.386 | Not recorded |
| 2031 final Step 3 | 9.546 | 16.834 | 18.828 | Not recorded |



Mean latency rose **2.63x, 1.45x and 1.77x** versus the original for seeds 2026,
2027 and 2031 respectively. Path-search counts fell **89.8%, 89.2% and 95.4%**.
The seed-2026 p95/p99 worsened relative to the original; seed-2027/2031 tails
improved. Seed-2026 final mean/p95/p99 improved relative to the much slower Step 2
intermediate result. Thus lower allocation/search churn is real, but an overall
speedup over original ADSS is **not supported**.

Correctness checks and different productive trajectories change the workload.
Repeated bidding/admission checks and offline feasibility checks are plausible
cost contributors by inspection; these final runs do not isolate their causal
shares. No new profiling/optimization tranche was started to explain away the
measured slowdown. These are local single-run distributions, with no confidence
intervals, process isolation or universal throughput guarantee.

Maximum latency was not retained by the tranche harness. A **separate original
audit run**, using different instrumentation at the same short horizon, recorded
maxima of 18.481 ms (2026; repeat 18.882), 44.838 ms (2027) and 161.275 ms (2031).
These are preserved in `original_audit_baseline.json`; there is no equivalent final
maximum, so no before/after maximum-latency comparison can be made.

## 9. Reproducibility results

The final seed-2026 run and repeat agree on **all 18 recorded non-timing fields**,
including awards, cancellations, completions, search count, ownership, coverage,
survivors, connectivity and state histogram. Both final-state hashes are:

```text
932fe36206f28b06c2e2525adbfe9bbdd1fed90d46ad009c44ce72eba56459e7
```

The hash covers fog, discovered survivors, weather and each drone's position,
state, battery, path and queue. It does not serialize every internal field or
prove identical trajectories on every platform. The independent post-run check
is saved in `reproducibility_check.json`, including hashes of the current source,
tests and harness. No non-timing differences were found.

Timing varied as expected: first run mean/p95/p99 **8.984/17.296/19.061 ms**;
repeat **9.006/17.461/20.601 ms**. Headless reproducibility is supported for this
case. Rendering consumes shared randomness in the existing application, so this
is not a claim of render-independent deterministic experiments.

## 10. Connectivity analysis

The reported **69.1%** was an intermediate Step 3 smoke result. Final code reached
**79.7%** over 10,800 ticks: still **8.6 percentage points below** the original
88.3%, but above the unchanged 65% acceptance floor. Majority connectivity rose
from **89.2% to 99.8%**, above the unchanged 70% requirement; full collapse remained
zero. Minimum connectivity was 2/8 for the final long run. A small temporary
minority of disconnected drones can lower the mean without usually losing a
connected majority.

At 3,600 ticks, final connectivity was **85.93%, 82.64%, 80.41%** for seeds 2026,
2027, 2031, versus 100% in their original short baselines. The final range is 5.52
percentage points; degradation occurs across all three seeds, not just one.
The short baselines also covered only 6.20–9.37% with extreme task churn, whereas
final coverage was 22.59–28.09% with completed contracts.

**Assessment:** this is a measured connectivity-quality reduction, accompanied by
better task execution and coverage, not a failure of the tested communication
invariants in final code. Longer exploration contracts plausibly explain part of
it, and the evidence is consistent with that tradeoff. However, motion, planner,
relay persistence and admission policy changed together; no controlled ablation
isolates the cause. It would be unjustified to assert that all of the decrease is
inevitable, desirable or fully explained. No further algorithm change was made
merely to recover the old number. Route-wide connectivity and untested seeds
remain open reliability questions.

## 11. Intentional behavior changes

- Ordinary waypoints/targets are reached at exact centers; blocked corners/edges
  are invalid. Docking retains its distinct physical-zone semantics.
- A* secondary seeded ties and its scaled heuristic can change routes. The legacy
  list API remains; callers can opt into explicit failure/fallback information.
- Productive tasks persist through forced auctions and frontier refresh. Completion
  is synchronous and exactly once for the live contract.
- Sector/frontier/relay transitions release old ownership; safety cancellation is
  explicit and counted. Offline task recovery cancels; mesh detours preserve work.
- Productive connected relays persist beyond their minimum hold; new anchors must
  join the held connected chain. Offline capacity spans live tasks and sector fallback.
- Slow wind movement/detours no longer imply stalls; genuinely stationary work
  still reroutes or becomes available for reassignment.

## 12. Remaining known risks/issues

**Confirmed and still present:**

- Soft reservation ownership can be overwritten, and smoothed intermediate cells
  and physical arrival times are not represented faithfully. ReservationTable was
  verified unchanged against HEAD. No collision-free guarantee is justified.
- Existing radio grace-period handling can publish discoveries before LOST_COMM,
  and two risk helpers still coerce a zero connected ratio to 1.0 via `or 1.0`.
  These prior-audit defects were not part of this closure and were not repaired.
- Existing replay is not faithful full-state restoration; rendering shares RNG
  consumption with simulation; some timing/analytics fields are wall-clock or
  incomplete. These audited areas remain unchanged.
- The measured mean-update slowdown and reduced average connectivity relative to
  the original are real remaining costs. No blanket optimization claim is made.

**Design limits and unverified risks:**

- Static-grid A* optimality does not imply optimality with time-dependent
  reservation costs or after weighted-path smoothing.
- Point agents, simplified sensing/radio and battery estimates limit physical
  realism. Anchor-destination validity does not prove connectivity along a route.
- Capacity/ownership invariants do not prove stability under arbitrary relay
  failures, every seed, large swarms or long-duration missions.
- The three short seeds and one long seed disable stochastic failures. Failure
  transitions have test coverage, not a measured failure-rate reliability study.
- Repeated bidding, pathless replanning and offline feasibility checks may dominate
  some workloads; their final per-component cost is unmeasured.
- Assignment ownership assumes the existing serial update loop and is not a
  distributed-consensus or replay-persistence protocol.

## 13. Git diff summary

Tracked changes relative to the original checkout:

| File | Added lines | Removed lines |
| --- | --- | --- |
| core/drone.py | 69 | 49 |
| core/intelligence.py | 12 | 10 |
| core/pathfinding.py | 113 | 55 |
| core/swarm.py | 171 | 76 |
| **Tracked total** | **365** | **190** |

New implementation/test/harness files add 57 lines of geometry, 583 test lines
(137 motion + 139 planner + 307 lifecycle), and 106 harness lines. Documentation,
README and evidence artifacts are additional new files. Including every currently
untracked text file, the working-tree total is **2,671 added / 190 removed
lines across 24 files** (including this report and raw evidence; generated
evidence should not be mistaken for production-code size).

The substantive runtime change is five files: the four tracked files above and
new geometry. There are no commits, merges or deployments from this tranche.
`git diff --check` passes. Original tests and configuration are unchanged.
Changes stayed within motion/planner/task correctness and the relay/capacity
corrections needed to pass the related validation. No reservation/collision,
communication-boundary, replay, RNG/clock, renderer/UI or broad architecture
implementation was started. This closure added only reporting/evidence.

## 14. Phase 1 assessment

ADSS now demonstrates meaningful engineering improvements: explicit movement and
search contracts, independent shortest-path verification, stable task identities,
central ownership, justified cancellation, valid relay assignment and reproducible
headless validation. Zero observed lifecycle inconsistencies and completed
frontier contracts replace the original churn, while three seeds show higher
coverage and more survivor discoveries.

It remains unsuitable for claims of research-grade collision avoidance,
distributed communication correctness, physical realism, replay fidelity,
render-independent determinism, scalable real-time performance or statistically
established mission reliability. The result is a stronger portfolio simulator
with evidence and explicit limitations, not a validated robotics research stack.

## 15. Recommendation for the next tranche — not implemented

Review and accept the measured coverage/connectivity/latency tradeoffs first.
After explicit approval, retain Step 4 as a separate reservation-correctness
tranche: ownership, swept/smoothed occupancy and physical arrival-time semantics,
starting from small crossing/corridor counterexamples. Carry forward every current
docking, communication and lifecycle regression. Later communication-boundary,
replay, RNG/clock and performance work should remain separately scoped; profiling
is needed before selecting optimizations, and larger controlled experiments are
needed before stronger autonomy claims.

Reproduce the current checks with `python -m pytest -q -s` and the commands in
`benchmarks/README.md`. Raw results and verification are in
`benchmarks/results/tranche1/`; contracts are in `docs/tranche1_contracts.md`.

**Phase 1 is closed. Stopped after Steps 1–3; waiting for approval before Step 4.**
