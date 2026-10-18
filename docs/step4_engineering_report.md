# ADSS — Step 4 engineering closure report

Date: 2026-09-22. Scope: reservation and collision contract only. Phase 1 remains approved; Step 5 has not started.

## 1. Executive summary

Step 4 validation is complete. The final code passes **88 tests**, including all 51 Phase 1 tests and 37 Step 4 cases. No production changes were made during the final continuation: production hashes still match the previously validated Step 4 implementation.

Across seeds 2026, 2027 and 2031, each run for 3,600 ticks, actual field point-contact pair-ticks fell from **387 to 0** under the same continuous-contact probe. This is a bounded empirical result for point agents, not a blanket physical collision-free claim. Unfinished-task replacements, relay/exploration conflicts and ownership inconsistencies remain zero. Seed 2026 repeats exactly across all 24 recorded non-timing fields, including the final-state hash.

The added safety has costs: waits are frequent, mission trajectories change, and mean update latency increases on all three seeds. The long-run smoke test improves coverage from 47.14% to 49.00% but lowers average connectivity from 79.7% to 75.6%. Those tradeoffs are retained and reported rather than compensated with unrelated changes.

## 2. Original reservation defects reproduced

- **Ownership overwrite:** cell/time storage held one owner; a later claimant replaced the earlier owner and could see no penalty against it. Owner sets now preserve both claims.
- **Planner-cost/time mismatch:** A* queried temporal penalties with `int(g_score)+1`. Accumulated terrain/congestion/bias cost is not execution time. A focused probe reproduces that call; A* now uses only a static spatial reservation envelope.
- **Sparse smoothed-path reservations:** enumeration assigned one artificial step per sparse waypoint, omitting swept intermediate cells. Forecasts now execute the motion rule tick by tick and record swept geometry.
- **Missing stationary occupancy:** idle, failed, stranded and charging agents without paths were absent. Forecasts now hold their actual positions throughout the horizon.
- **No execution enforcement:** focused motion reproducers demonstrate same-arrival, head-on, diagonal, stationary-agent and wind-speed contacts despite soft planning costs. Movement now goes through a one-tick gate.
- **Additional Step 4 edge cases:** regressions caught an obsolete sidestep surviving a state change, nearly coincident departures hiding contact beyond the docking boundary, and final docking approach ignoring a pending sidestep. Each has a saved failing test and a local correction. Duplicate legacy owner trajectories are explicitly rejected; reroute start waypoints cannot replenish backoff budgets.

The initial Phase 1 red run recorded **22 failures and three passes**. Some failures specified new contract APIs; they are not all independently existing bugs. Soft congestion penalties were an intentional original design choice, not themselves a bug. Normal failure transitions already cleared paths after Phase 1; that safeguard passed before Step 4 and was preserved. A synthetic stale failed path is additionally ignored by forecasting.

## 3. Final reservation contract

Time is an **absolute simulation tick**, not wall time, A* cost or waypoint index. A record at tick `t` covers the swept segment over `(t-1,t]`; the initial epoch records current occupancy. The default forecast horizon remains 24 ticks. Each cell/tick and endpoint-cell edge/tick stores a set of owners. Overlapping claims coexist as potential-conflict information; storage never silently chooses a winner. Exact per-owner pixel positions and per-tick segments remain available alongside coarse cells.

Forecasts repeat the same capped movement, starting-cell wind speed, exact waypoint arrival and terrain geometry as execution. On a uniform segment, arrival takes the required whole number of motion ticks; wind boundaries and waypoint consumption are simulated explicitly. Within a tick, collision checks interpret the capped displacement as a straight, uniformly traversed segment. A* consumes a static nonnegative spatial penalty; it makes no temporal reservation query.

IDLE, FAILED, STRANDED and CHARGING occupy their current positions, even if a stale path exists. RETURNING follows its current path or physical final approach; entering the docking zone permits the existing dock snap. Shared occupancy is intentionally allowed inside the existing **30-pixel physical docking disk**. The disk has no capacity model. Outside it, coincident centers are prohibited by the execution gate.

Forecasts are conditional advice for the currently known path. Future task awards, state changes, waits and replans can invalidate them; rebuilding updates the view, and the current-tick execution gate is authoritative. The legacy `reserve_path` signature remains as a normal-speed/free-space adapter. Wind/terrain-aware callers use `rebuild(drones, start_tick=...)`. Re-reserving the same legacy owner without rebuilding now raises `ValueError`.

## 4. Final collision/yielding policy

Swarm updates drones in ascending drone-ID priority by default. Reversed priority is tested explicitly. At tick start, the gate snapshots every position. A proposed move is checked against earlier committed trajectories and stationary fallback trajectories for peers that have not moved. This conservative policy permits an unprocessed drone to wait without invalidating an earlier commitment.

Rejected movement stops velocity, retains position, task and waypoint, and records a wait. Collision waits do not trigger the unrelated generic stall-task cancellation. After 150 consecutive blocked movement attempts, an eligible lower-priority mover, or a mover blocked by a stationary-state peer, can search fixed-order cardinal neighbors for a terrain-valid sideways/backward detour. The detour is checked again on every executed tick. Finishing it clears the path so the retained task can be replanned.

At most two candidate-search attempts are allowed per goal/state before budget exhaustion is recorded. Reaching the goal, or changing goal/state, permits a new episode; merely replanning through a start waypoint does not. When no safe move or useful detour is available, the drone waits. Battery consumption continues. The controller neither teleports agents nor forcibly overwrites their task ownership.

## 5. Geometry and conflict semantics

- **Vertex:** drone centers coincide at a tick boundary outside the shared docking disk. Coarse cell overlap alone is a potential conflict, not an enforced physical contact.
- **Swap:** oppositely directed motion occupies the same point at the same fraction of a tick, including head-on exchanges.
- **Geometric crossing:** two swept segments intersect at the same time. Geometric intersection at different times is allowed.
- **Continuous check:** relative linear motion is evaluated over the entire tick, with a `1e-7` pixel numerical contact tolerance. The entire tolerance-contact interval is checked against the docking exception, including almost co-moving departures.
- **Point-agent model:** radius remains visual. This contract does not enforce finite-body separation, rotor clearance, acceleration limits or a near-miss distance. Terrain remains governed by the Phase 1 closed-cell/corner supercover rule.

## 6. Production files changed

| File | Step 4 responsibility |
|---|---|
| `core/geometry.py` | Shared executable motion step, swept-cell collection and synchronous contact geometry. |
| `core/intelligence.py` | Multi-owner forecasts, absolute tick records, static planner envelope, execution gate and bounded backoff. |
| `core/drone.py` | Uses shared motion/gate, preserves waypoints on waits, follows/clears temporary detours and retains docking safeguards. |
| `core/swarm.py` | Supplies tick epochs, snapshots movement and applies deterministic commit order. |
| `core/pathfinding.py` | Replaces cost-indexed temporal queries with the static reservation envelope. Phase 1 queue/result semantics remain intact. |

No communication delivery semantics, clock/RNG, replay, analytics architecture, UI or configuration were changed for Step 4. The benchmark instruments existing APIs externally.

## 7. Tests added

`tests/reservation_tests.py` contains **29 test functions / 37 parameter-expanded cases**:

- **Reservations:** multi-owner visibility, duplicate legacy owner rejection, smoothed intermediate cells, absolute epochs, fast multi-cell sweeps, stationary-state occupancy, inactive stale paths, existing failure cleanup, normal/wind forecasts, and no A* cost/time queries.
- **Geometry/execution:** same arrival, head-on swap, crossing diagonals, different-time crossing, all four stationary states, mixed wind speeds, multiple simultaneous conflicts, normal/reversed priority and collision waits retaining tasks.
- **Docking:** shared occupancy and physical docking, coincident/near-coincident departures, final-approach forecast, and yielding around a blocked docking entrance.
- **Corridors/backoff:** single-agent traversal, opposing traffic with bounded recovery, task retention during sidesteps, state-change cleanup, reroute-budget protection, and no-space budget exhaustion.
- **Determinism:** repeated execution with permuted input lists, plus the separate full seeded benchmark repeat.

Existing Phase 1 test files and `config.py` retain their saved hashes. The original tests and acceptance thresholds were not weakened.

## 8. Focused test results

The final focused run passed **83 cases**: 37 Step 4 cases plus the 46 Phase 1 motion, A* and task-lifecycle regression cases. The saved log is `benchmarks/results/step4/focused.txt`. Earlier failing evidence remains in `red_tests.txt`, `extended_red.txt`, `boundary_red.txt`, `docking_yield_red.txt` and `representation_red.txt`. The latter also records a no-space fixture corrected to actually remove retreat space; that fixture issue was not represented as a production bug.

## 9. Complete suite and smoke results

Command: `python -u -m pytest -q -s`. Result: **88 passed, one pre-existing third-party deprecation warning, 191.82 seconds**. `full_final.txt` validates the exact current production hashes. The interrupted `full_initial.txt` is incomplete evidence and is not treated as a passing run.

| 10,800-tick seed-2026 smoke metric | Phase 1 | Step 4 |
|---|---|---|
| Coverage | 47.14% | 49.00% |
| Survivors | 4/5 | 4/5 |
| Average connectivity | 79.7% | 75.6% |
| Majority-connected fraction | 99.8% | 99.5% |
| Minimum connected | 2/8 | 4/8 |
| Full communication-collapse ticks | 0 | 0 |
| Final stranded / empty-battery RTB drones | 0 / 0 | 0 / 0 |
| Final LOST_COMM drones | 2 | 2 |
| Maximum normal-run lost streak | 540 ticks | 498 ticks |
| Forced communication recovery | 655 ticks | 794 ticks |
| Recharge/relaunch | Pass | Pass |
| Offline map buffering and synchronization | 29 cells, pass | 29 cells, pass |
| Offline survivor buffering and synchronization | Pass | Pass |

Communication delivery semantics were not changed. The changed routes affect measured connectivity and recovery duration. All existing acceptance checks pass; the average-connectivity reduction is still a real behavioral cost. This long smoke run did not record the standalone continuous-contact probe or lifecycle benchmark counters, so short-run safety numbers are not presented as long-run measurements.

## 10. Before/after safety metrics

Each column compares 3,600 ticks with the same seed, zero random-failure probability, normal mode and offline autonomy enabled. Both versions use `step4-contact-interval-v2-components`; the saved Phase 1 production snapshot was hash-verified before running it.

| Metric | 2026 before → after | 2027 before → after | 2031 before → after |
|---|---|---|---|
| Actual field point-contact pair-ticks | 129 → 0 | 38 → 0 | 220 → 0 |
| Closest-approach proximity episodes | 44 → 24 | 42 → 30 | 42 → 40 |
| Rejected proposed peer conflicts | N/A → 3384 | N/A → 5857 | N/A → 6602 |
| Wait/yield decisions | N/A → 3384 | N/A → 5857 | N/A → 6602 |
| Backoff candidate-search attempts | N/A → 1 | N/A → 2 | N/A → 4 |
| Sidesteps/retreats initiated | N/A → 1 | N/A → 2 | N/A → 4 |
| Backoff-budget exhaustion events | N/A → 0 | N/A → 0 | N/A → 0 |

**Interpretation:** actual contact counts are drone-pair/tick observations, not distinct crash incidents. Proximity episodes use the probe's closest-approach threshold of 0.85 cells, with the shared-base exception; they are not actual contacts. `conflicts` counts peer conflicts found in rejected movement proposals under the committed/stationary-fallback policy. `waits` counts rejected requests. These are prevented proposed contacts under that policy, not a measured counterfactual count of crashes that an unconstrained run would have suffered.

`recoveries` counts detours initiated, not proven completed missions or globally resolved deadlocks. `deadlocks` counts exhausted backoff episodes, not cycles detected in a dependency graph. Phase 1 had no equivalent gate counters: N/A is not a fabricated zero. Separate mission-wide vertex/swap/crossing counts were not collected; their semantics are covered by focused tests, while the mission probe aggregates all continuous point contacts. Zero exhausted-budget events in these runs does not establish absence of blockage.

## 11. Before/after behavioral metrics

| Metric | 2026 before → after | 2027 before → after | 2031 before → after |
|---|---|---|---|
| Coverage % | 28.09 → 24.12 | 26.06 → 30.55 | 22.59 → 24.64 |
| Survivors discovered | 2 → 2 | 2 → 2 | 3 → 3 |
| Average connectivity % | 85.93 → 83.44 | 82.64 → 81.74 | 80.41 → 80.42 |
| Majority-connected % | 99.42 → 100.00 | 99.00 → 99.31 | 92.25 → 100.00 |
| Full communication-collapse ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Stranded drone-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Final stranded drones | 0 → 0 | 0 → 0 | 0 → 0 |
| Unfinished-task replacements | 0 → 0 | 0 → 0 | 0 → 0 |
| Relay/exploration conflicts | 0 → 0 | 0 → 0 | 0 → 0 |
| Ownership inconsistencies accumulated over ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Final ownership inconsistencies | 0 → 0 | 0 → 0 | 0 → 0 |
| Frontier awards | 25 → 19 | 22 → 23 | 23 → 24 |
| Frontier completions | 13 → 10 | 13 → 11 | 13 → 13 |
| Path searches | 2204 → 2222 | 2806 → 3038 | 1150 → 3101 |
| Field charging violations | 0 → 0 | 0 → 0 | 0 → 0 |

All major Phase 1 ownership invariants remain intact across all three seeds. Coverage, discoveries, awards, completions and route counts may change under the new movement and congestion policy; the table retains both improvements and reductions rather than selecting favorable seeds.

## 12. Performance: Phase 1 → Step 4

These are fresh, sequential runs on the same host using the same harness. Latency encloses `Mission.update` including the small component-timer wrappers, but excludes the post-update safety/ownership probes. No benchmark simulations were run concurrently. They are observations from one primary run per seed, not confidence intervals or a hard real-time guarantee. Maxima are sensitive to scheduling and GC.

| Seed/stage | Mean ms | p50 ms | p95 ms | p99 ms | Max ms |
|---|---|---|---|---|---|
| 2026 Phase 1 | 8.991 | 9.957 | 17.322 | 19.533 | 57.073 |
| 2026 Step 4 | 11.957 | 12.244 | 21.279 | 25.386 | 129.572 |
| 2027 Phase 1 | 9.541 | 7.827 | 20.491 | 25.886 | 71.923 |
| 2027 Step 4 | 11.238 | 9.991 | 22.139 | 26.169 | 79.060 |
| 2031 Phase 1 | 9.772 | 11.881 | 17.147 | 19.951 | 30.400 |
| 2031 Step 4 | 10.086 | 8.726 | 17.614 | 23.034 | 40.952 |

Mean-latency increases: **2026: 33.0% (+2.966 ms), 2027: 17.8% (+1.698 ms), 2031: 3.2% (+0.314 ms)**.

Reservation rebuilding, measured within the actual missions (two calls per update):

| Seed | Calls, each stage | Phase 1 mean/call ms | Step 4 mean/call ms | Step 4 p95/call ms | Phase 1 → Step 4 ms/update |
|---|---|---|---|---|---|
| 2026 | 7200 | 0.0090 | 2.3531 | 3.0677 | 0.0180 → 4.7062 |
| 2027 | 7200 | 0.0093 | 2.4641 | 3.1772 | 0.0186 → 4.9282 |
| 2031 | 7200 | 0.0083 | 2.4751 | 3.0846 | 0.0167 → 4.9501 |

Collision gate, including its occasional backoff checks:

| Seed | Gate calls | Mean/call ms | p95/call ms | Total ms/update |
|---|---|---|---|---|
| 2026 | 17216 | 0.0089 | 0.0144 | 0.0424 |
| 2027 | 19703 | 0.0098 | 0.0176 | 0.0537 |
| 2031 | 20364 | 0.0095 | 0.0168 | 0.0537 |

Phase 1 had no corresponding execution gate. The gate table excludes terrain checks and the forecasting motion helper; it is not a measure of all motion code. Component timings are inclusive wall times, so they are descriptive cost attribution rather than a controlled isolated subtraction. Most direct new coordination cost is reservation construction; the gate itself is much smaller. Changes to routes and task timing also change the rest of mission work. No unrelated optimization was attempted, and the final continuation made no production optimizations.

**Separate historical comparison — Original ADSS → Phase 1:** the saved Phase 1 engineering measurements reported mean update times of **3.418 → 8.984 ms** (2026), **6.270 → 9.098 ms** (2027), and **5.390 → 9.546 ms** (2031), or 2.63×, 1.45× and 1.77×. Those are earlier runs using the tranche-1 harness. They are not mixed with the fresh Step 4 timings or used to calculate the incremental percentages above. The interrupted September 19 Step 4 baseline/profile is likewise superseded for comparison; its coarse CPU micro-timer even rounded the old rebuild cost to zero, so it is not used as a valid zero-cost measurement.

## 13. Reproducibility

Seed 2026 was repeated for 3,600 ticks under the same final Step 4 implementation. **All 24 non-timing fields match exactly**, including counters, fog/discovery/path/battery-derived final state hash and states. Both component call counts also match. The established hash covers fog, discovered survivor IDs, weather and each drone's position, state, battery, path and scan queue; it is not a hash of every internal object.

Final and repeated seed-2026 hash:

`78ca5dba2d20351341ce32ce70798fe2a39c3b7b9bab48df36bcaad1aea29a3f`

First-run mean/p95/p99: 11.957/21.279/25.386 ms. Repeat: 11.725/21.101/23.675 ms. Timing variation is expected and excluded from deterministic equality.

The fresh Phase 1 snapshot reproduced every recorded non-timing field and hash from its earlier closure for all three seeds. Step 4's trajectories differ from Phase 1 by design; equality with the old trajectory was not required. See `reproducibility_check.json` for every compared field.

## 14. Deadlock and corridor behavior

A single mover traverses a narrow corridor correctly. Opposing movers cannot swap through one another. An eligible mover can yield sideways or retreat when terrain and occupancy permit. The no-space test exhausts exactly two recovery searches, records one budget-exhaustion event and keeps the task while waiting.

This is not a complete corridor solver. Static priorities can cause starvation, opposing traffic may have no legal passing space, a pending detour can itself become blocked, and battery drain continues while waiting. The implementation does not search joint configurations, schedule corridor entry globally, detect every dependency cycle or guarantee that all tasks finish. Introducing MAPF would exceed this approved tranche and is not required to state the current contract honestly.

## 15. Intentional behavior changes

- Movement can wait or temporarily detour to avoid field point contacts.
- All reservation owners remain visible, including stationary and inactive occupants.
- Planning uses a static congestion envelope, replacing incompatible cost-indexed time penalties.
- Priority controls which safe proposals commit first; forecasts and later paths therefore change deterministically.
- Collision waits preserve ownership rather than triggering generic task replacement.
- The legacy duplicate-owner adapter now fails explicitly instead of storing contradictory owner trajectories.
- Short-run mission progress, connectivity and latency change as measured above. Shared docking remains an explicit exception.

## 16. Remaining confirmed Step 4 limitations

The implementation models point centers, not finite aircraft; visual overlap and near misses can remain. Forecasts cover only a finite horizon/current plan and are not a global space-time solution. The safety arbiter centrally observes all agents, including disconnected ones; this is simulator-level coordination, not distributed radio-based collision avoidance. Base capacity is unlimited. Backoff is bounded per goal/state, not per entire mission. Exhaustion metrics do not enumerate all possible blockages. Stationary failed/stranded agents may permanently obstruct narrow passages. Initial overlapping field states are not repaired automatically. Explicit operator rescue/repositioning and motion invoked without the reservation gate lie outside the validated coordinated update contract.

The performance overhead and reduced long-run average connectivity are measured limitations. The legacy cell-only reservation adapter cannot infer wind or terrain. These limitations are not hidden behind a blanket collision-free or deadlock-free claim.

## 17. Remaining unverified risks

The three normal-mode seeds, one long smoke run and focused fixtures do not cover every map, speed, externally edited state, failure schedule or large fleet. Arbitrary floating-point extremes, large-fleet latency tails, liveness under sustained adversarial traffic and all combinations of mid-detour state/terrain changes remain unverified. No maximum fleet-size, physical safety margin or probabilistic reliability bound is established. These are coverage limits, not claims of newly reproduced defects. Communication-boundary defects from the roadmap remain deferred to Step 5.

## 18. Git diff summary

The repository already contains the approved uncommitted Phase 1 work. The following diff is specifically **against the saved Phase 1 source**, not against the original Git commit:

| Step 4 source/test/harness file | Added lines | Removed lines |
|---|---|---|
| core/drone.py | 30 | 16 |
| core/intelligence.py | 199 | 51 |
| core/swarm.py | 4 | 3 |
| core/pathfinding.py | 5 | 5 |
| core/geometry.py | 57 | 0 |
| benchmarks/step4.py | 162 | 0 |
| tests/reservation_tests.py | 342 | 0 |

Source/test/harness subtotal: **799 additions, 75 deletions across seven files**, of which five are production files. Including this 250-line report and 20 versionable validation artifacts (2,032 lines), the complete Step 4 repository delta against Phase 1 is **28 files, 3,081 additions and 75 deletions**. Ignored console logs and external task artifacts are excluded from that total. `source_manifest.json` records source hashes, preservation checks and scoped line counts; the saved `step4_only.diff` separates Step 4 from Phase 1. The ordinary Git diff includes both tranches and must not be labeled Step 4-only.

`git diff --check` passes. No Phase 1 files were reverted, no existing tests were weakened, and no communication delivery, RNG/clock, replay, analytics architecture, UI or unrelated performance systems were modified. No commit, push or PR was created.

## 19. Step 4 assessment

ADSS can accurately claim deterministic, centralized, tick-based reservation forecasts with preserved multi-owner claims; execution-compatible point geometry; a tested priority/wait/backoff controller; explicit stationary and docking rules; and zero observed field point contacts in the three measured final runs while retaining the Phase 1 ownership invariants.

It cannot claim complete MAPF, universal collision freedom, finite-body safety, decentralized avoidance, deadlock freedom, starvation freedom, guaranteed mission completion or improved overall performance. The safety improvement, mission tradeoffs, component costs and reproducibility are separately evidenced.

## 20. Recommendation and stop boundary

Review and accept the measured Step 4 safety/throughput/connectivity/latency tradeoffs. The next approved-roadmap candidate remains **Step 5 — connectivity and discovery boundaries**: first-disconnected-tick delivery gating, explicit zero-connectivity handling and failure-radio semantics, with partition/rejoin tests. This is a recommendation only. **Step 5 has not been implemented; work stops here pending approval.**

## Evidence and reproduction

- `benchmarks/results/step4/full_final.txt`: current complete-suite and long-smoke evidence.
- `benchmarks/results/step4/focused.txt`: 83 focused passes; adjacent red logs preserve failures before fixes.
- `baseline_verified.json`, `after.json`, `repeat.json`: matching v2 probe runs; `.partial.json` files are checkpoints, not separate experiments.
- `reproducibility_check.json`, `source_manifest.json`: equality and source provenance.
- `benchmarks/step4.py`: safety probe, component timing and checkpointed runner. Use the same script against the saved Phase 1 source and the final source, with seeds `2026 2027 2031`, `--ticks 3600`, failure probability zero.
- Final command: `python -u -m pytest -q -s`. Benchmark: `python -u benchmarks/step4.py --label step4-final --output benchmarks/results/step4/after.json`. Repeat adds `--seeds 2026` and a separate output filename.

The Phase 1 snapshot and scoped patch are retained in the task artifact directory `local evidence directory` (`step4_phase1_source`, `step4_phase1_run`, `step4_only.diff`).
