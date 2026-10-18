# ADSS — Step 6 engineering report

Date: 2026-09-27. Scope: P1 simulation clock, RNG isolation and experiment configuration. Steps 1–5 remain approved. Step 7 has not begun.

## 1. Executive summary

The simulator now advances in fixed 1/60-second simulation ticks, owns simulation randomness independently of presentation draws, and captures canonical immutable experiment settings at factory creation. The full suite passes **157 tests**, including all **128 previously approved cases** and **29 new Step 6 cases**. No existing test or acceptance threshold was changed.

All seven alternative presentation conditions now match the headless state and knowledge hashes; all seven differed on unchanged Step 5. The final seed-2026 repeat matches all **33 available non-timing fields**, including both established hashes, the expanded behavioral hash and experiment identity. Three 3,600-tick mission runs retain zero measured field point contacts, disconnected publication, unfinished-task replacement, relay conflicts and ownership inconsistencies. These are measured results, not exhaustive safety guarantees.

## 2. Original time defects reproduced

`MissionStats` used `time.time()` for elapsed duration, so equal tick counts produced different mission times and pauses advanced the displayed duration. A regression replaces wall time with a large jump and checks that six updates mean 0.1 seconds; it failed before the fix. Completion at time zero also now uses an explicit `None` check.

`TARGET_FPS` controlled coverage history windows, per-minute coverage growth, communication-risk relaxation cadence/history and emergency recharge allowance in `Swarm`, plus CSV sample cadence in `Mission`. A dedicated stalled-coverage fixture produced different relaxation at 30 and 60 FPS settings. Those conversions now use the fixed simulation tick rate. This changes no communication thresholds or relaxation policy constants.

Movement, wind, scans, battery drain/recharge, grace/recovery, reservations, negotiation, task stalls and weather timers were already update-count based. They were not incorrectly rewritten as broken time systems. `pygame.time.Clock` caps presentation pacing, and the app advances one update per running loop; there was no variable-delta physics integration to replace.

## 3. Original RNG coupling reproduced

Map construction seeded both Python's process-global RNG and NumPy's process-global RNG. World placement, drone initial scatter/battery, hardware failure trials and weather transitions consumed the same Python stream as particles, weather-overlay effects and demo camera selection. A UI draw could therefore alter subsequent failure or weather outcomes. NumPy was seeded but had no simulation-critical random draws in the audited code.

Actual renderer calls, changed render frequency, disabled overlays/dashboard/minimap and injected unrelated Python/NumPy draws reproduced different simulation results. The unchanged-source matrix records seven state and seven knowledge mismatches against headless. A separate regression demonstrates that creating a map changed the caller's global RNG state.

## 4. Configuration and reproducibility issues reproduced

Most core settings were read from mutable module globals during every update, while some construction-time values were already cached. Changing globals could silently change an existing run's speed, failure probability or behavior, with no experiment identity describing it. The regression mutates globals after constructing equivalent missions and compares their subsequent state. The missing experiment identity/snapshot test is a new API requirement, distinguished from an existing incorrect API.

Initial regression evidence: **12 failed, one passed** on unchanged Step 5. This includes the new snapshot API requirement, not 12 independent old bugs. Existing per-drone `ai_rng`, arithmetic AI seeds and cell-based planner tie noise were already deterministic and remain intact.

## 5. Final simulation-time contract

One normal `Mission.update()` advances `SimulationClock.tick` by one. One tick represents exactly **1/60 simulation second**. `Mission.frame` remains the compatible absolute-tick property used by reservations, drones and swarm; it delegates to the clock rather than maintaining a second counter. `MissionStats` reads clock seconds, and records its completion time in those units.

All behavioral durations and per-frame rates retain their existing per-tick interpretation. The tick rate is fixed, not inferred from render FPS. Wall time remains permitted for performance profiling, display FPS, export timestamps and file naming. No behavioral system reads wall time. Continuing to call update after mission completion still advances the simulated world, as the existing benchmark does; completed mission duration remains frozen. Replay playback remains its existing separate, incomplete snapshot path and is excluded from the forward-simulation reproducibility contract.

## 6. Rendering and time separation

Pause means the controller does not call update. Rendering any number of frames, delaying rendering or consuming presentation randomness cannot advance simulation time. `TARGET_FPS` controls presentation pacing only. The main loop remains one tick per running loop iteration; lower FPS or heavy rendering can slow progress per wall-clock second. This tranche guarantees equal outcomes at equal tick counts, not identical real-time throughput or catch-up scheduling. No accumulated-wall-delta loop, UI redesign or dropped-tick policy was added.

The matrix renders to real Pygame software surfaces using the existing complete render function, with dummy video/audio drivers. FPS settings are 30/60/144, not physical monitor measurements. Reduced rendering draws every seventh tick; the delayed condition adds sleeps. A separate paused-render test draws without updates and proves unchanged behavioral state and elapsed simulation time.

## 7. RNG ownership and streams

`Experiment` owns cached `random.Random` instances. World generation uses the experiment's `world` stream; drone scatter and initial battery use `initialization` streams keyed by drone ID; weather uses `environment`; hardware failures use `failure` keyed by drone ID. Map creation no longer seeds either process-global RNG. The only nondeterministic simulation entry is resolving an unspecified seed from `SystemRandom`; that resolved integer is returned and stored in the identity.

Existing per-drone planning/personality RNG remains owned by each drone. Swarm queue/frontier policy continues to use its existing local deterministic `Random` instances keyed by AI seed and task/sector. A* tie noise remains its stable cell/AI-seed function. Presentation retains Python's global RNG for visual effects and camera selection, which simulation-critical code no longer consumes. No NumPy simulation stream was added because there are no NumPy random simulation draws to route.

## 8. Seed derivation

Named streams except world derive a seed from SHA-256 of canonical JSON `["adss-streams-v1", experiment_seed, domain, agent_id]`, interpreted as a big-endian integer. No process-randomized `hash()` is used. The world stream intentionally uses the original integer seed directly to retain existing terrain generation. The retained planner AI seed is `seed * 1009 + drone_id * 9176`, with the existing task/sector derivations unchanged.

Stream separation ensures that consuming one stream does not consume another's PRNG state. It is not a proof of statistical independence. A changed weather outcome can still affect motion and later eligibility for a failure trial through legitimate simulation causality; the design does not promise counterfactual trajectory independence between physical systems.

## 9. Experiment configuration

`make_simulation(seed, experiment_config=...)` captures or accepts an immutable `ExperimentConfig`, then constructs map, swarm and mission inside its context. `Mission.update` activates that same context and restores the previous context even on exceptions. Core settings access uses a small context-local adapter, without assigning to global config values during updates. This permits sequentially interleaved experiments with different snapshots.

The snapshot captures all uppercase config entries except presentation colors/fonts, window dimensions/title, render FPS, map display offsets/pixel-surface dimensions, visual radii, export directories and `RANDOM_SEED` (the resolved seed belongs to the experiment). It includes simulation geometry/docking radius, counts, probabilities, rates, behavioral intervals and existing replay sampling settings. Nested lists are frozen as tuples and dictionaries as read-only mappings. Canonical JSON can reconstruct a snapshot after globals change.

Runtime UI flags, camera state, render timing and export destinations intentionally remain mutable. Direct low-level component calls retain their legacy live-config defaults outside an experiment context; callers driving those APIs must use `with mission.experiment.activate():`. Full per-object configuration injection across every helper was deliberately avoided. The reproducible creation/update boundary is the simulation factory and Mission, not arbitrary external state edits or every standalone constructor.

## 10. Experiment identity

The experiment hash is SHA-256 of canonical JSON containing the resolved integer seed, RNG scheme version, configuration schema, fixed tick rate and captured settings. Serialization sorts keys, uses fixed separators and rejects non-finite numbers. Reordered setting keys produce the same identity; changing speed or seed changes it; changing render FPS does not.

Identity does not hash source code, dependency versions, external commands, arbitrary Python object state, UI caches or current RNG positions. Source hashes and runtime versions are saved separately. Derived geometry values are captured as configured; the snapshot does not automatically recompute dependent globals or validate every physically sensible parameter combination. Replay import/export formats and restoration architecture were not expanded.

## 11. Production files changed

| File | Step 6 change |
|---|---|
| `core/experiment.py` | New fixed clock, immutable canonical snapshot, experiment identity, owned streams and context-local settings adapter. |
| `core/mission.py` | Clock-backed frame/time, owned weather RNG, update snapshot context and fixed CSV tick cadence. |
| `core/map.py` | Owned world RNG; remove global Python/NumPy seeding; snapshot-aware settings import. |
| `core/drone.py` | Owned initialization/failure streams and snapshot-aware settings import. |
| `core/swarm.py` | Replace gameplay FPS conversions with fixed tick rate; settings import. |
| `main.py` | Factory captures/resolves experiment and accepts a serialized/reconstructed snapshot. |
| `core/battery.py`, `core/communication.py`, `core/geometry.py`, `core/intelligence.py`, `core/analytics.py` | Settings import only, so existing behavior reads the active experiment snapshot. Algorithms/policies are unchanged. |

The analytics import change is necessary to keep its existing distance threshold inside the snapshot. There is no analytics/event architecture change. Reservation code has only its settings import changed; no reservation optimization or collision-policy alteration occurred. UI modules, pathfinding, config.py and every previously approved test file are unchanged.

## 12. Tests added

`tests/experiment_tests.py` adds **29 cases**: seven real-render presentation variants; preservation of global RNG state; fixed elapsed time and pause; FPS-independent relaxation; live-global mutation isolation; canonical round-trip/identity; different-seed worlds; immutable nested snapshot values; reconstruction after globals change; interleaved experiments/context restoration; four domain draw-isolation cases; actual weather/per-agent failure ownership; enabled-failure repeat; planner tie stability; two FPS variants of battery/grace/failure-recovery/reservation timing; zero-tick completion; key-order and seed identity; paused rendering; and two FPS variants of stall-warning timing.

Existing communication grace/recovery, offline discovery, collision wait/backoff, task ownership, motion, docking and A*/Dijkstra tests remain unchanged. They provide the detailed previously approved edge-case coverage; this tranche adds clock/RNG/config boundary tests around them.

## 13. Focused results

**156 passed in 19.66 seconds** with `python -m pytest -q --ignore=tests/gameplay_smoke.py`. The first corrected 13-case set also passed. One subsequently added planner test initially used the wrong `find_path` call signature; that test setup was corrected to the existing API, with no production planner change. Dedicated red logs and final focused results are retained. The only warning is the existing pygame/pkg_resources deprecation.

## 14. Complete suite and smoke

**157 passed in 226.10 seconds**, including the existing 10,800-tick seed-2026 gameplay smoke and forced communication/offline synchronization scenarios. The full-suite output contains:

```text
frames=10800
coverage_start=0.0124
coverage_end=0.5164
survivors_found=4/5
relaunch_succeeded=True
stranded=[]
final_lost_comm=[]
connectivity_min_connected=4/8
connectivity_avg_ratio=0.741
connectivity_majority_ratio=0.997
connectivity_full_collapse_frames=0
coverage_growth_per_min=10.35%
forced_lost_comm={'recovered': True, 'max_lost_streak': 805, 'final_state': 'returning', 'frames_since_contact': 0, 'recovery_label': 'base (timeout)'}
offline_autonomy={'was_offline_autonomous': True, 'offline_cells': 29, 'unsynced_before_reconnect': 29, 'pending_after_sync': 0, 'synced_cells_visible': True, 'comm_mode': 'SYNCING', 'field_charging_violation': False}
offline_survivor={'survivor_idx': 4, 'detected_offline': True, 'global_before_sync': False, 'global_after_sync': True, 'synced_survivors': 1, 'field_charging_violation': False}
```

The previous Step 5 long smoke reported 44.47% coverage, 4/5 survivors, 79.0% average connectivity, 99.8% majority connectivity and zero full collapses. The changed RNG ownership intentionally permits a different trajectory; acceptance thresholds are preserved. Safety/delivery probe counts below cover the three measured 3,600-tick runs, not every tick of the long smoke.

## 15. Presentation-independence matrix

Seed 2026, 300 updates, normal mode, weather interval 30 ticks and failure probability 0.003 per eligible drone-tick. These deliberately active stochastic settings exercise renderer/RNG interference sooner than the standard mission benchmark. They are identical across presentation conditions and stages.

| Presentation condition | FPS setting | Before state / knowledge equal to headless | After state / knowledge / experiment equal to headless |
|---|---|---|---|
| headless | 60 | True / True | True / True / True |
| normal | 60 | False / False | True / True / True |
| normal | 30 | False / False | True / True / True |
| normal | 144 | False / False | True / True / True |
| reduced | 60 | False / False | True / True / True |
| overlays_off | 60 | False / False | True / True / True |
| noisy | 60 | False / False | True / True / True |
| delayed | 60 | False / False | True / True / True |

All final conditions have exactly 5.0 simulation seconds and the same mission summaries. The expanded state digest includes grid, fog/heatmap, global/local/pending knowledge, positions, batteries, drone states, paths/queues, assignments, task/collision counters, communication contact ages, recovery/scan timers, weather/timer and relaxation. The dedicated knowledge hash covers global and local discovery/buffers. Rendering cache state, alert consumption, camera animation and profiling are excluded.

Final matrix state hash: `611cd4ded71b12f9127e85474311d5a44a67b9a09dd2f7753e991731bcc88b84`.

Final matrix knowledge hash: `ced3646a4d46ae193369d52be271dd38c2a0827621d06503d39e39ba7dfd6729`.

Final matrix experiment hash: `859b4326a1372e447488dea1ec58e333c0b2b0e6fb9d090bc59baa7e592d613c`.

## 16. RNG-isolation results

Extra presentation draws (97 Python plus 31 NumPy draws per tick in the noisy matrix condition) leave the final simulation state unchanged. Actual particle/overlay drawing is also included. Domain tests consume 99 extra draws in one named stream and compare samples from all other named streams. An actual Weather pair retains equal transitions despite extra failure-stream/global draws; a different drone's failure stream is untouched. High-probability actual failure runs contain FAILED states and repeat exactly despite presentation draws. Planner paths remain identical after unrelated global/weather RNG consumption.

## 17. Before/after reproducibility

Presentation state mismatches: **7/7 → 0/7**. Knowledge mismatches: **7/7 → 0/7**. Before had no explicit experiment identity; after has one stable identity across all eight conditions. The final 3,600-tick seed-2026 repeat matches **33 non-timing fields**; timing and component latency distributions are excluded. Fresh before runs reproduce all comparable non-timing Step 5 closure fields.

Final established state hash: `f9e960c453c5210473b8f9c6ba0b6b05bcc826792d6c5b601ab9c8c9021b2553`.

Final established knowledge hash: `036b750d4c7e3c68400e6a6a18120819cebe775587a75f9569e198c8be6d2d88`.

Final experiment hash for the normal mission benchmark: `1e62ad727c0ffc67557a631c475b30150f0139cb5647df3a1b919c6238878f9d`.

The matrix configuration intentionally differs from the normal benchmark, so its experiment hash should differ. Hash equality is evidence for the covered state, not a hash of every object or a cross-platform deterministic-numerics guarantee.

## 18. Before/after mission metrics

Fresh sequential normal-mode runs, seeds 2026/2027/2031, 3,600 ticks, offline autonomy enabled and random failures disabled. The same unchanged Step 5 independent communication/contact probes are used in both stages.

| Metric | 2026 before → after | 2027 before → after | 2031 before → after |
|---|---|---|---|
| Coverage % | 23.64 → 25.53 | 27.70 → 28.48 | 24.56 → 21.84 |
| Survivors | 2 → 2 | 2 → 2 | 3 → 3 |
| Average physical connectivity % | 83.72 → 78.43 | 81.43 → 82.08 | 78.08 → 85.50 |
| Majority connected % | 100.00 → 100.00 | 99.31 → 98.03 | 98.11 → 100.00 |
| Full collapse ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Unfinished-task replacements | 0 → 0 | 0 → 0 | 0 → 0 |
| Relay/exploration conflicts | 0 → 0 | 0 → 0 | 0 → 0 |
| Accumulated ownership inconsistencies | 0 → 0 | 0 → 0 | 0 → 0 |
| Stranded drone-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Path searches | 1851 → 2435 | 2214 → 3384 | 3478 → 1038 |
| Frontier completions | 10 → 12 | 13 → 20 | 15 → 10 |
| Actual field point-contact pair-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Disconnected global cell publication | 0 → 0 | 0 → 0 | 0 → 0 |
| Disconnected global survivor publication | 0 → 0 | 0 → 0 | 0 → 0 |

RNG isolation changes initial scatter/batteries, weather and failure streams. World terrain and planner seeding are retained; equal Step 5 and Step 6 trajectories are not required. No task, communication or collision policy was tuned to offset the changed trajectory.

## 19. Step 5 → Step 6 performance

| Seed/stage | Mean ms | p50 ms | p95 ms | p99 ms | Maximum ms |
|---|---|---|---|---|---|
| 2026 Step 5 | 11.929 | 12.648 | 20.309 | 23.594 | 47.565 |
| 2026 Step 6 | 10.316 | 10.733 | 16.011 | 20.098 | 87.474 |
| 2027 Step 5 | 10.227 | 8.973 | 21.152 | 22.772 | 41.000 |
| 2027 Step 6 | 15.703 | 15.572 | 28.433 | 36.219 | 87.147 |
| 2031 Step 5 | 10.425 | 10.112 | 18.422 | 21.539 | 44.290 |
| 2031 Step 6 | 13.129 | 14.070 | 22.920 | 28.269 | 99.132 |

Mean changes: **2026: -13.5% (-1.613 ms), 2027: +53.5% (+5.476 ms), 2031: +25.9% (+2.704 ms)**.

This is fresh same-harness incremental timing, separate from earlier Phase 1/Step 4 overhead. Profiling remains wall-clock `perf_counter` based. Rendering is excluded from mission-update latency; sensor/sync and component instrumentation are included, as in Step 5. Fresh timed simulations run sequentially after the full tests, without concurrent test processes. Earlier exploratory before-run timings overlapped focused validation and are retained separately, not used in this table.

The context-local settings adapter adds lookups in simulation hot paths; the new RNG layout also changes workloads and path searches. Single runs per seed do not isolate these causes or establish a statistically robust overhead estimate. No unrelated system or reservation performance was optimized. Raw component timings remain in the JSON results.

## 20. Intentional behavior changes

Elapsed mission time and per-second policy conversions now use simulation ticks. Render FPS no longer changes policy seconds. Global config mutation does not change an existing factory-created mission during update. Map creation no longer reseeds caller RNGs. Weather, failures and initialization no longer share each other's or presentation's draw stream. Unspecified seeds use OS entropy and are recorded. Invalid non-integer seeds are rejected. These changes intentionally break trajectory equality with older releases while establishing repeatability under the final implementation.

## 21. Remaining confirmed limitations

Real-time throughput remains coupled to the application's one-update-per-loop pacing; equal wall-clock duration is not equal simulated duration at different FPS. Snapshot activation is a factory/update boundary; standalone component manipulation outside its context reads global config. This is a documented compatibility boundary, not complete per-object dependency injection. Arbitrary external state changes and interactive rescue commands must be repeated as identical tick-indexed inputs for reproducibility.

The experiment hash is not a code/version hash and does not include every initial object or intervention. Configuration capture does not add exhaustive range/dependency validation. Presentation still uses a global RNG, so visual animations themselves are not required to repeat. No independent NumPy simulation generator is installed for hypothetical future stochastic code. Replay still does not restore full configuration, local buffers or RNG state; no deterministic replay/resume claim is made.

## 22. Remaining unverified risks

Cross-Python/Pygame/NumPy versions, platforms and floating-point implementations have not been exhaustively compared. The selected seeds, horizons and failure fixtures do not prove behavior for every configuration, fleet size or stochastic history. Context isolation is tested for sequential interleaving and exception restoration, not simultaneous mutation of shared simulation objects across threads. Adding future simulation code that bypasses the settings adapter or consumes module-global randomness could violate the contract and should receive a regression. Prior point-agent/deadlock and abstract-radio limitations remain unchanged.

## 23. Git diff summary

The repository already contained approved uncommitted Steps 1–5. This table compares against the frozen Step 5 snapshot, not original Git HEAD:

| File | Added | Removed |
|---|---|---|
| core/analytics.py | 1 | 1 |
| core/battery.py | 1 | 1 |
| core/communication.py | 1 | 1 |
| core/drone.py | 7 | 5 |
| core/geometry.py | 1 | 1 |
| core/intelligence.py | 1 | 1 |
| core/map.py | 9 | 11 |
| core/mission.py | 24 | 11 |
| core/swarm.py | 6 | 6 |
| main.py | 10 | 8 |
| core/experiment.py | 125 | 0 |
| tests/experiment_tests.py | 230 | 0 |
| benchmarks/step6.py | 143 | 0 |

Scoped production/test/harness total: **559 additions and 46 deletions across 13 files**. The new report and validation artifacts are additional files. Source hashes verify every previously approved test, config.py, pathfinding and UI source is preserved. Geometry/reservation/communication policy files change only their configuration import where indicated. `git diff --check` passes. No commit, push or PR was created.

## 24. Accurate reproducibility claims

For the supported runtime and normal factory/update path, equal captured settings, resolved seed, update count and external interventions reproduce the tested behavioral state independently of actual renderer calls, presentation FPS settings, overlays, reduced/delayed rendering and unrelated presentation random draws. Mission elapsed time is simulated time. Named PRNG ownership and canonical experiment identity make the tested experiments inspectable and reproducible.

ADSS cannot yet claim universal cross-platform bitwise determinism, deterministic replay restoration, equal real-time progression across rendering rates, statistically independent random streams, universal collision freedom or realistic network simulation. All zero-contact/publication and mismatch counts are scoped to the documented tests and runs.

## 25. Recommendation and stop boundary

The original roadmap's next tranche is **Step 7 — P0/P4: Replay and persistence correctness**. Recommend beginning with versioned self-contained scenario/configuration metadata, playback pacing and isolation from live state, schema validation, and output-collision/atomic-write regressions. The new seed/config identity and clock provide useful foundations. This report does not implement replay, event architecture or additional roadmap work. **Step 6 is complete; Step 7 has not begun. Stop pending approval.**

## Evidence and reproduction

`benchmarks/results/step6/` contains the unchanged-source red evidence, focused/full test logs, fresh `before.json`, `after.json`, `repeat.json`, presentation matrices, source hashes and `reproducibility_check.json`. Checkpoints are not additional independent trials. The frozen Step 5 source and scoped `step6_only.diff` are under `local evidence directory`.

Commands: `python -m pytest -q -s`; `python benchmarks/step6.py --output benchmarks/results/step6/after.json`; repeat with `--seeds 2026`; matrix with `--matrix --ticks 300 --seeds 2026`. Use the same harness in the frozen source tree for before measurements. Runtime: Python 3.13.7, pygame 2.6.1, existing Windows host. Canonical benchmark configuration is included in final JSON results.
