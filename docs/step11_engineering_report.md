# Step 11 engineering closure — measured optimization with exact equivalence

Evidence closed: 2026-09-30. Source and validation details are linked below.

## 1. Executive summary

Step 11 is complete with one production optimization: a bounded per-drone cache of the **pure route-energy geometry/drain calculation**. Policy assessments, feasibility decisions, diagnostics, accounting, route generation and RNG consumption still execute.

All three 3,600-tick seeds match frozen Step 10 at every tick in the differential projection, with exact detailed checkpoint, final state, event, RNG, replay and CSV equality. The final suite passed **302 tests** (277 preserved + 25 new), including the 10,800-tick smoke. The repeated seed and all seven presentation conditions match.

Fresh paired clean runs show mean update time reductions of **49.9%, 47.8%, and 38.8%** for seeds 2026/2027/2031. p95 and p99 decreased in all three; maximum latency increased in all three. These are sequential single-pair observations, not a statistical guarantee or proof that every timing difference was caused by the cache. No second optimization was added. Step 12 has not begun.

## 2. Frozen Step 10 baseline

The exact baseline is retained privately; see [archived baseline provenance](evidence/README.md#private-baselines). Its 47 captured source/test/harness files were copied and SHA-256 hashed before production changes. The Step 10 report, benchmark evidence and 277-test result were preserved there. The current Step 11 validation manifest contains 49 source/test/harness files.

Closure independently verified all 47 frozen hashes and all 49 current validated hashes. Of the 47 original paths, only `core/energy.py` differs in the current tree. All previous test files, configuration and other production files match. Frozen profile results and fresh clean baselines also match the approved Step 10 authoritative final results.

Evidence is separate under [benchmarks/results/step11](evidence/step11/). The saved initial `git_status.txt` and `git_diff.txt` preserve the pre-Step-11 working-tree state. Prior work remains uncommitted; no commit, push, reset or discard was performed.

## 3. Profiling and timing methodology

Python 3.13.7 on the same Windows workspace; standard eight-drone configuration, offline autonomy enabled, hardware failures disabled for the main three-seed comparison, 3,600 fixed simulation ticks per run. Configuration/experiment identity matches between each baseline and candidate.

cProfile and targeted wrappers sample the first 120 updates of every 600-update block: **720 profiled ticks distributed across each 3,600-tick run**. They measure inclusive/self time, calls, assessment callers, existing route-cache activity and repeated pure costs. These are representative samples, not exhaustive whole-run CPU totals. Nested cumulative times overlap and must not be summed. `perf_counter`/cProfile timings are subject to host scheduling.

Clean runs have no profiler or internal operation-count wrappers. Only `mission.update()` is timed. Hashing, inspection, JSON construction and checkpoint serialization occur outside the timer. Existing in-update CSV/replay work remains included. Before/candidate/profile/test jobs run sequentially; clean timing did not overlap those jobs. Construction and rendering are excluded. Untimed inspection can still affect cache locality; the same harness is used on both versions.

Historical Step 10 latency, sampled profiler time and the fresh clean runs are different methodologies. Performance claims below use **only fresh clean Step 10 versus clean Step 11**. The existing saved runs were reused at closure, not repeated.

## 4. Initial whole-simulation profile

| Seed | Sampled ticks | Total self seconds | Energy estimate cumulative s | Pure route-energy cumulative s |
| --- | --- | --- | --- | --- |
| 2026 | 720 | 91.521 | 66.969 | 55.243 |
| 2027 | 720 | 158.204 | 121.379 | 101.386 |
| 2031 | 720 | 55.702 | 35.962 | 28.581 |

The dominant measured issue was repeatedly evaluating the geometry of routes already known to the existing route cache. The 182,857–711,189 full-run energy assessments remain necessary under approved policy; their expensive repeated inner calculation was the selected target.

## 5. Top cumulative-time functions

| Function (sampled seed 2026) | Calls | Cumulative seconds |
| --- | --- | --- |
| experiment.py:112:bound | 720 | 91.570 |
| mission.py:190:update | 720 | 91.555 |
| swarm.py:927:update | 720 | 90.699 |
| step11.py:77:estimate | 65,018 | 67.327 |
| energy.py:101:estimate | 65,018 | 66.969 |
| drone.py:306:can_accept_task | 62,405 | 66.446 |
| step11.py:97:cost | 190,832 | 56.034 |
| energy.py:33:route_energy | 190,832 | 55.243 |
| swarm.py:802:_negotiate_frontiers | 1,208 | 44.470 |
| geometry.py:66:segment_is_clear | 1,840,265 | 40.422 |
| swarm.py:453:_comm_risk_limit | 30,528 | 32.914 |
| swarm.py:323:_assign_nearest_sector | 1,553 | 32.522 |
| geometry.py:27:swept_cells | 990,467 | 28.075 |

Full cumulative rankings and callers for every seed are saved in `before_profile/profile_<seed>.json` and the raw `.prof` files. Wrapper, parent and child rows overlap. In particular negotiation includes many energy assessments.

## 6. Top self-time functions

| Function (sampled seed 2026) | Calls | Self seconds |
| --- | --- | --- |
| geometry.py:66:segment_is_clear | 1,840,265 | 10.816 |
| map.py:220:is_passable | 12,903,997 | 5.771 |
| experiment.py:101:__getattr__ | 16,161,588 | 4.857 |
| ~:0:&lt;built-in method builtins.__build_class__&gt; | 990,467 | 4.689 |
| ~:0:&lt;built-in method builtins.all&gt; | 5,576,479 | 4.650 |
| geometry.py:76:clear | 11,847,452 | 4.474 |
| geometry.py:86:endpoint_clear | 3,680,530 | 3.245 |
| energy.py:33:route_energy | 190,832 | 3.053 |
| map.py:217:in_bounds | 20,933,586 | 2.926 |
| geometry.py:32:is_passable | 7,818,918 | 2.590 |

High-frequency geometry, passability, configuration reads and temporary class creation dominate self time. Low-frequency route searches are individually costly, but their aggregate sampled cost is substantially below repeated route-energy geometry. Call frequency alone was not used to select the optimization.

## 7. Energy-assessment caller breakdown

| Seed | Direct caller ← caller | Calls (both) | Before s | After s | Route searches (both) |
| --- | --- | --- | --- | --- | --- |
| 2026 | can_accept_task &lt;- _comm_risk_limit | 30,528 | 32.599 | 6.732 | 142 |
| 2026 | can_accept_task &lt;- evaluate_frontier_bid | 20,923 | 17.937 | 3.546 | 166 |
| 2026 | can_accept_task &lt;- energy_feasible | 10,040 | 14.796 | 3.845 | 163 |
| 2026 | has_safe_return_energy &lt;- _maintain_relay_anchors | 1,234 | 0.240 | 0.099 | 0 |
| 2026 | has_safe_return_energy &lt;- update | 543 | 0.405 | 0.370 | 94 |
| 2026 | can_accept_task &lt;- _tick_scanning | 590 | 0.438 | 0.310 | 155 |
| 2027 | can_accept_task &lt;- _comm_risk_limit | 49,324 | 58.106 | 9.746 | 188 |
| 2027 | can_accept_task &lt;- evaluate_frontier_bid | 33,401 | 33.573 | 6.656 | 372 |
| 2027 | can_accept_task &lt;- energy_feasible | 17,204 | 27.819 | 5.682 | 242 |
| 2027 | has_safe_return_energy &lt;- _maintain_relay_anchors | 1,200 | 0.255 | 0.100 | 0 |
| 2027 | has_safe_return_energy &lt;- update | 812 | 0.542 | 0.395 | 113 |
| 2027 | can_accept_task &lt;- _tick_scanning | 910 | 0.793 | 0.547 | 315 |
| 2031 | can_accept_task &lt;- _comm_risk_limit | 15,258 | 17.015 | 7.089 | 117 |
| 2031 | can_accept_task &lt;- evaluate_frontier_bid | 10,882 | 9.745 | 3.740 | 114 |
| 2031 | can_accept_task &lt;- energy_feasible | 5,110 | 8.039 | 4.472 | 123 |
| 2031 | has_safe_return_energy &lt;- _maintain_relay_anchors | 1,190 | 0.211 | 0.179 | 0 |
| 2031 | has_safe_return_energy &lt;- update | 628 | 0.416 | 0.536 | 58 |
| 2031 | can_accept_task &lt;- _tick_scanning | 700 | 0.567 | 0.689 | 201 |

Communication-risk checks, frontier bids and sector evaluation account for the largest repeated work. Full caller dictionaries include allocation, offline continuation, recovery and relay paths. Every sampled caller's assessment count and route-search delta match before/after. Seed 2027 also had 260 diagnostic `estimate_task_energy ← task_energy_reason` calls (0.218 s before, zero route searches); diagnostic queries were not the main slowdown. Repeated results were observed directly, not inferred solely from these call counts.

## 8. Energy route-search and cache analysis

| Seed | Route lookups | Existing route hits | Existing route misses | Before repeated cost results | New cost reuse | Raw cost evaluations after | Effective reuse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026 | 190104 | 189302 | 802 | 188491 | 188996 | 1836 | 99.04% |
| 2027 | 289293 | 288034 | 1259 | 286799 | 287720 | 2471 | 99.15% |
| 2031 | 80688 | 80038 | 650 | 79111 | 79437 | 1299 | 98.39% |

All numbers above are from the same 720-tick profiling windows. Existing route-cache hit/miss counts are unchanged. The “before repeated” diagnostic used a separate 4,096-entry observation window; it is not the new production cache.

New cost reuse is `_route_cost` calls minus actual `route_energy` calls on these standard-Map runs. Miss counts include any uncached pure queries; they are not necessarily insertions. No custom-map bypass occurs in these workloads. Effective reuse is 99.04%, 99.15% and 98.39% respectively. Cache eviction totals were **not recorded**; the focused capacity test verifies the 1,024 bound. No eviction count is invented. There were no sampled terrain-route invalidations or uncached pure-query route searches reported by the probe (absence is limited to these windows). Weather is in the cost key, rather than forcing unrelated entries to be removed.

## 9. Pathfinding analysis

| Seed | Sampled A* calls, both | A* before s | A* after s | Smoothing calls, both |
| --- | --- | --- | --- | --- |
| 2026 | 935 | 4.974 | 5.938 | 935 |
| 2027 | 1433 | 7.443 | 8.423 | 1433 |
| 2031 | 800 | 3.492 | 6.954 | 795 |

The existing route cache already avoids most repeated route generation. A* cost, heuristic, tie-breaking, smoothing and planner calls are untouched. Full-run counted planner searches remain 5,331 / 6,455 / 3,400. Those are the established accounting-hook counts; the profile separately counts actual A* calls in its windows. We do not present sampled calls as an exhaustive count of every uncounted query outside those windows.

## 10. Reservation analysis

| Seed | Rebuilds in sample, both | Before cumulative s | After cumulative s | Gate calls in sample, both |
| --- | --- | --- | --- | --- |
| 2026 | 1440 | 10.010 | 11.995 | 4095 |
| 2027 | 1440 | 11.217 | 12.514 | 3583 |
| 2031 | 1440 | 10.324 | 20.500 | 4255 |

Two reservation rebuilds per update remain, with the same horizon, contents, geometry, stationary occupancy, priority and docking rules. Reservation construction is a meaningful remaining cost; no reservation optimization was attempted. The higher measured time for unchanged rebuild code, particularly seed 2031, demonstrates timing variability rather than a semantic change. Complete reservation contents and recovery internals are included in differential hashes/checkpoints.

## 11. Allocation and negotiation analysis

| Seed | Negotiation calls, both | Before s | After s | Frontier-work calls, both |
| --- | --- | --- | --- | --- |
| 2026 | 1208 | 44.470 | 17.043 | 40812 |
| 2027 | 1208 | 82.994 | 29.900 | 65960 |
| 2031 | 1089 | 23.725 | 17.485 | 20251 |

Allocation still evaluates the same candidates in the same order, with the same bids, winners, ownership lifecycle and forced-negotiation behavior. It benefits indirectly when its repeated pure energy calculations hit the cache. Frontier-work construction remains expensive; no candidate pruning, cadence changes or allocation-result cache was added.

## 12. Communication, analytics and persistence analysis

| Sampled operation, before | 2026 s | 2027 s | 2031 s |
| --- | --- | --- | --- |
| Accounting emission | 0.179 | 0.111 | 0.210 |
| Analytics observation | 0.163 | 0.187 | 0.172 |
| Analytics sampling | 0.124 | 0.139 | 0.139 |
| Replay sampling | 0.426 | 0.471 | 0.438 |
| CSV write | 0.108 | 0.122 | 0.137 |

Radio graph refresh used 0.183 / 0.201 / 0.225 cumulative seconds in these windows (1,440 calls per seed). CSV performed 12 writes, replay 120 snapshots, and analytics 840 samples. Energy-estimate diagnostic serialization used 0.983 / 1.876 / 0.593 seconds, still much less than geometry. No delivery, sampling, retention, serialization or export semantics were changed. These systems were not selected for optimization.

## 13. Confirmed bottlenecks

The dominant removable duplication was pure route-energy computation after a route-cache hit. For seed 2026 it used 55.243 of 91.521 sampled self-total seconds, with 188,491 repeated inputs/results observed. Seed 2027 magnified this cost through more communication-risk/frontier/sector checks.

Secondary costs include reservation geometry/record creation, frontier-work construction, existing route-cache context/key work and A*. Dynamic context reads and temporary allocations are visible in the self profile. These findings explain the new energy-related cost without claiming a controlled causal decomposition of every historical Step 9 → Step 10 timing difference.

## 14. Candidate optimizations considered

| Candidate | Evidence/opportunity | Risk/complexity | Disposition |
| --- | --- | --- | --- |
| Pure route-energy memoization | Dominant repeated computation | Small; complete input/context key required | Implemented |
| Additional route/A* reuse | Existing route cache already ~99% hits in samples | Tie-breaking/route-history sensitivity | Deferred |
| Reservation derived-data reuse | 10–11 s sampled before at eight drones | Large occupancy/invalidation surface | Deferred |
| Frontier-work reuse | 20k–66k sampled calls | Mutable knowledge/ownership inputs | Deferred |
| Fewer energy/negotiation checks | Large call count | Changes approved decisions/events | Rejected |
| Trim diagnostics, replay or CSV | Small relative cost | Violates semantics | Rejected |

## 15. Candidates rejected or deferred and why

Only one optimization was needed for a material measured reduction. Reducing policy cadence, reservation horizons, planner quality or event work would violate equivalence. Caching feasibility/assignment outcomes would require more volatile inputs and could suppress established side effects; it was unnecessary. Secondary-system optimizations would expand the validation surface and are left for separate approval. No global configuration-proxy, geometry-helper or pathfinding refactor was made.

## 16. Optimization 1 implementation

`EnergyPolicy._route_cost` reuses the exact float returned by the unchanged `route_energy` function. Three existing cost call sites route through it. Each drone owns an `OrderedDict`, bounded at **1,024 results**, evicted FIFO; hits do not reorder entries. A context change clears it on a recording assessment. No cache is shared between agents or missions.

The computation uses the same arithmetic in the same order on a miss. No numerical approximation or alternative route calculation is introduced. Standard `Map` geometry is required; subclasses or overridden geometry methods fall back to the original calculation. Production contains no new profiling wrappers or hit counters.

## 17. Optimization 1 correctness contract

The cached value is route movement charge, not a task/energy-policy/accounting/allocation decision. Exact start coordinates, ordered route cells, activity and weather identify a result inside a validated map/configuration context. Identical inputs return the previously computed exact result, including an unreachable infinite cost.

Assessment still performs route selection/lookups, work/reserve/uncertainty arithmetic, battery comparisons, counter increments, latest-decision diagnostics and caller behavior. Active paths and sidesteps contribute their actual selected geometry. Custom geometry bypasses memoization. Query mode may read a valid cached value but cannot populate, clear, reorder or otherwise mutate the cache. No RNG is used by the cache.

## 18. Optimization 1 performance result

| Seed | Pure geometry calls before → after (sample) | Pure geometry cumulative s before → after | Cache wrapper cumulative s after | Clean mean reduction |
| --- | --- | --- | --- | --- |
| 2026 | 190,832 → 1,836 | 55.243 → 0.559 | 3.066 | 49.9% |
| 2027 | 290,191 → 2,471 | 101.386 → 0.803 | 4.785 | 47.8% |
| 2031 | 80,736 → 1,299 | 28.581 → 0.708 | 2.895 | 38.8% |

Profiler call reduction directly establishes eliminated repeated computation. Clean timing independently shows a material mean/p95/p99 improvement for each main seed. It does not establish that the cache caused every observed wall-time difference. Maxima and one median worsened; see sections 38–39.

## 19. Optimization 2 implementation

Not implemented. Optimization 1 met the measured-improvement objective while preserving exact tested behavior.

## 20. Optimization 2 correctness contract

Not applicable; there is no second production optimization or second cache to validate.

## 21. Optimization 2 performance result

Not applicable. Secondary costs are documented, not silently optimized.

## 22. Cache contract and invalidation rules

| Input/lifetime | Treatment |
| --- | --- |
| Exact pixel start; ordered route geometry | Key; no rounding, sorting or simplification |
| Activity and weather | Key; execution-state drain and storm behavior remain distinct |
| Map identity, rows/cols, grid shape/dtype/content | Context; direct terrain edits detected through exact grid bytes |
| Obstacle/no-fly/wind cell constants | Context |
| Cell size, normal/wind speed | Context |
| Move/scan/idle drain and storm extra drain | Context |
| route_energy, segment_is_clear, swept_cells, Battery.drain_per_tick | Function identities in context |
| Map geometry implementation | Exact standard Map and original method identities required; otherwise bypass |
| Battery, reserve, work duration, uncertainty | Not cached; recomputed by estimate every query/assessment |
| Planner settings, agent, reservations, path/sidestep | Route selection still executes; resulting ordered geometry enters key |
| Across ticks | Retained until relevant context change or FIFO eviction |
| Across drones/missions | Never shared; constructor creates empty cache |
| Capacity | 1,024 entries per drone; entry size depends on route length |
| Pure query | Read-only hit or uncached calculation; no invalidation/insertion/reordering |
| Diagnostics/RNG | No cache diagnostic side effects or random draws |

Context is validated on each access, so mutation checks are not avoided for speed. Tests exercise changed terrain/wind/no-fly cells, bounds/dtype, geometry, speeds, rates, weather/activity, experiment/world context, battery/reserve/work/uncertainty, active path and sidestep. The contract assumes the existing pure calculation and standard Map methods; it is not a mechanism for detecting every possible hidden input of arbitrary monkeypatched Python code.

## 23. Production files changed

**Only `core/energy.py`** relative to frozen Step 10: imports the standard Map model, records original geometry method identities, allocates the per-policy cost cache, implements `_route_cost`, and redirects three pure cost calls. Scoped change: **44 additions / 3 deletions**. No configuration, policy, UI, RNG, clock, planner, collision, communication, accounting or replay production file changed.

## 24. Tests added

`tests/performance_tests.py` adds **25 collected cases**:

- Exact first-field/event divergence detection and detached checkpoint projection (2).
- Repeated geometry reuse while assessment/search/accounting semantics remain intact (1).
- Sixteen parameterized numeric/geometry/context invalidation cases (16).
- Pure-query cache immutability; battery/reserve/work/uncertainty reevaluation; bounded agent-local storage; custom-geometry bypass; world/experiment isolation; changed path and active sidestep (6).

The uncached implementation reproduced repeated geometry calls before optimization (`optimization_red.txt`). A separate harness-only live battery-dictionary reference defect was reproduced (`harness_red.txt`) and corrected by detached projection; it did not change simulation behavior. Existing Steps 1–10 tests and thresholds are byte-identical to the frozen baseline.

## 25. Differential-equivalence harness

[benchmarks/step11.py](../benchmarks/step11.py) records **15 authoritative groups at every tick, including tick zero**, and full detached state every 300 ticks. Main runs therefore compare 3,601 tick states and 13 detailed checkpoints each.

Groups cover each drone's position/velocity/state/battery/path/index/queue/tasks/relay/knowledge/energy diagnostics; world grid and survivor truth; global fog/heatmap/discoveries/weather; swarm frontier/sector ownership; accounting/metrics/final summary/outcome; simulation and agent RNG streams; experiment identity; additional scalar timers and battery/radio internals; reservation contents and collision/recovery state. Derived cache contents are deliberately excluded: they are the optimization, not authoritative policy state.

Final sampled replay payload and CSV byte hashes are compared independently. Comparison is exact, with no floating tolerance. This is a diagnostic projection and hash chain, not checkpoint restoration or a proof covering arbitrary future state additions. Instrumentation stays outside clean update timing.

## 26. First-divergence testing behavior

The harness aborts at the first unequal tick/group and saves the candidate's raw state. `--dump-tick N` produces the frozen baseline at that exact tick; recursive `first_difference` identifies the first differing field/event without tolerance.

An intentionally corrupted reference `drone_0` hash at **tick 30** caused exactly that first divergence and the expected failing process exit. Baseline and candidate raw dumps at tick 30 were equal, confirming this was an injected reference fault. A focused nested-event payload fixture catches a difference of approximately 1e-15. No actual candidate-versus-baseline divergence occurred in accepted runs.

## 27. Three-seed exact-equivalence results

| Seed | Per-tick group hashes checked | Detailed checkpoints | Final groups | Replay | CSV | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 3,601 × 15 | 13 | 9 | exact | exact | PASS |
| 2027 | 3,601 × 15 | 13 | 9 | exact | exact | PASS |
| 2031 | 3,601 × 15 | 13 | 9 | exact | exact | PASS |

All intermediate and final covered fields match. Closure reread and compared the saved traces and raw checkpoints independently of the run-time reference checks. The repeated 2026 run also matches all non-timing clean-result fields, every tick hash and every checkpoint. No policy mismatch was accepted as “close enough.”

## 28. Accounting and event-hash equivalence

| Seed | Lifetime events, both | Event hash, both |
| --- | --- | --- |
| 2026 | 18851 | `1bf33781d03106b644e74723a6cdcd7ebd811802f59f5a3a733ff5756c9edd88` |
| 2027 | 7820 | `d7a7564d5d292b565d7249839dfcaff1508d84d79dc3a5c3cffec2386c25cd53` |
| 2031 | 22602 | `db68c1c803601646d3294b05190fb156f9405d12b4c0753df8fd4021f2a376e7` |

Counts, chained event hash, event-derived metrics and summaries match throughout the traces. The chain covers event ordering, payload, tick and lifetime sequence, including records outside bounded retention. Retention remains 4,096 records, queries remain pure, and no cache hits suppress assessments or events. Event hashes are verification evidence, not a reconstruction log.

## 29. RNG equivalence

| Seed | Final simulation/agent RNG hash, both |
| --- | --- |
| 2026 | `843b1c9bc6e37db173e33a494add41e8ce5cd3d092f0ab19879264bdcf8e8221` |
| 2027 | `ad5ee39c8f3ba4e52597dfcfb9189d387de2c1b423351ec8f7595cf39c442d4a` |
| 2031 | `f1baada88b4fbba8b2929eed249844ee20d7088da4dabca66eb7299748189a6b` |

Full RNG states also match at detailed checkpoints and their group hashes at every tick. No new random source, draw, unordered RNG-dependent iteration or presentation interaction was introduced.

## 30. Energy-policy equivalence

| Seed | Assessments | Infeasible assessments | Energy route searches | Energy returns | Charge starts/completions | Actual relaunches |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 246605 | 53 | 4562 | 1 | 13/13 | 11 |
| 2027 | 711189 | 13829 | 5596 | 1 | 16/16 | 14 |
| 2031 | 182857 | 1355 | 2650 | 0 | 4/4 | 4 |

Each value is identical before/after. Estimated components, margin, latest reason, readiness, batteries and selected paths match as well. Reserve, uncertainty, drain, work overhead, reassessment cadence and controlled return policy are unchanged. The modeled avoidable-stranding fixture remains a preserved Step 10 test; no broader guarantee of energy safety is introduced.

## 31. Collision and reservation equivalence

| Seed | Rejected proposals / waits (both) | Backoff attempts / initiated | Exhausted | Measured field contacts |
| --- | --- | --- | --- | --- |
| 2026 | 6554/6554 | 1/1 | 0 | 0 |
| 2027 | 452/452 | 1/1 | 0 | 0 |
| 2031 | 9408/9408 | 3/3 | 0 | 0 |

Reservation contents, moving/stationary occupancy, waits, active recovery state and deterministic decisions match. Point-contact fixtures and docking exceptions pass unchanged. Zero observed contacts does not imply finite-radius safety, deadlock freedom or MAPF completeness. Proximity episodes remain a separate metric.

## 32. Communication and knowledge equivalence

| Seed | Partitions | Reconnects | LOST_COMM entries | Global survivors | Knowledge hash, both |
| --- | --- | --- | --- | --- | --- |
| 2026 | 56 | 53 | 4 | 2 | `17f4fc00652849f95e2c386b2b873a12ce18cbc83ca93e6d43b88e24a688c8ce` |
| 2027 | 57 | 55 | 9 | 2 | `d1f447421c08207af06bd3702e9de962188268015a78406ecab92a345298e913` |
| 2031 | 75 | 73 | 7 | 3 | `7a9cc4a94921b66f394acfbdfd2f790b1af242fa99a65f368b19a074a586155b` |

Radio state, pending/private observations, synchronization state and global knowledge match per tick; all Step 5 tests pass. Historical Step 10 independent probes recorded zero disconnected global publication, ownership inconsistencies, relay/task conflicts and unnecessary unfinished replacements. The fresh baseline matches their authoritative final result and Step 11 matches the fresh baseline at every tick. Those independent probe counts were not newly instrumented during clean Step 11 timing; preservation is supported by exact trajectories/state plus the unchanged contracts and regression suite, not fabricated new probe measurements.

## 33. Replay and persistence equivalence

For each full three-seed run, the **entire sampled replay payload hash and CSV byte hash match** frozen Step 10; seed 2026 repeat and scaling pairs also match. Optional accounting/energy extensions, sample cadence, embedded world/private knowledge and experiment identity are preserved. Detached playback, incompatible/corrupt-file rejection, unique/atomic outputs and no automatic live resume pass the existing suite. There is no checkpoint or deterministic-continuation feature.

Exact replay/CSV hashes are stored in `closure_analysis.json`. File names and storage locations can legitimately differ under unique-output semantics; content comparison does not treat the name as simulation state.

## 34. Headless and rendering equivalence

| Condition | Presentation FPS setting | Ticks | Result |
| --- | --- | --- | --- |
| headless | 60 | 180 | all 9 final groups exact |
| normal | 60 | 180 | all 9 final groups exact |
| normal | 30 | 180 | all 9 final groups exact |
| normal | 144 | 180 | all 9 final groups exact |
| reduced | 60 | 180 | all 9 final groups exact |
| overlays_off | 60 | 180 | all 9 final groups exact |
| noisy | 60 | 180 | all 9 final groups exact |

The existing seven-condition harness asserts authoritative state before/after each render. It exercises the supported core factory, graphical compatibility factory, 30/60/144 FPS settings, one draw per seven updates, hidden overlays/dashboard/minimap and unrelated Python/NumPy presentation draws. Each condition had three hardware failures and six weather changes; all match the Step 10 matrix too.

The matrix is display-backed rendering at equal ticks, without an FPS sleep; it validates presentation independence rather than monitor/frame-pacing performance. Headless tests prohibit graphical initialization, Surface/presentation Clock creation, input and UI imports. Core render-capable modules may still import Pygame. We claim no graphical initialization is required, not zero Pygame imports.

## 35. Focused test results

The saved focused run passed **53 checks**: 25 Step 11 cases plus 28 route-energy regressions. The initial 60-tick exact differential passed before full runs. Red/green logs are preserved. Final closure did not rerun these completed checks because the validated production/test/harness hashes still match.

## 36. Complete test-suite result

**302 passed, 1 warning, 1,255.63 seconds (20:55)** in the saved final run. The warning is Pygame's dependency use of deprecated `pkg_resources`; it is not a failed assertion. All 277 Steps 1–10 tests remain present and unchanged, including movement, A*, ownership, collision, communications, experiment isolation, replay, accounting, headless operation and energy policy.

[full_final.txt](evidence/step11/full_final.txt) contains the complete result and captured smoke output. `jobs_complete.json` confirms completion and source verification; closure independently reverified the same hashes. No repeat of this expensive suite was necessary.

## 37. 10,800-tick gameplay smoke

The smoke was part of the final suite and passed at seed 2026:

- Coverage: **1.24% → 50.49%**; five of five survivors discovered.
- Actual relaunch succeeded; no stranded drones, empty-battery return stalls or final LOST_COMM drones.
- Average connectivity **0.787**, majority-connected fraction **0.999**, zero full-collapse frames.
- Forced LOST_COMM recovered; longest forced recovery streak 827 ticks.
- Offline map fixture: 29 local cells, 29 pending before reconnect, zero pending afterward, synchronized cells visible.
- Offline survivor remained private before reconnect and globally visible afterward; one synchronized report.
- No field-charging violation; zero emergency recoveries.

These match the approved Step 10 smoke outcomes. The smoke is additional long-horizon acceptance coverage, not a second 10,800-tick per-tick frozen-baseline differential run.

## 38. Step 10 → Step 11 clean update performance

| Seed | Version | Mean ms | p50 ms | p95 ms | p99 ms | Maximum ms |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | Step 10 | 40.659 | 21.577 | 91.843 | 139.510 | 601.061 |
| 2026 | Step 11 | 20.363 | 17.216 | 37.636 | 92.109 | 823.526 |
| 2027 | Step 10 | 105.045 | 107.613 | 227.072 | 327.168 | 707.580 |
| 2027 | Step 11 | 54.840 | 50.017 | 122.347 | 259.550 | 1,425.107 |
| 2031 | Step 10 | 33.091 | 10.434 | 84.434 | 119.191 | 595.397 |
| 2031 | Step 11 | 20.260 | 12.336 | 41.963 | 73.630 | 827.810 |

These are fresh sequential 3,600-update runs with the same non-profiled timing boundaries. They include normal in-update persistence and exclude rendering/inspection. Mean reductions are 49.9%, 47.8%, 38.8%; the equal-horizon aggregate mean is lower as well. There is one baseline/candidate timing pair per seed, plus the candidate 2026 repeat. No confidence interval or universal speedup is claimed. The earlier Step 10 37.064/95.267/27.282 ms means used different measurement instrumentation and are not the denominators here.

## 39. p95, p99 and maximum-latency analysis

All three p95 and p99 values decreased. Maxima rose from 601.061 → 823.526 ms, 707.580 → 1,425.107 ms, and 595.397 → 827.810 ms. Seed 2031's median increased from 10.434 → 12.336 ms despite lower mean/tails. The cache therefore does **not** establish a uniform latency improvement or bounded worst-case latency.

Candidate seed 2026 repeat: mean **23.003 ms**, p50 20.607, p95 40.604, p99 86.324, max 887.491. Behavior is exactly equal despite timing variation.

Miss/context-validation overhead, cold routes, large allocation work and host scheduling can affect tails; this evidence does not isolate their individual causes. Unchanged reservation code's sampled time also varied substantially. Profiling supports elimination of repeated cost computation, but does not justify attributing all clean wall-time differences to the cache. Average 60 Hz real-time performance is not reached on these runs.

## 40. Operation-count and mission comparison

| Metric: Step 10 = Step 11 | 2026 | 2027 | 2031 |
| --- | --- | --- | --- |
| Coverage % | 27.574 | 26.891 | 23.322 |
| Survivors globally published | 2 | 2 | 3 |
| Task awards | 35 | 32 | 24 |
| Task completions | 13 | 17 | 8 |
| Task cancellations | 16 | 10 | 9 |
| Counted path searches | 5331 | 6455 | 3400 |
| Energy assessments | 246605 | 711189 | 182857 |
| Energy route searches | 4562 | 5596 | 2650 |
| Collision waits | 6554 | 452 | 9408 |
| Charging starts | 13 | 16 | 4 |
| Charging completions | 13 | 16 | 4 |
| Relaunches | 11 | 14 | 4 |
| Stranded transitions | 0 | 0 | 0 |
| Battery consumed, abstract units | 337.273 | 353.456 | 315.503 |
| Battery recharged, abstract units | 271.063 | 313.165 | 127.368 |
| Outcome | running | running | running |

Sampled existing route lookups/hits/misses, assessment caller counts/searches, A* calls, negotiation calls, candidate feasibility calls, reservation rebuilds and gate calls also match; see sections 7–11. Pure route-energy computation counts alone drop as intended. Internal cost-cache metrics are measured in profiler windows only; no debug counters were inserted into clean updates.

Historical independent full-run Step 10 probes recorded average connectivity 85.344% / 80.955% / 80.913%, majority connectivity 99.889% / 91.750% / 100%, and zero full-collapse ticks for these seeds. These remain reference behavior supported by per-tick radio/state equality, rather than new instrumented clean-run counters. Survivor rescue remains unsupported (`null`), and outcome remains RUNNING at 3,600 ticks.

## 41. 8/16/32-drone bounded scaling probe

| Drones | Before mean ms | After mean ms | Before p95 ms | After p95 ms | Assessments, both | Path searches, both | Energy searches, both |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | 36.174 | 34.768 | 39.370 | 37.114 | 851 | 462 | 420 |
| 16 | 147.097 | 118.689 | 303.869 | 133.588 | 8517 | 1472 | 1378 |
| 32 | 1,448.587 | 524.116 | 2,030.936 | 814.933 | 168946 | 4689 | 4605 |

Seed 2026, 180 ticks each, sequential paired runs. All 181 tick states, final authoritative groups, available detailed checkpoint, replay and CSV match exactly at each size. This is a short startup/scaling probe, not a steady-state large-swarm claim. At 8 drones much of the horizon is cold work, so the benefit is small; at 32 drones repeated assessments are much more pronounced.

The separate 32-drone profile covers 120 of these ticks. Before: 386.412 sampled self-total seconds, 327.808 energy-estimate cumulative seconds and 216.875 pure route-energy seconds. After: 118.486 total, 74.602 energy estimate; `_assign_nearest_sector` remains 82.641 cumulative seconds, route lookup 53.764 and A* 47.485. These nested values overlap. Allocation's route-search demand is now the dominant sampled scaling issue.

At 32 drones, clean maximum update time increased from 25,300.802 to 29,386.153 ms; at 16 drones p99 increased despite a lower mean/p95. The cache does not solve large-swarm startup stalls or provide real-time scaling.

## 42. Remaining measured performance bottlenecks

Reservation rebuilding/trajectory geometry, repeated frontier-work construction and allocation/route work remain substantial. After-cache sampled seed 2027: negotiation 29.900 s, energy estimates 23.254 s, frontier-work construction 12.721 s, reservations 12.514 s and A* 8.423 s (overlapping). At 32 drones, sector assignment and route searches dominate. The cache still creates/checks terrain bytes and route tuples on each lookup; this conservative validity cost is intentional. No secondary optimization was added.

## 43. Remaining confirmed limitations

The cache bounds entry count, not bytes; route-key memory varies with path length. It is not useful for every cold/unique route and preserves all existing planner/allocation cost. Context checking is still per access. Eviction totals and whole-run cost-cache hit totals were not instrumented; sampled reuse is not a claim about every tick.

No guaranteed 60 Hz rate, worst-case latency bound, large-swarm completeness, collision completeness, physical battery accuracy, network realism, survivor rescue or checkpoint continuation is added. Existing Step 10 energy forecasts still exclude unpredictable future traffic/weather/recovery changes. Core Pygame imports remain possible even though headless execution needs no graphical initialization.

## 44. Remaining unverified risks

Exact equality is demonstrated for the tested seeds/configurations/horizons and focused mutation fixtures, not all imaginable maps or Python object states. The differential projection is explicit and must be extended if future authoritative fields are added. It is not a serialization of all process memory.

Arbitrary impure replacements of numerical helpers with hidden mutable inputs are outside the cache contract; function identity checks cannot prove their purity. Custom Map geometry is conservatively bypassed. Cross-platform floating-point/runtime-version equivalence, long-run cache memory distributions, worst-case adversarial route churn and statistically robust latency distributions were not established here. No known authoritative divergence remains in the accepted evidence.

## 45. Scoped Git diff and source validation

| Step 11 file | Additions | Deletions | Purpose |
| --- | --- | --- | --- |
| core/energy.py | 44 | 3 | Only production change: pure-cost cache |
| benchmarks/step11.py | 195 | 0 | Profile/clean timing/per-tick differential harness |
| tests/performance_tests.py | 177 | 0 | 25 collected optimization/tooling cases |
| docs/step11_engineering_report.md | new report | — | This 47-section closure report |

Production + test + workload harness scope is **416 additions / 3 deletions** relative to frozen Step 10. Report and evidence/orchestration files are additional non-production artifacts. Their file inventory/hashes and report line count are recorded in `final_closure_checks.json` and `final_artifact_hashes.json`; raw profiles/checkpoints are evidence, not production code.

Repository-wide Git status also contains approved Steps 1–10 changes, including untracked core files; a HEAD diff alone cannot isolate this tranche. The frozen-source comparison is authoritative for Step 11 scope. `git diff --check` passed; separate scoped validation includes new/untracked Step 11 code and the report. All 49 validated source/test/harness hashes match, all 47 frozen hashes match, and the other 46 baseline paths are unchanged. See `energy_scoped.diff`, `step11_scoped.diff`, and `performance_tests_scoped.diff`. No production change was made during closure.

## 46. Accurate performance claims

ADSS can accurately claim that one bounded pure-calculation cache eliminated most repeated route-energy geometry work in the sampled workloads, while retaining exact tested Step 10 trajectories, decisions, diagnostics, events, RNG, knowledge and persisted content. Fresh paired trials show materially lower mean/p95/p99 update time for the three established seeds.

It cannot claim that decisions were cached, that assessment count was reduced, that every update became faster, that maxima improved, that 60 Hz is guaranteed, or that timing observations establish a platform-independent speedup. The optimization makes the same measured simulation cheaper; it does not reduce policy checks, fidelity or accounting.

## 47. Recommendation for the next roadmap step

Stop here and review Step 11. Retain the exact differential harness as an acceptance gate for future changes. For the next separately approved roadmap tranche, prioritize the roadmap's planned work and use the remaining profile evidence when performance becomes relevant; do not automatically add a reservation or allocation optimization. Broader seed/map/generated-scenario validation and repeated controlled timing trials would strengthen confidence without changing policy.

This is a recommendation only. **Step 12 has not begun. No commit/push/reset/discard was performed. Awaiting approval.**
