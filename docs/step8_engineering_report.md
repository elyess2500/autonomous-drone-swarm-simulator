# Step 8 engineering report — metrics, events, and mission outcome

Step 8 closed on 2026-09-28. Final validation recovered and verified; no production changes were made during closure. Step 9 has not begun.

## 1. Executive summary

Step 8 adds a small deterministic accounting ledger, fixes misleading statistics, separates sampled state from logical actions, and gives mission success and final summaries explicit semantics. Simulation policies from Steps 1–7 remain intact. No Step 9 work or checkpoint continuation is included.

## 2. Metrics/accounting defects reproduced

The initial six red fixtures reproduced: hardware failures remaining zero; permitted base occupancy counted as a near miss; analytics queries creating proximity episodes; empty survivor lists completing an unexplored mission; temporary all-failed swarms being classified as terminal failure; and repeated completion overwriting duration. Later red fixtures cover emergency-charge accounting, missing versioned accounting snapshots, percentage normalization, inconsistent replay metric/event counts, and percentage display. The emergency and replay-extension failures were coverage of the new accounting implementation, not newly discovered Step 7 simulation-policy bugs.

## 3. Placeholder/incorrect statistics

`cells_scanned`, failures, battery returns, communication losses, and weather events had no writers; `missions_found` was assigned only at completion. They now project actual knowledge or events. `battery_returns` retains its compatibility name but means all RETURNING entries, including communication/failure recovery; the summary label is Return Entries. Comm-Loss Events becomes LOST_COMM Entries, separate from physical partitions. Failed-drone state counts no longer include STRANDED. The arbitrary efficiency formula remains a heuristic score, labeled Score/Heuristic score rather than a measured efficiency. It must not be used as a validated scientific efficiency measure.

## 4. Final event model

One ledger belongs to each Swarm, created before initial assignment. Task mutations, drone transitions, survivor observations/publications, upload operations, movement departure after charging, and collision-gate actions emit records at their mutation sites. Weather and mission-completion events belong to Mission. Analytics observes radio transitions, endpoint proximity entry, and swept field contacts once after each complete forward update. The ledger is not an event-sourced simulator and cannot reconstruct or resume a run.

## 5. Event schema and ordering

Version 1 records contain `tick`, zero-based lifetime `sequence`, `kind`, optional integer `actor`, optional string `subject`, `reason`, and canonical JSON `payload_json`. Records are frozen; payloads have no live object references. Construction events use tick 0. Tick execution order is preserved: weather, existing swarm policy/movement/sensing hooks, post-update observations, then completion. Existing deterministic drone priority and sorted upload IDs remain unchanged. The sequence breaks same-tick ties. A state transition and its specialized failure/charging event describe different concepts; they are not added together as one metric.

## 6. Source-of-truth contract

Event metrics project the ledger counts through `EVENT_METRICS`. Knowledge, coverage, battery level, current drone states and radio flags are sampled state. Ratios, unions, elapsed time and summaries are pure queries. Battery consumption/recharge and accepted-movement distance are subsystem accumulators updated where the numerical change happens, not inferred from coarse snapshots. Existing subsystem diagnostics remain explicitly named diagnostics. Appendix A inventories definitions, units, owners, update cadence and persistence coverage. Queries neither emit nor consume records.

## 7. Mission-outcome contract

Supported outcomes are RUNNING and SUCCESS. Compatibility `mission.state` remains running/complete. Success means either global non-obstacle coverage >=98%, reason `coverage_target`, OR every member of a nonempty survivor list globally published, reason `all_survivors_published`. This preserves the prior OR policy; it does not require both, rescue, or every drone returning. LOST_COMM, FAILED or STRANDED drones do not prevent those goals being satisfied. With no survivors, coverage must satisfy the target. There is no mission time limit, partial-success policy, irreversible failure classifier, or persisted aborted outcome. A blocked run stays RUNNING; recoverable failure and operator-rescuable stranding do not terminate the application. This limitation is explicit rather than hidden behind an invented failure rule.

## 8. Survivor accounting

`survivor_local` occurs once per drone/survivor pair on local detection, with connected/disconnected reason. `survivors_local` is the distinct union of privately observed survivor IDs (an omniscient diagnostic, not data supplied to disconnected agents). `survivor_local_observations` counts those pairs. `survivor_published` occurs only on first global insertion through online sensing or gated reconnect upload. `survivors_published` samples global set size. Repeated reports do not produce another publication. Survivor rescue is not modeled: `survivors_rescued` is null, exported as a blank CSV value. Manual rescue relocates stranded drones and emits `drone_rescued`; it is not survivor rescue.

## 9. Task accounting

Awards count new authoritative frontier, sector and relay claims, including tick-zero setup. Retaining the same claim is not an award. Release emits exactly one completed or cancelled event only when a live assignment exists, with kind/ID subject and reason. Replacement is a cancellation followed by an award. A collision wait does not complete or cancel work. Existing frontier-only counters and cancellation reason dictionaries remain compatibility diagnostics; their narrower meaning is retained. Completion means the existing task lifecycle declared its work complete, not a new guarantee about mission success.

## 10. Communication accounting

Partition/reconnect events are per-drone changes in the post-update delivery graph sample, starting from the normal connected-at-base initial condition. They are distinct from delayed LOST_COMM entry and connected recovery. Events may miss disconnect/reconnect transients wholly inside one tick; they do not claim packet-level outage accounting. `discovery_upload` records each nonempty connected buffer merge, carrying newly global and duplicate cell/survivor counts. Empty repeat syncs do not emit. The prior physical-publication probe remains independent validation. `communication_health` is mean modeled signal quality; `connected_fraction` is the fraction of cached base-reachable radio flags, meaningful after graph initialization, not a renamed signal-quality score.

## 11. Collision/safety accounting

`collision_rejected` counts proposals rejected because of blockers; payload lists sorted blocker IDs. `collision_wait` counts the resulting wait once. Backoff attempt, accepted sidestep target, and first exhaustion for a goal/state are separate events. Legacy `conflicts` counts blocker occurrences, which can exceed proposals. Legacy `recoveries` means sidestep initiated, not proven deadlock resolved; `deadlocks` means bounded backoff exhausted, not a graph-theoretic deadlock proof. `field_contact` counts pair-ticks with synchronous continuous point contact outside the docking exception, including stationary pairs. Endpoint proximity episodes use <=0.85 cell size and exclude both centers in the docking zone. They are neither collisions nor rejected proposals. The independent benchmark uses swept proximity episodes, so that differently defined proximity counter is not silently equated with endpoint episodes.

## 12. Energy, charging and failure accounting

Consumption and recharge accumulate actual clamped changes from Battery operations in native battery charge units (100 units at default capacity), not joules. Emergency recharge boosts are included. Forced/operator level assignments are excluded. Average battery and battery percentage displays normalize to each battery capacity. Charging start counts entry into CHARGING; completion means reaching the configured relaunch threshold and transitioning CHARGING→IDLE, not necessarily 100% charge. Relaunch means the first nonzero accepted movement after that completion, including movement within the docking area. Failure/stranding count state entry once, rather than each update spent in that state. Distance sums accepted `_move_toward` increments in pixels; docking snaps and operator relocations are excluded.

## 13. Time accounting

Tick rate remains 60 Hz. `simulation_seconds` always advances with the simulation clock. `elapsed_sec` is mission duration, frozen at the first completion. Completion is idempotent even at tick zero through the compatibility Stats API. CSV retains its legacy two-decimal duration formatting; exact represented time is recoverable from ticks and the unrounded simulation time. Pause/playback do not advance live mission accounting.

## 14. Retention and query semantics

The ledger retains the newest 4096 immutable records and all lifetime per-kind counts. It maintains a SHA-256 chain beginning with 32 zero bytes, hashing previous digest plus canonical record bytes. Count/sequence/hash metadata survives record eviction. Records are accessed as a tuple; snapshots are detached dictionaries. New simulation objects reset everything, including initial assignment records. There is no in-place partial reset. The chain supports repeat comparisons; it is not a signature, and after eviction the retained tail alone cannot recompute the lifetime hash or counts. No unbounded full event journal is persisted.

## 15. CSV consistency

Metrics metadata is version 2 with accounting version 1 and unchanged embedded experiment identity/config. CSV includes exact event counters, outcome/reason/completed tick, sampled mission state and event hash. Samples occur every 60 ticks, plus an immediate completion row even between those boundaries. A completion on a sampling boundary writes only one row. The logger retains Step 7 unique paths and atomic row publication. Unsupported rescue is blank; legacy rounded columns use `csv_row()` consistently. Direct external repeated calls to the low-level logger still append explicit samples; Mission owns normal scheduling.

## 16. Replay consistency

Replay root remains version 2 sampled playback. An optional `accounting` version-1 frame extension holds cumulative counts, retention metadata and hash; `final_summary` holds the frozen completion summary when present. New frames validate the extension version, tick, count sum, retention bounds, hash representation and event-derived metric agreement. Legacy Step 7 frames without this extension remain loadable without invented event counts. Playback does not generate live events. Replay still does not contain a complete event log, executable checkpoint or deterministic continuation.

## 17. Final-summary consistency

`Mission.summary()` returns a detached current snapshot while running, then a frozen completion snapshot. MissionStats projects real sources and freezes with it. Completion is processed before live metrics, CSV and replay capture. Deliberate benchmark updates can continue after completion; those later live metrics have advancing frame/counters but a fixed mission duration and completion tick. The final summary remains the completion-time snapshot and must not be compared as if it represented later ticks.

## 18. Production files changed

- `core/accounting.py`: immutable event records, bounded ledger, count mapping and lifetime digest.
- `core/analytics.py`: pure queries, once-per-tick observations, explicit metric fields, corrected state/battery semantics and CSV metadata.
- `core/mission.py`: real summary projections, idempotent completion, explicit outcome/reason, completion-first export ordering and frozen summary.
- `core/swarm.py`: authoritative task hooks, tick ownership, emergency charge accumulation and operator drone-rescue event.
- `core/drone.py`: transition/discovery/upload/search/relaunch hooks and accepted-movement distance; percentage representation.
- `core/battery.py`: clamped consumed/recharged accumulators.
- `core/intelligence.py`: event hooks beside existing collision diagnostics only; collision policy unchanged.
- `core/replay.py`: optional versioned accounting extension and validation, fresh metric snapshot capture.
- `main.py`: remove unsupported terminal-failure inference and correct metric labels/percentage.
- `ui/dashboard.py`, `ui/replay_view.py`: minimal truthful metric labels/percentage normalization; no UI redesign.

## 19. Tests added

All new fixtures are in `tests/accounting_tests.py`. They cover original defects; task award/completion/cancel/reassignment; private discoveries, duplicates and distinct discoveries; grace/LOST_COMM/partition/rejoin; rejected proposals, retained work and bounded backoff; normal/emergency charging, energy clamp, departure and manual drone rescue; weather/return/coverage sources; success reasons, exact time and frozen summary; field-contact detection; ledger retention/immutability/reset; replay/CSV agreement, compatibility, corrupt counts and detached playback; presentation noise; and percentage display.

## 20. Hand-calculated fixtures

Expected values include: repeated failure trigger →1 failure; same-task retention→1 award; two completed-release calls→1 completion; repeated cancellation→1 cancellation; two drones detecting one survivor→2 local observations and1 publication; different survivors→2 publications; first offline upload→29 new cells; duplicate second upload→0; one radio outage/rejoin→1 partition/1 reconnect; four blocked proposals→4 rejections/4 waits/2 backoff attempts/2 initiated sidesteps/1 exhaustion; no movement→0 contacts; a deliberately overlapping field pair for2 ticks→2 pair-tick contacts but1 proximity episode; charge readiness→0 relaunch until first movement; one tick to success→1/60 second forever; five events with retention2→5 lifetime counts and2 records.

## 21. Focused test results

**33 new Step 8 checks passed; 78 accounting + replay checks passed in 10.90 seconds.** Initial baseline: 6/6 original regression fixtures failed. Follow-up logs preserve the two accounting-extension failures, the two normalization/consistency failures, and the display failure before their focused corrections. One pre-existing pygame/pkg_resources deprecation warning remains. No prior assertion or threshold was weakened.

## 22. Complete suite and smoke results

**235 tests passed in 246.81 seconds**, including all 202 preserved tests and 33 new Step 8 checks. The saved final run completed before the interruption; closure verified its result and the exact current source hashes rather than repeating completed work. All 13 source/test/harness hashes match the pre-validation manifest; all 26 preserved files match the approved baseline hashes.

The full suite includes the 10,800-tick seed-2026 gameplay smoke test. Coverage rose from 1.24% to 51.64%; 4/5 survivors were globally found; relaunch succeeded; no stranded drones, stuck-zero-battery returns, final LOST_COMM drones, or full communication-collapse ticks occurred. Average connectivity was 74.1%, majority connectivity 99.7%, minimum connected count 4/8. Forced communication recovery succeeded with an 805-tick maximum LOST_COMM streak. The existing 29-cell offline buffer synchronized completely, and the offline survivor remained private until reconnect, then published once. Docking checks passed. Existing movement, A*, ownership, reservation/contact, communication, clock/RNG/configuration and replay/persistence tests all passed without altered thresholds.

One existing pygame/pkg_resources deprecation warning remains. `git diff --check` returned exit code 0 with no whitespace errors; its only notice concerns existing LF/CRLF normalization in `core/map.py`, which Step 8 did not modify. A separate scoped check also found no whitespace errors, including new source/test/harness files. That no-index comparison used temporary LF-normalized copies; production files were untouched. Its status 1 denotes differing trees, with no whitespace diagnostics. Closure evidence is saved in `closure_validation.json`, `git_diff_check.txt` and `scoped_diff_check.txt`.

## 23. Before/after metric correctness

| Fixture / interpretation | Before | After |
| --- | --- | --- |
| Repeat failure trigger while already failed | Summary0 | One failure |
| Initial shared docking occupancy | 26 near misses | Zero proximity episodes |
| Separate/rejoin positions between analytics queries | 26 → 27 without a simulation update | Queries do not count events |
| No survivor zones, unexplored world | Immediate completion | RUNNING until coverage goal |
| All drones temporarily FAILED | Terminal application failure | RUNNING; recovery remains possible |
| Complete at60 ticks, call again at120 | Duration2 seconds | Duration1 second |
| Capacity200, level100 | 100% average/card | 50% |
| New replay count differs from event snapshot | Initially accepted extension mismatch | Rejected |
| Discover then later synchronize | Discovery/rescue ambiguous in aggregate | Local pairs, unique global IDs, rescue null |

No previous 3600-tick non-timing mission/communication/safety probe value changed. New lifetime event totals cannot be retroactively recovered from old sampled replay; none are fabricated as historical measurements.

## 24. Mission benchmark metrics

| Metric (before = after) | 2026 | 2027 | 2031 |
| --- | --- | --- | --- |
| Coverage % | 25.526 | 28.479 | 21.839 |
| Global survivors | 2 | 2 | 3 |
| Frontier awards / completions | 21 / 12 | 32 / 20 | 19 / 10 |
| Path searches | 2435 | 3384 | 1038 |
| Mean physical connectivity % | 78.427 | 82.076 | 85.503 |
| Majority-connected % | 100.000 | 98.028 | 100.000 |
| Full collapse ticks | 0 | 0 | 0 |
| Physical partitions / reconnects | 67 / 67 | 28 / 26 | 86 / 83 |
| LOST_COMM entries (boundary probe) | 11 | 9 | 2 |
| Field contact pair-ticks | 0 | 0 | 0 |
| Leaked global cells / survivors | 0 / 0 | 0 / 0 | 0 / 0 |
| Unfinished replacements / relay conflicts / ownership inconsistency ticks | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Stranded drone-ticks | 0 | 0 | 0 |

New trustworthy accounting fields (historical measurements unavailable unless a matching diagnostic existed; unavailable is not zero):

| Final Step 8 metric | 2026 | 2027 | 2031 |
| --- | --- | --- | --- |
| Outcome | running | running | running |
| Distinct local survivors | 2 | 2 | 3 |
| Local drone-survivor observations | 2 | 6 | 9 |
| Rescued survivors (unsupported) | None | None | None |
| All-kind task awards | 27 | 40 | 28 |
| All-kind completions | 12 | 21 | 11 |
| All-kind cancellations | 9 | 14 | 12 |
| Nonempty connected upload merges | 64 | 21 | 73 |
| Collision proposal rejections | 6553 | 453 | 5319 |
| Collision waits | 6553 | 453 | 5319 |
| Backoff attempts | 1 | 1 | 3 |
| Backoffs initiated | 1 | 1 | 3 |
| Exhausted backoffs | 0 | 0 | 0 |
| Charging state entries | 2348 | 5341 | 5367 |
| Threshold charge completions | 2348 | 5338 | 5364 |
| Actual relaunch movements | 7 | 19 | 7 |
| Hardware failures | 0 | 0 | 0 |
| Stranded entries | 0 | 0 | 0 |
| Lifetime events | 25316 | 26011 | 33547 |

Charge-entry/completion counts are large because existing base policy repeatedly cycles CHARGING→IDLE→CHARGING. These are actual mutation-site transitions; they are not thousands of complete battery/flight cycles. Relaunch counts and charge added are separate. No allocation/charging policy was changed. Failure probability is zero in these established benchmark scenarios; positive failure accounting is covered by fixtures and the stochastic presentation matrix. No seed reached success in 3600 ticks; completion behavior is validated with exact fixtures.

| Additional final accumulator | 2026 | 2027 | 2031 |
| --- | --- | --- | --- |
| Accepted movement, pixels | 20129.637 | 28095.400 | 19030.228 |
| Consumed charge units | 303.336 | 377.844 | 272.199 |
| Recharged charge units | 205.560 | 416.559 | 275.714 |


## 25. Step 7 → Step 8 performance

Fresh same-host, same-seed/config/horizon runs: 3600 ticks each, normal mode, autonomous offline enabled, failures disabled. Before uses frozen Step 7 with the unchanged Step 6/5/4 probe; after uses the same underlying probe plus extraction of new accounting outside timing. Timing includes normal update work, CSV/replay work and the established sensor instrumentation, and excludes external post-update graph/contact checks. No full suite or second benchmark ran concurrently with the timed trials. Short interactive editing/test activity during the first baseline and normal host load were not controlled; these are observational timing comparisons, not isolated causal overhead measurements.

| Seed | Mean ms before→after | p50 | p95 | p99 | Max | Mean delta |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | 11.799 → 10.678 | 11.740 → 11.002 | 19.153 → 16.449 | 30.657 → 25.438 | 79.417 → 54.982 | -9.50% |
| 2027 | 16.567 → 16.118 | 16.557 → 15.903 | 28.015 → 29.912 | 39.166 → 41.183 | 82.482 → 107.209 | -2.71% |
| 2031 | 13.124 → 13.058 | 13.996 → 14.231 | 21.870 → 21.660 | 30.033 → 27.303 | 63.536 → 51.353 | -0.51% |

These single sequential trials do **not** establish a speedup. There was no optimization. Unchanged reservation construction also ran faster in the after trials, showing substantial host/run variability. Step 8 adds hash/event and observation work; its collision-gate portion has measurable extra cost in the high-wait runs. The total wall-time difference cannot isolate that cost causally from host variability. Seed 2027 tail latency worsened even though its mean decreased.

| Seed | Reservation rebuild ms/tick before→after | Gate ms/tick before→after |
| --- | --- | --- |
| 2026 | 5.4078 → 4.7321 | 0.0937 → 0.1747 |
| 2027 | 5.9275 → 5.4272 | 0.0780 → 0.0808 |
| 2031 | 4.9628 → 4.8016 | 0.0761 → 0.1338 |

Gate cost includes the new rejection/wait/backoff hooks; reservation rebuild code and call counts are unchanged. Persistence/accounting additions remain included in whole-update latency, with no unsupported attribution of their separate cost. These numbers describe only Step 7→Step 8, not Original ADSS→Phase 1 or the pre-existing Step 4 reservation cost.


## 26. Reproducibility

All **33 shared non-timing fields** matched Step 7→Step 8 for each of 2026/2027/2031. Repeated Step 8 seed 2026 matched **37 non-timing fields**, including all new metric fields/counts, summary, accounting metadata, outcome and the existing state/knowledge/experiment hashes. Timing fields and timing component summaries are deliberately excluded; component call counts are unchanged.

| Seed 2026 repeat comparison | Run A = Run B |
| --- | --- |
| Existing state hash | f9e960c453c5210473b8f9c6ba0b6b05bcc826792d6c5b601ab9c8c9021b2553 |
| Step 6 behavioral state hash | ac429158094d91f742d9223e792f4a1cfe321b141a58eedee6c4a31a0c619cd0 |
| Knowledge hash | 036b750d4c7e3c68400e6a6a18120819cebe775587a75f9569e198c8be6d2d88 |
| Experiment identity | 1e62ad727c0ffc67557a631c475b30150f0139cb5647df3a1b919c6238878f9d |
| Event/accounting hash | f2ece15a163b224973a36abdffe3daff8c22bad4995921b923f8de874e3b286c |
| Outcome | running |

The presentation matrix used 180 ticks, failure probability 0.003 and weather interval 30 to exercise failure and weather events. It is a different declared configuration from the 3600-tick no-failure benchmark; their hashes are not compared to each other. All seven conditions matched state, knowledge, experiment, full metrics and accounting/event hash:

| Condition | FPS argument | Render cadence | Mismatches |
| --- | --- | --- | --- |
| headless | 60 | none | 0 |
| normal | 60 | each tick | 0 |
| normal | 30 | each tick | 0 |
| normal | 144 | each tick | 0 |
| reduced | 60 | every 7 ticks | 0 |
| overlays_off | 60 | each tick | 0 |
| noisy | 60 | each tick | 0 |

The matrix produced 894 events, including 3 hardware failures and 6 weather changes, in every condition. Event hash: `7298dd658fdd1fea94f37de67d2c920750704dca53c2a95f55d7bd7091f7a987`. Renderer conditions use software surfaces and nominal FPS arguments, not a claim about real display-driver rates. The noisy mode adds unrelated Python/NumPy presentation draws. Seed 2026 repeat mean update latency was 10.706 ms; host variation remains visible even with identical state.


## 27. Intentional behavior changes

Empty survivor lists no longer imply immediate success. Temporary all-failed/all-stranded swarms no longer cause unsupported automatic terminal failure; the user can continue or stop a blocked mission. Analytics queries no longer change proximity history. Shared-base proximity is excluded. Final duration and summary freeze once, completion is exported immediately, and failed/stranded and local/global/rescue concepts remain distinct. Extra bookkeeping does not feed allocation, navigation, radio delivery or collision decisions. Minimal label/percentage corrections affect presentation only.

## 28. Remaining confirmed limitations

Repeated charging-state churn at base remains existing policy; charging transition counts are not flight-cycle counts. No survivor-rescue mechanic, irreversible failure policy, time limit, aborted outcome, globally complete event journal, checkpoint, or continuation exists. Success retains the permissive coverage-OR-discovery policy. Events assume approved mutators; direct external field mutation can bypass them. Standalone drones without a Swarm owner have no mission event ledger. Tick-zero radio flags have not yet been graph-refreshed; connectivity metrics use cached flags, not an independent fresh graph query. Endpoint proximity is sampled, not swept. Point contacts are not finite-body collisions. Energy is abstract charge, and movement distance excludes snaps/relocations. The heuristic score is not validated efficiency. Legacy diagnostic names have the meanings documented here rather than implied stronger meanings.

## 29. Remaining unverified risks

Cross-platform floating-point/event-hash equality, arbitrary third-party state mutation, unusual custom initial deployments, extreme swarm sizes, and statistical confidence intervals from larger timing samples remain unverified. No claim of general collision completeness or network realism is added. Hashes are reproducibility aids, not authenticity protection.

## 30. Git diff summary

Diffs are measured against the frozen approved Step 7 working tree, **not** Git HEAD, which also contains prior approved uncommitted tranches. The scoped code/test/harness diff is:

| File | Added | Deleted |
| --- | --- | --- |
| benchmarks/step8.py | 80 | 0 |
| core/accounting.py | 68 | 0 |
| core/analytics.py | 78 | 6 |
| core/battery.py | 6 | 0 |
| core/drone.py | 36 | 3 |
| core/intelligence.py | 5 | 0 |
| core/mission.py | 65 | 25 |
| core/replay.py | 25 | 1 |
| core/swarm.py | 9 | 0 |
| main.py | 6 | 11 |
| tests/accounting_tests.py | 368 | 0 |
| ui/dashboard.py | 4 | 4 |
| ui/replay_view.py | 1 | 1 |

Subtotal: **13 code/test/harness files, +751/−51 lines**; 11 production files, one new test file, one benchmark harness. This new engineering report adds 362 lines, bringing the reviewed source/test/harness/report scope to 14 files, +1113/-51 lines. Saved validation artifacts are additional evidence files, outside that source diff. `step8_scoped_git.diff` is the final Git-generated scoped diff; `step8_only.diff` is the readable baseline comparison, and `source_manifest.json` retains hashes. Both working-tree and scoped whitespace checks passed. All existing tests and `config.py` are byte-for-byte unchanged. Communication, planner, geometry, experiment/clock/RNG and persistence implementations are unchanged. Movement, allocation, radio and collision policies were not modified; their files received only the accounting hooks listed above. Replay architecture/capabilities are unchanged; only optional accounting metadata/validation and percentage presentation were added. No unrelated optimization or Step 9 work was done. No commit or reset was performed.


## 31. Accurate claims

ADSS can report deterministic, explicitly defined action counts from approved mutation paths; separate private discovery, global publication and unsupported rescue; distinguish waits/rejected proposals from actual point contacts; expose sampled state without query side effects; freeze outcome-time summaries; and persist compatible sampled accounting snapshots. These claims are scoped to documented semantics and validated scenarios. It cannot claim complete event reconstruction, realistic energy/network/collision physics, irreversible-failure classification or survivor rescue.

## 32. Recommendation and stop boundary

Recommend the original roadmap's Step 9 — P1: Incremental headless/render separation, in a separately approved tranche. Preserve the new event and metric contracts while clarifying simulation/presentation interfaces. Step 8 is complete. Stop here and wait for explicit approval; Step 9 has not begun.

## Appendix A — audited metric inventory

Inventory conventions: **E** = cumulative event-derived count, **A** = mutation-site accumulator, **S** = sampled state, **Q** = pure derived query, **D** = legacy diagnostic. All reset on a fresh simulation, not on render/pause/query. E fields count approved logical actions once, including multiple distinct transitions inside one tick; bypassing approved mutators can miss them. A fields accumulate every actual operation including multiple operations per tick. S/Q fields never increment an event by observation. Unless noted otherwise, MissionMetrics fields are captured after each update, exported every 60 ticks plus completion, persisted at replay samples/explicit export, and frozen in the final summary. Replay holds the preceding sample between recorded ticks, and CSV rounds only its documented legacy columns. UI animation can lag sampled values visually; it is not a separate authoritative counter.

| Metric(s) | Class / unit | Source and update location / frequency | Consistency, duplication and persistence |
|---|---|---|---|
| frame; simulation_seconds | Q / ticks; seconds | SimulationClock; every forward update, seconds=tick/60 | Never advanced by playback; in CSV/replay/summary |
| elapsed_sec; Stats elapsed/start_time/end_time | Q/S / seconds | MissionStats clock and first complete() | Duration freezes once; CSV elapsed rounded2 decimals |
| outcome; completion_reason; completed_tick | S / enum, reason, tick | Mission.update success gate once | Completion event once; frozen final snapshot; later live samples labeled explicitly |
| coverage_pct; Map.exploration_pct; Swarm.mission_progress | Q / percent or fraction | Global fog AND grid!=OBSTACLE / all grid!=OBSTACLE | NO_FLY is included in this historical denominator; not reachable/searchable-area coverage |
| Stats cells_scanned | Q / unique eligible cells | Same numerator as coverage | Includes zero-event initial reveal; freezes at completion; replay Stats and summary |
| active_drones | Q / drones | Count states excluding FAILED, STRANDED, CHARGING | LOST_COMM and RETURNING included; not synonymous with productive |
| failed_drones; stranded_drones | Q / drones | Separate current-state counts | Current occupancy, not lifetime entries |
| average_battery | Q / percent | Mean 100*level/max across all drones | Changed from raw charge units; CSV rounded2 decimals |
| communication_health | Q / ratio | Mean CommNode.signal_quality | Modeled distance-based signal score, not connected fraction; CSV rounded3 decimals |
| connected_fraction | Q / ratio | Mean CommNode.is_connected flags after radio refresh | Cached graph state; tick0 flags uninitialized; no new RF model |
| frontier_completion_rate | Q / ratio | min(1,frontiers_completed/frontiers_assigned), zero with no awards | Frontier contracts only; cancelled/reawarded work remains denominator; CSV rounded3 decimals |
| collision_near_misses; Analytics.near_miss_count | E projection / episodes | Analytics.observe endpoint pair entry <=0.85 cells, excluding shared dock | Compatibility name; no longer query-driven; not collision probability |
| stuck_recoveries | D / recovery actions | Sum Drone._tick_stuck_recovery reroute/reassign actions | May count multiple different recovery actions; not proof of successful recovery |
| mission_efficiency | Q / score0–100 | Existing weighted coverage/battery/signal/frontier formula minus proximity/stuck/failed penalties | Heuristic only; label corrected; CSV rounded3 decimals |
| survivors_local | Q / distinct survivor IDs | Union of drone mission_found lists | Omniscient private-state diagnostic; not globally delivered knowledge |
| survivor_local_observations | E / drone-survivor pairs | Drone._scan_online/_scan_offline first local insertion | Two drones finding same survivor count 2; repeated same-drone detection counts 0 |
| survivors_published; Stats missions_found | Q / unique global IDs | Map.mission_found set after approved sensing/sync | Distinct from local pairs; summary freezes; survivor_published event records first publication |
| survivors_rescued | unsupported / null | No survivor rescue mechanic | CSV blank, JSON null; never substitutes discovery count |
| task_awards | E / contracts | Swarm._claim_assignment successful new claim | All frontier/sector/relay kinds, including tick0; same claim is idempotent |
| task_completions | E / contracts | Swarm._release_assignment(completed=True) with live claim | Repeated completion of released task counts 0 |
| task_cancellations (metrics) | E / contracts | Swarm._release_assignment non-completed live claim | Reassignment cancels then awards; waiting does neither |
| path_searches | E / search invocations | Drone._search_path before find_path | Includes feasibility and route searches, successful or not; excludes external standalone planner calls |
| partitions; reconnects | E / per-drone graph transitions | Analytics.observe once per completed forward tick | Initial deployment assumed connected-at-base; intra-tick transients not counted |
| lost_comm_entries; Stats comm_losses | E / entries | Drone.set_state→LOST_COMM | Timeout behavior count, not physical partition count |
| discovery_uploads | E / nonempty connected buffer merges | Drone._sync_offline_discoveries | Includes duplicate-only merges; empty or disconnected attempts do not emit |
| collision_rejections; collision_waits | E / proposals; waits | ReservationTable.try_move blocker branch | One rejected proposal can have several blocker IDs; neither counts actual contacts |
| backoff_attempts; backoffs; exhausted_backoffs | E / attempts; initiated targets; exhaustion notices | ReservationTable._recover | Bounds unchanged; exhaustion once per tracked goal/state episode |
| field_contacts | E / pair-ticks | Analytics.observe synchronous center trajectories with docking exception | Repeated sustained contact counts each tick; positive fixture validates monitor; not body-volume collision |
| charging_starts; charging_completions | E / state entries; threshold completions | Drone.set_state CHARGING and CHARGING→IDLE at relaunch threshold | Repeated base cycling is real state churn, not necessarily meaningful charge cycles |
| relaunches | E / departures | First accepted nonzero _move_toward after charge completion | Not counted merely for IDLE readiness; pending departure cleared by failure/stranding |
| hardware_failures; Stats drone_failures | E / FAILED entries | Drone.set_state transition | Repeated observation/trigger while still FAILED does not recount |
| stranded_transitions | E / STRANDED entries | Drone.set_state transition | Separate from number currently stranded |
| distance_travelled_px | A / pixels | Accepted _move_toward increments | Excludes docking snap and manual relocation; sums all drones |
| battery_consumed_points; battery_recharged_points | A / charge units | Battery.update/_charge and Swarm emergency boost | Clamped numerical changes; excludes direct external overrides, not physical energy |
| event_count; event_hash | Q / count; SHA256 | Accounting lifetime sequence and chain | Retained records may be fewer; counts/hash persisted, full log not persisted |
| Stats num_drones; total_missions | S / counts | Mission construction from actual swarm/world | Static experiment metadata; replay Stats and summary labels |
| Stats battery_returns | E / RETURNING entries | Drone.set_state | Compatibility name; summary relabeled Return Entries; includes recovery returns |
| Stats weather_events | E / weather changes | Mission after Weather.update | Counts actual changed weather, not weather frames; replay and summary |
| Swarm frontiers_assigned/frontiers_completed | D / frontier contracts | Auction award / authoritative completed release | Narrower than all-task metrics; preserved replay fields |
| Swarm task_cancellations dictionary | D / cancellations by reason | Authoritative released claims | Same mutation as task_cancelled; compatibility reason projection; replay preserved |
| Swarm assignments/offline_assignments | S / ownership maps/sets | Claim/release, not sampled counts | Authoritative owners; invariant probe tests agreement; assignments replayed |
| sectors_completed; Sector.completed | S/Q / sectors, bool | Sector is_fully_scanned/assignment lifecycle | Historical flags, not task completion events; replay sector fields |
| relay_drone_count/explorer_drone_count | S / drones | _update_exploration_balance role projection | Exposed debug/HUD, may precede final tick role changes; replay drone roles allow inspection |
| average_frontier_distance | Q / cells | Mean base-to-active frontier or queue-first target in _update_exploration_balance | Name is broader than frontier-only; HUD/debug; not a travel-distance metric |
| coverage_growth_per_min | D/Q / coverage fraction per minute | Rolling <=one-minute tick/coverage history before movement | Nonnegative, short-history floor retained; HUD/replay swarm field |
| comm_risk_relaxation | D / bounded policy scalar | Every60 updates using stall/growth history | A policy setting, not a measured communication success rate; replayed |
| offline_risk_assignments | D / frontier awards | Successful auction claims tagged offline-risk | Not all offline ticks or all current offline contracts; debug/HUD |
| comm_repair_events | D / repair activations | _repair_comm_mesh at configured repair interval | Attempts, not successful reconnects; replayed |
| full_comm_collapse_events | D / pre-motion zero-connected ticks | _repair_comm_mesh each update before its interval gate | Despite name, not unique collapse episodes; separate benchmark post-motion collapse ticks |
| min_connected_count; last_comm_snapshot | D/S / count; graph snapshot | Repair observation minimum; latest radio refresh snapshot | Lifetime pre-motion min vs current graph distinguished; graph diagnostic only |
| coverage_stall_recoveries; emergency_recoveries | D / recovery procedure activations | _watch_coverage_stall/_emergency_recover_swarm | Not proven successful recovery; emergency count replayed |
| Drone lost_comm_recoveries | D / helper calls | _recover_comm_link | Compatibility procedure counter, distinct from transition event; not a global reconnect count |
| Drone offline_synced_cells/survivors | A / newly global items | _sync_offline_discoveries successful merge | Duplicate items add 0; replayed per drone; cell metric includes any terrain |
| pending/offline cell and survivor sets, info/progress buffers | S / IDs/cells/records | Sensing and reconnect merge | Sets idempotent; progress logs bounded, not full observation counts; sets/info replayed |
| Drone map_known; mission_found | S / cell IDs; survivor IDs | Local observation (map also peer knowledge merge) | Map-known does not imply personally sensed; replay local knowledge masks/lists |
| Drone state/prev_state, comm_role, relay flags/lease, task IDs, queue/path, decision | S / enum, IDs, ticks, cells, text | Existing state/policy mutators | Diagnostics and rendering; main structural fields replayed, decision text not an event source |
| Contact age, lost_comm_frames, failure/scan/reroute/stuck timers | S / ticks | Existing update/state routines | Timers, not counts of logical events; listed Step 7 private fields persisted |
| Drone comm_risk_score / comm_path_risk_weight | D / heuristic scalars | Bid evaluation/assignment | Not measured loss probability; debug only |
| CommNode signal_quality, connected_ids/relay_ids, is_connected/is_lost | S/Q / ratio, IDs, bool | CommManager graph refresh / contact age | Physical graph flags and timeout state distinct; replay flags/age/signal |
| CommManager connected_ratio/reachable_ids/weak IDs/clusters/link lists | S / ratio, graph sets | Graph refresh pre/post movement | No packet statistics; debug overlays; no new cumulative count inferred |
| Map fog and heatmap | S/A / bool; reveal/online scan contributions | reveal_area, scan_area, reveal_cells | Heatmap is not total physical visits: offline repeated visits collapse on merge; replayed |
| Survivor debug reachability/radius/nearest-drone/in-sensor | Q / bool, cells | Map.survivor_debug | Ground-truth diagnostic, not delivered discovery; not event counted |
| Weather current/_timer | S / enum; ticks | Weather.update each forward tick | Step6 RNG unchanged; replayed |
| Reservation conflicts/waits/recovery_attempts/recoveries/deadlocks | D / blockers, proposals, attempts, initiated sidesteps, exhaustion notices | Existing gate/recovery sites | Exact aliases to narrower event concepts documented above; preserved replay counters |
| Reservation cells/edges/trajectories/tick and waiting/attempt maps | S / occupancy, absolute ticks | Rebuild/begin_tick/gate | Forecasts/control state, not collision counts; replay retains diagnostic tick/counters only |
| Path result status/cost/expanded/resolved goal | D / enum, traversal cost, nodes, cell | Each planner call result | Per-search diagnostic, not a cumulative search count; no planner redesign |
| Benchmark unfinished_task_replacements/relay_task_conflicts/orphaned_ownership_ticks | external D / observed calls or inconsistent-object ticks | Unchanged tranche1 instrumentation | Not production event counts; raw before/after JSON and invariant assertions |
| Benchmark physical avg/majority connectivity, collapse ticks, max offline ticks | external S/Q / fractions, ticks | Independent physical graph each sampled tick | Majority means >half; denominator all drones; averaged over requested horizon |
| Benchmark disconnected observations/buffer additions/uploads/duplicates/leaks | external A / operations or items | Independent radio graph around sensing/sync | Attempts-with-pending include disconnected failed attempts; differs intentionally from discovery_upload events |
| Benchmark point_contact_pair_ticks/proximity_episodes, stranded_drone_ticks, field_charging_violations | external S/A / pair-ticks, episodes, drone-ticks | Independent continuous safety and state probes | Proximity uses swept geometry; exported JSON, not silently equated with endpoint proximity |
| Benchmark latency/component timing, state/knowledge/experiment hashes | external Q / wall ms, SHA256 | perf_counter and detached state serialization | Excludes post-update probe checks; includes existing sensor instrumentation; no wall time in simulation decisions |
| Dashboard FPS/animation/pulses/alert age; alert strings | presentation / frames,FPS,text | Render/UI calls | Not simulation event evidence; alerts can be bounded/repeated and are never parsed for accounting |


## Evidence and reproduction

Evidence is under `benchmarks/results/step8/`; the frozen Step 7 source is `external frozen baseline (step8_step7_baseline)`. Prior uncommitted work is preserved. Red/focused/full-suite logs, fresh before/after/repeat JSON, presentation matrix, source hashes and a scoped patch are retained. Partial JSON files are progress checkpoints, not separate trials.

Reproduction commands (run benchmarks sequentially):

```text
python -m pytest tests/accounting_tests.py tests/replay_tests.py -q
python -m pytest -q -s
# In the frozen Step 7 directory, with output pointed to the Step 8 evidence directory:
python benchmarks/step6.py --ticks 3600 --seeds 2026 2027 2031 --output before.json
# In the current working tree:
python benchmarks/step8.py --ticks 3600 --seeds 2026 2027 2031 --output benchmarks/results/step8/after.json
python benchmarks/step8.py --ticks 3600 --seeds 2026 --output benchmarks/results/step8/repeat.json
python benchmarks/step8.py --matrix --ticks 180 --seeds 2026 --output benchmarks/results/step8/presentation_matrix.json
```

Python 3.13.7 / pygame 2.6.1 on the existing Windows host. Experiment identity retains Step 6 semantics: selected configuration, resolved seed and RNG-version metadata; it does not hash source code. Event/accounting schema version and source manifests are recorded separately.
