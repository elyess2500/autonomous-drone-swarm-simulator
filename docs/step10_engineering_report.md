# Step 10 — Route-aware energy feasibility and coherent autonomy

Evidence: `benchmarks/results/step10/`. Scope is Step 10 only.

## 1. Executive summary

Energy admission now prices a terrain-valid route to the next work waypoint,
work overhead, and a return route in existing abstract charge units. It reuses
executable paths and rejects unavailable routes. Charging readiness persists
while waiting at base, removing the reproduced meaningless state loop without
suppressing real events. The modeled reserve policy prevented the reproduced
avoidable stranding case; it does not guarantee energy safety.

The cost is substantial in these trials: mean update latency increased from
11.67/15.62/13.13 ms to 37.06/95.27/27.28 ms for seeds 2026/2027/2031. These are
observations, not isolated causal estimates. All three exceed a 16.67 ms real-time
60 Hz update budget under this instrumented workload, although simulation ticks
remain fixed. The change is not presented as a performance improvement.

## 2. Original energy/autonomy audit

Battery consumption was state/tick based, but admission used straight-line cell
distance, normal speed and moving drain with a 1.45 multiplier. Obstacles,
no-fly detours and longer existing paths were ignored. Old work allowance was
four scan intervals. Frontier bids and sector filters used the heuristic;
direct frontier admission did not independently check it. Queue personalization
could change the first sector work cell afterward. Relay selection relied mainly
on battery fraction/low-charge guards. Offline autonomy checked return-route
existence but discarded its energy cost. Return, replanning, collision waits,
communication recovery, charging and emergency paths were traced. The preserved
pre-implementation audit is `audit_and_contract.md` in the evidence directory.

## 3. Reproduced weaknesses

Saved failing cases demonstrate obstacle/no-fly underestimation, unreachable
work accepted as affordable, ignored longer executable routes, unguarded direct
frontier/relay admission, and charging churn: 11 starts instead of one in the
no-work fixture. Validation also exposed two Step 10 interactions: filtering by
a blocked sector centroid instead of reachable intended work, and omitting an
active sidestep from the forecast. Both received focused red/green regressions.
Final-suite validation exposed the energy replay extension assuming optional
accounting existed; the preserved legacy test reproduced it before correction.

## 4. Existing battery/energy units

Charge units are abstract, not joules. Default per-tick drain is SCANNING 0.012,
RETURNING 0.030, IDLE/LOST_COMM 0.008; storm adds 0.015 and wind 0.0045. Failed
drones do not drain. One tick remains 1/60 second. Existing charging/capacity
clamps and emergency boosts remain. `Battery.drain_per_tick` supplies both actual
consumption and prediction, without changing these rates.

## 5. Final energy-estimation contract

`EnergyPolicy.estimate` exposes outbound, return, work, uncertainty and reserve.
At defaults: total = `(outbound + return + work) * 1.45 + 18`. Missing/invalid
routes cost infinity; diagnostic serialization uses null instead of JSON infinity.
Pure estimates neither fill caches nor mutate decision counters/RNG. Policy
assessments explicitly record diagnostics.

## 6. Route-aware estimation semantics

The horizon is the next work waypoint plus return, not an entire sector/packet.
Use the actual remaining path when available; otherwise use existing A*/smoothing.
A fallback goal different from the intended goal is rejected. An active sidestep
is forecast first, then a route toward the retained task, matching replanning.
Segments cost `ceil(distance/speed)` ticks; a zero-length waypoint costs one tick.
Return includes the base lane and center, conservatively beyond actual docking.
A* accumulated cost is never treated as elapsed time or charge.

Each drone caches at most 512 terrain routes, keyed by endpoints and planner/agent
settings; terrain-byte changes invalidate them. Energy values are recomputed.
Dynamic traffic/radio detours are not cached predictions. Actual outbound geometry
is checked before task ownership changes. Cache reuse and invalidation are tested.

## 7. Return-reserve policy

Existing ExperimentConfig settings supply `BATTERY_TASK_RESERVE` (18 units),
`BATTERY_PATH_INEFFICIENCY` (1.45, now an explicit uncertainty allowance), and
the independent low-charge guard (35 units). Exact modeled budget is accepted
only if state/low-charge guards also permit it. A deficit is rejected.
“Safe return” means modeled terrain-route affordability at the decision point,
not guaranteed return under future changes. No new hidden hysteresis is added.

## 8. Task/bid energy-feasibility policy

Frontier bids/direct admission, sectors and relays use route-aware checks.
Sector queues are personalized before validating the first work cell; centroids
remain only in existing selection policy. The real outbound route is prepared
and checked before the authoritative claim. Rejection leaves ownership unchanged.
Relay estimates include the configured hold interval. Existing allocation,
communication-risk and priority policies otherwise remain intact.

## 9. Dynamic reassessment policy

Normal work reassesses on cell, weather, remaining path, next target, active
sidestep or terrain changes, or after `REROUTE_INTERVAL` (120 ticks). Low charge
and depletion guards remain immediate. Newly planned work is checked before
movement. Offline/relay recovery retains its decision paths with route-aware
energy. Returns cancel through authoritative release, never false completion.

## 10. Charging lifecycle before Step 10

When no eligible work existed, allocation called `_dock()`. Already-charged
drones entered CHARGING, immediately reached the threshold, and returned to
IDLE; the next allocation repeated this. Counters accurately described those
state episodes, but they were not distinct charge needs or real departures.

## 11. Charging lifecycle after Step 10

Docking begins CHARGING; charging reaches the existing 85-unit departure threshold.
The drone becomes IDLE with persistent readiness and may wait/top up at base.
Assignment/retained work starts flight behavior and stops charging. First nonzero
movement clears readiness and records actual relaunch. Readiness alone is not
departure. Failure/stranding clear readiness. Physical docking safeguards remain.

## 12. Stranding/emergency semantics

The windy-detour fixture starts with 60 units. Step 9 accepts it and strands at
tick 2,531. Step 10 rejects it and is unstranded, at base, at tick 6,000. This
demonstrates prevention of that modeled case only. Externally depleted field
drones still strand once. Emergency recharge remains dock-only, counts actual
charge, and can establish readiness without relaunch. Hardware failure/manual
rescue remain separate mechanisms.

## 13. Wind/weather treatment

Current storm drain is included. Wind anywhere along a segment makes its full
length use the slower speed/higher drain: conservative for mixed segments.
Homogeneous estimates agree with tick-by-tick battery consumption; a mixed-wind
fixture bounds unimpeded execution. Future weather is not predicted. Allocation
receives current weather before checking energy.

## 14. Collision/wait energy treatment

Waiting drains the current state's existing rate without consuming the waypoint
or replacing the task. Active backoff geometry enters the forecast. Unknown
future waiting is not precisely modeled; allowance and reassessment provide a
buffer. Step 4 geometry, priority and bounded recovery remain unchanged.

## 15. Communication/recovery interaction

Offline continuation requires reserve; inadequate energy triggers existing
base-recovery paths. Physical connectivity, publication gating, local buffers,
radio eligibility and synchronization remain intact. Energy-return events
distinguish modeled/low-charge recovery from a timeout-only recovery.

The forecast prices work as SCANNING and return as RETURNING. Existing LOST_COMM
execution drains at the lower idle rate, so this assumption is conservative for
that recovery state rather than an exact prediction of its entire state sequence.

## 16. Accounting/events added or changed

`energy_return` records a reserve/low-charge base-return decision.
`energy_rejected` records final assignment-preparation rejection, not every
failed bid. Existing task-cancellation records remain authoritative. A benchmark
observer separately counts cancellations during energy-emitting return/recovery
calls; it is not a second live counter. Charging event meanings are preserved,
but their underlying lifecycle intentionally changes: ready docked top-up adds
charge without another completion episode. Ledger retention remains 4,096 records,
with lifetime counts and chained hash surviving eviction.

## 17. Metrics added or changed

`energy_checks`, `energy_infeasible_checks`, `energy_route_searches` sum per-drone
diagnostics; `energy_returns` comes from accounting. Infeasible checks can repeat
for bids or return assessments; they are not unique rejected tasks. State/low
guards can short-circuit before a modeled check. Latest decisions retain target,
weather, battery, estimate, margin and reason. Queries are pure; CSV includes
the added metrics. Frozen final summaries remain intact. Survivor rescue remains
unsupported; success is still 98% coverage OR all nonempty survivor zones globally
discovered. No terminal-failure policy is invented.

## 18. Replay/persistence impact

Optional per-drone `energy` extension version 1 records diagnostics/readiness.
Validation checks count types and metric agreement, including energy-return
agreement when accounting is present. Legacy data without energy remains valid,
as do frames without optional accounting. Detached sampled playback, existing
schema version and explicit non-support for checkpoint/continuation are retained.

## 19. Headless/API impact

`core.simulation.make_simulation` remains the supported factory. Energy is core
logic requiring no UI/display initialization. Existing estimate methods remain
available, with energy snapshots/mission metrics for diagnostics. Fixed time,
RNG ownership and config snapshots are unchanged. Render helpers still import
Pygame; zero Pygame imports is not claimed.

## 20. Production files changed

| File | Purpose |
|---|---|
| `core/energy.py` | New estimator, bounded route reuse and diagnostics |
| `core/battery.py` | Shared unchanged drain-rate calculation |
| `core/drone.py` | Admission, reassessment, energy returns and readiness |
| `core/swarm.py` | Work-cell/relay feasibility and actual-route admission |
| `core/analytics.py` | Pure energy metric projection |
| `core/replay.py` | Optional energy capture/validation |
| `config.py` | Comments only; no value changes |

## 21. Tests added

`tests/energy_tests.py` adds 28 parameterized cases: obstacle/no-fly detours,
unreachable work/return, longer paths, direct frontier/relay gating, four exact
wind/storm estimates, reserve boundary, pure queries/cache invalidation, longer
replans, wait drain/ownership, low-charge/offline recovery, ready waiting/real
departure, impossible stranding, emergency charging, blocked centroid, personalized
work, active sidestep, real-plan rejection, mixed wind and replay compatibility.
Prior tests and acceptance thresholds are unchanged.

## 22. Hand-calculated energy fixtures

With speeds 2 pixels/tick clear and 1 windy, a two-cell segment preceded by its
zero-length initial waypoint costs `1 + ceil(2 * CELL_SIZE / speed)` ticks.
Clear/wind/storm/combined cases multiply this by the shared SCANNING rate and
compare actual Battery consumption. A 40-unit reserve fixture rejects total
minus 0.0001 and accepts exact total. Outbound-only affordability is insufficient.

## 23. Focused test results

Final compatibility correction: **106 energy/accounting/replay checks passed**,
including all 28 energy cases. Earlier saved runs include 187 preserved/new
checks and red/green reproductions. `legacy_accounting_red.txt` and
`replay_compatibility_green.txt` document the final correction. The sole warning
is the existing Pygame/pkg_resources deprecation warning.

## 24. Complete suite and 10,800-tick smoke

**277 passed, 1 warning in 1308.56s (0:21:48)**. This includes the unchanged Steps 1–9 tests and all 28 new energy cases. The earlier 269-test pass did not cover final changes and is not substituted for this result.

The unchanged 10,800-tick gameplay smoke, forced communication recovery, offline map/survivor synchronization and recharge/relaunch assertions all passed. Full captured values are in `full_final.txt`.

| Final smoke measurement | Result |
|---|---|
| Updates | 10,800 |
| Coverage | 1.24% → 50.49% |
| Published survivors | 5/5 |
| Recharge/relaunch observed | yes |
| Stranded / zero-charge RETURNING / final LOST_COMM | none / none / none |
| Average / majority connectivity | 78.7% / 99.9% |
| Full communication-collapse ticks | 0 |
| Forced LOST_COMM recovery | recovered; maximum 827-tick streak |
| Offline map buffering | 29 local, 29 hidden before reconnect, 0 pending afterward |
| Offline survivor synchronization | private before reconnect; published once afterward |
| Field charging violations in offline fixtures | none |

The smoke's full acceptance thresholds were retained. It is a separate 10,800-tick
integration run, not pooled with the 3,600-tick timing trials.

## 25. Three-seed 3,600-tick behavioral comparison

Fresh frozen Step 9 and final Step 10 use the same established Step 8/5 probes,
normal mode, offline autonomy and failure probability zero. Each run is 60
simulated seconds. Values below are **Step 9 → Step 10**.

| Metric | 2026 | 2027 | 2031 |
|---|---:|---:|---:|
| Coverage % | 25.526 → 27.574 | 28.479 → 26.891 | 21.839 → 23.322 |
| Published survivors | 2 → 2 | 2 → 2 | 3 → 3 |
| Task awards | 27 → 35 | 40 → 32 | 28 → 24 |
| Task completions | 12 → 13 | 21 → 17 | 11 → 8 |
| Task cancellations | 9 → 16 | 14 → 10 | 12 → 9 |
| Unfinished replacements | 0 → 0 | 0 → 0 | 0 → 0 |
| Relay/task conflicts | 0 → 0 | 0 → 0 | 0 → 0 |
| Ownership inconsistency ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Physical mean connected fraction | 0.784 → 0.853 | 0.821 → 0.810 | 0.855 → 0.809 |
| Physical majority fraction | 1.000 → 0.999 | 0.980 → 0.917 | 1.000 → 1.000 |
| Full collapse ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Field contact pair-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Collision waits | 6553 → 6554 | 453 → 452 | 5319 → 9408 |
| Stranded entries | 0 → 0 | 0 → 0 | 0 → 0 |
| Final stranded drones | 0 → 0 | 0 → 0 | 0 → 0 |
| Consumed charge units | 303.336 → 337.273 | 377.844 → 353.456 | 272.199 → 315.503 |
| Recharged charge units | 205.560 → 271.063 | 416.559 → 313.165 | 275.714 → 127.368 |
| Partitions | 67 → 56 | 28 → 57 | 86 → 75 |
| Reconnects | 67 → 53 | 26 → 55 | 83 → 73 |
| LOST_COMM entries | 11 → 4 | 9 → 9 | 2 → 7 |
| Disconnected map publication | 0 → 0 | 0 → 0 | 0 → 0 |
| Disconnected survivor publication | 0 → 0 | 0 → 0 | 0 → 0 |
| Outcome | running → running | running → running | running → running |

Contacts are continuous point-agent contact pair-ticks under the established
shared-docking exception. Proximity episodes, rejected proposals and waits are
different measurements; zero observed contacts is not a universal safety proof.

## 26. Charging churn before/after

| Metric | 2026 | 2027 | 2031 |
|---|---:|---:|---:|
| Charging starts | 2348 → 13 | 5341 → 16 | 5367 → 4 |
| Threshold completions | 2348 → 13 | 5338 → 16 | 5364 → 4 |
| Actual relaunches | 7 → 11 | 19 → 14 | 7 → 4 |

The no-work fixture changes from 11 starts to one start/one completion/zero
relaunches. This follows persistent readiness, not counter suppression.
Mission totals also reflect changed allocation/trajectories.

An episode can still complete without later departure if no work becomes
available. That is meaningful readiness, not a fabricated relaunch.

## 27. Stranding/energy-safety results

Modeled reserve rejection prevents the specific tick-2,531 windy-detour stranding,
verified unstranded and at base at tick 6,000. Impossible depletion still strands.
Three-seed measurements in section 25 do not establish universal safety.

## 28. Path-search impact

| Metric | 2026 | 2027 | 2031 |
|---|---:|---:|---:|
| All counted path searches | 2435 → 5331 | 3384 → 6455 | 1038 → 3400 |

Step 10-only diagnostics (Step 9 has no equivalent counters; unavailable is not zero):

| Metric | 2026 | 2027 | 2031 |
|---|---:|---:|---:|
| Energy assessments | 246605 | 711189 | 182857 |
| Infeasible assessments | 53 | 13829 | 1355 |
| Energy route searches | 4562 | 5596 | 2650 |
| Energy returns | 1 | 1 | 0 |
| Energy-triggered cancellations (call probe) | 1 | 0 | 0 |
| Final-admission rejection events | 0 | 0 | 0 |

Energy-route searches are policy cache misses through the counted planner hook,
not the net change in all searches: policy also changes replans/allocation.
Pure estimate queries can perform uncached, non-accounting searches, including
diagnostic recovery explanations. Those are not counted by the established
planner-hook probe; the table is not an exhaustive count of every A* invocation.
Reuse/invalidation tests prove cache correctness for tested keys/terrain changes,
not optimality or a measured cache speedup.

## 29. Step 9 → Step 10 performance

| Metric | 2026 | 2027 | 2031 |
|---|---:|---:|---:|
| Mean ms | 11.671 → 37.064 | 15.624 → 95.267 | 13.132 → 27.282 |
| p50 ms | 11.741 → 17.982 | 15.614 → 98.873 | 14.255 → 10.144 |
| p95 ms | 18.443 → 76.946 | 27.500 → 194.657 | 21.973 → 60.105 |
| p99 ms | 28.727 → 128.327 | 35.654 → 297.577 | 30.241 → 85.914 |
| Max ms | 73.433 → 892.576 | 82.510 → 650.014 | 58.690 → 412.377 |

Wall-clock update timing includes established contact/radio/task/component probes.
The added cancellation-call observer has unquantified overhead; post-run
state extraction is outside timing. Trials ran sequentially, without concurrent
tests. These are single-trial observations, not causal speedup/regression claims.
Different policies perform different work. Historical uninstrumented Step 9 and
older ADSS/Phase 1 timings are not mixed in. No unrelated optimization occurred.
There is no isolated measurement of estimator CPU cost; search counts measure
operations, not elapsed time attributable solely to this policy.

## 30. Seed-repeat and presentation reproducibility

Seed 2026 repeats exactly across **40 non-timing top-level result fields**, including energy diagnostics, full authoritative projection, metrics, outcome and accounting hash. All seven presentation conditions match across 9 authoritative groups.

| Condition | FPS setting | Equal authoritative state |
|---|---:|---|
| headless | 60 | yes |
| normal | 60 | yes |
| normal | 30 | yes |
| normal | 144 | yes |
| reduced | 60 | yes |
| overlays_off | 60 | yes |
| noisy | 60 | yes |

Matrix horizon: 180 ticks; hardware failure probability 0.003 and weather interval 30 ticks. Each run recorded 3 failures and 6 weather changes. FPS is a presentation setting, not a wall-clock throttle. Reduced rendering is every seventh tick. Rendering is checked before/after every draw for mutation of authoritative state, including simulation RNG. Display drivers: headless, windows.

Final authoritative state SHA-256: `e9198b2f6796c606edcec35750ecc433e9d38abc5d2afd847db69ad34b1a2751`.

Knowledge SHA-256: `17f4fc00652849f95e2c386b2b873a12ce18cbc83ca93e6d43b88e24a688c8ce`.

Experiment SHA-256: `1e62ad727c0ffc67557a631c475b30150f0139cb5647df3a1b919c6238878f9d`.

Event hash: `1bf33781d03106b644e74723a6cdcd7ebd811802f59f5a3a733ff5756c9edd88`. Step 9/10 trajectory equality is neither required nor claimed.

Hashes cover the established recorded state/knowledge/RNG projections and energy
diagnostics, not every Python object or a restorable checkpoint.

## 31. Behavioral trade-offs

Admission is more conservative about detours/missing routes, while pricing a
smaller explicit work horizon than the old four-scan allowance. Ready waiting
permits top-up and genuine departure without state churn. Coverage/productivity
need not improve; changed progress and reserve protection must be considered
together. Seed-dependent measurements above do not predict all maps.
Using the actual SCANNING drain instead of moving drain can also lower an
outbound estimate. The new policy is therefore not uniformly stricter than the
old heuristic on every route.

Coverage increased for 2026 and 2031 but decreased for 2027; globally published
survivors remained 2/2/3. Average connectivity improved for 2026 and decreased
for the other seeds. Seed 2027 majority connectivity fell from 98.03% to 91.75%.
Charging events now reflect coherent episodes, but real relaunch counts did not
uniformly increase. The increased latency and assessment counts are material
limitations, not hidden by the charging-counter reduction.

## 32. Remaining confirmed limitations

Only the next waypoint plus modeled return is forecast. Future weather, traffic
and radio detours remain uncertain. Mixed wind/base-center pricing can overestimate.
Static return feasibility does not prove the future route remains unchanged.
The retained low-charge guard can be stricter than the modeled budget. Terrain
comparisons and added searches have cost. Assessments are not unique rejected
tasks. No survivor rescue, terminal-impossibility policy or checkpoint is added.
Controlled work reassessment does not cap assessment frequency in allocation,
relay or communication-risk callers; repeated candidate checks remain possible.

## 33. Remaining unverified risks

Extreme settings, prolonged congestion, adversarial weather, mid-flight terrain
changes and larger swarms are not exhaustively tested. Cross-platform exact
floating-point equivalence is unproven. Experiment identity covers seed/config,
not source: equal Step 9/10 identities do not imply equal policies. Source
manifests identify this implementation. These evidence limits are not confirmed bugs.

## 34. Git diff summary

| File | Added | Removed |
|---|---:|---:|
| `config.py` | 2 | 2 |
| `core/analytics.py` | 8 | 0 |
| `core/battery.py` | 10 | 4 |
| `core/drone.py` | 97 | 43 |
| `core/replay.py` | 19 | 0 |
| `core/swarm.py` | 40 | 10 |
| `core/energy.py` | 158 | 0 |
| `tests/energy_tests.py` | 322 | 0 |
| `benchmarks/step10.py` | 78 | 0 |
| `docs/step10_engineering_report.md` | 483 | 0 |

Production: **7 files, +334/−59**. With new tests/harness: **9 files,
+734/−59**. Including this report: **10 files, +1217/−59**.
All 37 other captured baseline paths are unchanged, including every preserved
test, prior benchmark, communication/collision/planner/clock/RNG module, engine
factory and UI. Config AST is unchanged: its two edits are comments only.

`git diff --check`: **exit 0**, with line-ending normalization notices only.
The normalized scoped `git diff --no-index --check` emits no diagnostics (exit 1
indicates file differences in no-index mode). The scoped patch includes new files
that ordinary tracked-file diff checking omits. Final source/test/harness hashes
match the 46-path manifest used for final tests, benchmarks and repeats.

Artifacts: `validated_source_hashes.json`, `final_hashes.json`, `scoped_step10.patch`,
`comparison.json`, `run_completion.json`, `git_diff_check.txt` and
`scoped_whitespace.txt`.

Git HEAD also includes approved uncommitted Steps 1–9 work; the scoped patch uses
the frozen Step 9 baseline. Generated validation evidence is additional to the
source/test/harness/report patch. No prior work was committed, reset or discarded.

## 35. Accurate energy/autonomy claims

ADSS supports deterministic route-aware next-waypoint admission in abstract charge
units, explicit reserve, bounded route reuse, controlled reassessment and coherent
charging/readiness/departure accounting. The policy prevented the reproduced
avoidable stranding case. It cannot claim physical battery accuracy, perfect
prediction, guaranteed return, eliminated stranding or deadlock-free navigation.

## 36. Recommendation for the next roadmap step

If approved separately, start Step 11 with measured bottlenecks and choose one
bounded optimization, preserving behavioral equivalence. New path-search counts
and established reservation costs are candidates for investigation, not reasons
to change code automatically. **Step 11 has not begun. Stop for user approval.**

In particular, profile repeated energy assessment/geometry work before choosing
an optimization: these runs made 182,857–711,189 assessments. This count alone
does not attribute the measured latency to a specific function.


Evidence provenance: Python 3.13.7, Pygame 2.6.1, Windows. Frozen Step 9 source:
`external frozen baseline (step10_step9_baseline)`.
All 43 captured baseline hashes still match. Final measurements are `before.json`,
`after.json`, `repeat.json` and `presentation_matrix.json`; focused/full logs and
red regressions are retained alongside them. The before runs were recovered,
not repeated. The incomplete pre-compatibility full run was stopped; the final
277-test suite covers the correction.

```text
python -m pytest -q -rP
python benchmarks/step10.py --ticks 3600 --seeds 2026 2027 2031 --output after.json
python benchmarks/step10.py --ticks 3600 --seeds 2026 --output repeat.json
python benchmarks/step10.py --matrix --ticks 180 --seeds 2026 --output presentation_matrix.json
```
