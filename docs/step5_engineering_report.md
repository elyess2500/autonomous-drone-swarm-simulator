# ADSS — Step 5 engineering report

Date: 2026-09-27. Scope: P0 connectivity and discovery boundaries. Phase 1 and Step 4 remain approved. Step 6 has not begun.

## 1. Executive summary

Step 5 closes the physical connectivity boundary around discovery publication. The complete suite passes **128 tests**, including all 88 previously approved tests and 40 new communication cases. The three 3,600-tick benchmarks reduced disconnected global publication from **447 map cells and two survivor IDs to zero of either**, measured with the same independent physical-connectivity probe. Field point contacts, unfinished-task replacements, relay conflicts and ownership inconsistencies remain zero in all three final runs.

The seed-2026 repeat matches all **29 non-timing fields**, its final simulation-state hash and a new local/global-knowledge hash. The long smoke run retains the existing acceptance thresholds: 4/5 survivors, no stranded drones or full communication collapses, successful docking/relaunch, communication recovery and offline synchronization. Global coverage falls from 49.00% to 44.47%; reported average connectivity rises from 75.6% to 79.0%. Correcting delivery changes the subsequent mission trajectory, so these are measured tradeoffs, not a controlled attribution of every change to one cause.

## 2. Original communication defects reproduced

The unchanged Step 4 implementation produced **23 failures and 10 passes** in the initial 33-case run. This count includes new contract decisions as well as bugs; it is not a claim of 23 independent defects.

- The scan branch used `AUTONOMOUS_OFFLINE_MODE && state == LOST_COMM`. Disconnected agents therefore published directly during grace, and disabling offline autonomy also disabled buffering.
- `_sync_offline_discoveries` had no delivery gate. Recovery from LOST_COMM was its only normal trigger, leaving brief reconnects and charging outside the synchronization lifecycle.
- A graph computed before movement could authorize a scan after crossing the radio boundary. A follow-up failure proved that buffered uploads during sequential drone updates could also use a relay that had already moved out of range.
- A low grace counter could restore the LOST_COMM behavioral state without a physical link.
- Offline survivor detection read the global `mission_found` filter, suppressing observations unknown to the disconnected observer. Repeated partition/rejoin could duplicate local survivor entries.
- Repeated map merges incremented the heatmap for already-global cells, making merge side effects non-idempotent.
- Offline survivor alerts were forwarded unconditionally to the global dashboard, disclosing an observation before synchronization.
- Both connectivity-risk consumers used `connected_ratio or 1.0`, replacing a legitimate zero with healthy connectivity.
- Broadcast flushed disconnected outboxes, discarding queued messages before delivery.

FAILED/STRANDED radio participation and disconnected peer gossip were ambiguous old semantics, not assumed failures of a previously explicit radio contract. This tranche adopts the rules below. Existing post-timeout buffering, relay reachability, survivor set merging and 29-cell recovery were working behavior and remain tested.

## 3. Final communication/connectivity contract

An enabled radio is connected when the symmetric distance graph has a path to the base sentinel `-1`, directly or through enabled peers. The existing configured range is 180 pixels, including the boundary. There is no RF obstruction, signal interference, packet loss, bandwidth or propagation-delay model. All enabled drones can relay regardless of their allocation role.

The graph is refreshed before motion for behavioral policy, then after all movement for sensing and delivery. Contact counters advance only during the first pass; the second pass preserves the inbox and does not increment them again. A detected reconnect resets the counter in either pass. Connected ratio includes all drones in its denominator; disabled radios are disconnected.

Disconnected observations stay local from the first disconnected sensing tick. Delivery occurs at the post-movement communication boundary, independently of grace or task policy. Pending discoveries synchronize immediately in that delivery phase, with no bandwidth limit, network queue or handshake simulation. Ordinary generic messages retain the existing periodic broadcast schedule and outbox abstraction.

## 4. Physical connectivity versus LOST_COMM

`CommNode.is_connected` represents the current graph snapshot. `LOST_COMM` remains a delayed behavioral state after `SIGNAL_LOSS_FRAMES=180` disconnected pre-movement samples. Its existing offline-task/recovery policy and 360-frame recovery timeout remain in place. A first loss detected after movement can have a zero grace counter until the next pre-movement sample; information delivery is already blocked.

A reconnect may upload data at the end of a tick while behavioral recovery waits until the next update. Recovery now requires a restored link, not just a small counter. Thus physical reachability, behavioral policy and data publication have explicitly different responsibilities. No simulation-clock or RNG redesign was introduced.

## 5. Local versus global knowledge

`Drone.map_known` holds locally available cells, including observations and permitted connected-peer sharing. `Drone.mission_found` is a persistent, duplicate-free list of locally observed survivor IDs. `offline_known_cells`, `offline_survivor_found` and survivor metadata hold pending observations. They survive disconnection and are cleared only after a connected merge.

`Map.fog` and `Map.mission_found` are the authoritative globally published discovery state used by frontier generation, coverage, mission completion and normal dashboard/map discovery displays. The simulator still owns terrain/survivor ground truth and omniscient diagnostic state; this is not a fully decentralized belief-state simulator.

## 6. Map discovery propagation

A scheduled scan first updates local knowledge. If disconnected, its in-bounds cells enter the offline set and do not alter global fog or heatmap. Connected scans retain the existing immediate global scan/visit behavior. Calling the online helper while disconnected redirects to local buffering.

On reconnect, `reveal_cells` unions buffered cells into global fog and returns the number newly revealed. Already-global cells are acknowledged without another heatmap increment. Connected repeated scans still increment the heatmap as visits. Offline buffers are sets, so they preserve discovery membership, not the full count/timing of every offline scan; the heatmap is not a complete offline visit history.

## 7. Survivor discovery propagation

Sensing checks nearby ground-truth zones without using the global found set to decide what the local observer may discover. The local ID list prevents repeat observations from duplicating local records. Disconnected new observations enter the survivor buffer; they do not update global survivor IDs or emit globally forwarded discovery alerts.

Synchronization processes IDs in sorted order. Only previously unpublished IDs receive new global discovery credit and a synchronized-survivor alert. Two disconnected agents can observe the same survivor; both acknowledge their buffered report, while global discovery is recorded once. Normal dashboard discovery totals continue to read the global set; no UI or analytics architecture was changed.

## 8. Partition and reconnect synchronization

Brief partitions and prolonged LOST_COMM partitions use the same buffers. Reconnecting before timeout, after LOST_COMM or while charging all trigger synchronization. Repeated empty or duplicate synchronization leaves discovery state unchanged. Each agent owns its own pending observations; another drone's report may make some buffered items globally redundant before upload.

Both scans and buffer uploads are deferred until the post-movement graph is fresh in `Swarm.update`. This closes the sequential-update relay-loss race. The standalone `Drone.update` default retains its existing calling convention and synchronizes using the graph supplied by its caller; callers outside Swarm must maintain that graph. Private helpers are not a substitute for a valid physical snapshot.

## 9. Relay semantics

Enabled peers form instantaneous multi-hop routes to base. A designated relay role affects allocation/positioning, not radio eligibility. Losing any necessary relay removes downstream base reachability; restoration permits publication in the next delivery phase. Connected peers retain shared-map gossip through the existing broadcast abstraction.

Disconnected components do not exchange the base knowledge bus or transfer ownership of pending buffers. Partition-to-partition store-and-forward is deliberately not modeled. Disconnected generic outboxes are retained until rejoin rather than flushed and lost. Connected message sources deliver within the base-connected component. BFS and component traversal use stable ordering for reproducible graph diagnostics.

## 10. Failed, stranded and docked radios

FAILED means hardware failure including the radio; STRANDED means no usable radio power. Neither acts as a base link, relay, message source or upload source, even if cached node links are stale. Their buffers remain in simulator memory and can be uploaded after an explicit state restoration and reconnect; no data-loss model is added.

Other states have operational radios. Docked CHARGING drones communicate on base power even at zero battery. This does not authorize charging outside the physical docking zone; all existing docking safeguards remain unchanged. Random failures are disabled in the comparable mission benchmarks, so failure-radio claims rely on focused fixtures rather than those normal-mode runs.

## 11. Zero-connectivity bug

`_relay_anchor_count` and `_comm_risk_for_cell` both converted `0.0` to `1.0` through truthiness. Their defaults now apply only when the snapshot key is missing: `get("connected_ratio", 1.0)`. Zero therefore produces the appropriate degradation penalty and relay-demand response. Tests cover exactly zero, `1e-12` and 0.1. Signal quality remains the existing distance-based heuristic; it is not substituted for graph connectivity or a measured RF probability.

## 12. Production files changed

| File | Reason |
|---|---|
| `core/communication.py` | Explicit radio eligibility; refresh without double-ticking counters; stable graph traversal; retain disconnected outboxes; restrict shared data/message delivery to the base component. |
| `core/drone.py` | Physical delivery gates, independent synchronization, deferred sensing/upload integration, local survivor deduplication and delayed discovery alerts. |
| `core/swarm.py` | Post-movement delivery phase and two zero-connectivity fallback fixes. |
| `core/map.py` | Idempotent buffered-cell merge, including heatmap side effects. |

Reservation geometry/control, A*, configuration, all previous test files, replay, clock/RNG, UI and analytics source remain byte-identical to the approved Step 4 snapshot. No unrelated task-allocation policy was rewritten; the two risk consumers changed only their zero handling.

## 13. Tests added

`tests/communication_tests.py` adds **40 parameter-expanded cases** covering first loss, grace, timeout and prolonged partition; offline-autonomy enabled/disabled; reconnect before and after LOST_COMM; repeated joins; map and survivor privacy; direct helper guards; globally known/local-unknown survivors; multiple agents with distinct or duplicate observations; heatmap idempotence; relay loss/restoration; FAILED/STRANDED/CHARGING radio rules; zero and near-zero connectivity; retained outboxes; connected and isolated peer sharing; stale movement/relay snapshots; timeout-counter cadence; discovery-alert gating; and deterministic repeated execution.

Initial failures are saved in `red.txt`. Additional failing evidence is in `phase_boundary_red.txt` (three failures, one passing counter guard) and `alert_red.txt` (one failure). The later prolonged-partition and connected-scan cases extend coverage of those established fixes.

## 14. Focused results

**123 passed in 3.06 seconds**: all 40 Step 5 cases plus the preserved 83 focused Phase 1/Step 4 cases. No acceptance threshold or existing test was weakened. The earlier 33-case communication-only checkpoint also passed before the remaining boundary tests were added. See `focused.txt` and `focused_initial.txt`.

## 15. Complete suite and smoke results

Command: `python -u -m pytest -q -s`. **128 passed in 207.20 seconds**, with one existing pygame/pkg_resources deprecation warning. This validates the final production hashes; there were no later production changes.

| 10,800-tick seed-2026 smoke diagnostic | Step 4 | Step 5 |
|---|---|---|
| Global coverage | 49.00% | 44.47% |
| Globally found survivors | 4/5 | 4/5 |
| Reported average connectivity | 75.6% | 79.0% |
| Reported majority-connected fraction | 99.5% | 99.8% |
| Minimum connected | 4/8 | 3/8 |
| Full communication-collapse ticks | 0 | 0 |
| Final stranded / zero-battery RTB | 0 / 0 | 0 / 0 |
| Final LOST_COMM agents | 2 | 0 |
| Forced recovery duration | 794 ticks | 794 ticks |
| Dock/recharge/relaunch | Pass | Pass |
| Offline map regression | 29 local cells, sync passes | 29 local cells, sync passes |
| Offline survivor regression | No early global reveal, sync passes | No early global reveal, sync passes |

Smoke connectivity is the existing diagnostic from the graph available at the end of update; Step 5 refreshes it later in the tick than Step 4. Use the independently sampled physical-connectivity comparison below for matching before/after sampling semantics. The smoke did not collect the full standalone delivery or field-contact probe, so short-run zero counts are not asserted for every long-run tick.

## 16. Before/after communication measurements

Each stage uses the same `step5-physical-observation-v1` harness, seeds 2026/2027/2031, 3,600 ticks each, normal mode, offline autonomy enabled and failure probability zero. Before runs use the hash-verified Step 4 snapshot. The observation probe computes an independent physical range graph at each sensor/sync call. It counts newly global cells/IDs published by physically disconnected sources, including stale cached links. Partition/reconnect durations use an independent post-update graph.

| Communication metric | 2026 before → after | 2027 before → after | 2031 before → after |
|---|---|---|---|
| Physically disconnected sensor events | 400 → 393 | 442 → 452 | 473 → 525 |
| Cells new to the observer while disconnected | 280 → 266 | 433 → 324 | 355 → 392 |
| Disconnected survivor encounters not in local ID list | 16 → 2 | 0 → 0 | 25 → 4 |
| New global map cells leaked while disconnected | 170 → 0 | 118 → 0 | 159 → 0 |
| New global survivor IDs leaked while disconnected | 1 → 0 | 0 → 0 | 1 → 0 |
| Cell additions to offline buffers | 590 → 2373 | 1051 → 2899 | 898 → 2226 |
| Survivor additions to offline buffers | 1 → 2 | 0 → 0 | 1 → 4 |
| New global cells uploaded after reconnect | 109 → 247 | 267 → 315 | 171 → 352 |
| New global survivors uploaded after reconnect | 1 → 1 | 0 → 0 | 1 → 2 |
| Pending-buffer checks, including blocked no-ops | 7 → 4391 | 6 → 5025 | 6 → 6091 |
| Already-global cells in connected uploads | 481 → 2029 | 636 → 2455 | 567 → 1651 |
| Already-global survivor IDs in connected uploads | 0 → 1 | 0 → 0 | 0 → 2 |
| Drone partition transitions | 48 → 57 | 45 → 69 | 51 → 34 |
| Drone reconnect transitions | 47 → 55 | 43 → 66 | 48 → 31 |
| LOST_COMM transitions | 7 → 9 | 8 → 7 | 8 → 11 |
| Longest physical offline interval, ticks | 585 → 479 | 672 → 628 | 651 → 625 |

Counts are not interchangeable: new-local cells are new to that observer's set, not unique across the swarm. Buffer additions can recur across partition cycles and include already-global data unknown to the disconnected sender. Survivor encounters not yet recorded locally can repeat in the old implementation because the global filter suppresses local recording. Uploaded-new counts measure newly published global information, while already-global upload items measure redundant data acknowledged without new discovery credit.

Pending-buffer checks include disconnected no-ops each tick; they are not successful transmissions or bandwidth consumption. Duplicate synchronization *event* counts were not collected separately; redundant item counts and focused repeated-call tests provide the available idempotence evidence. Reconnect and partition events count per-drone transitions, not unique network partitions. No asynchronous traffic, packet loss or bandwidth measurement is claimed.

## 17. Before/after mission and physical connectivity measurements

| Mission/network metric | 2026 before → after | 2027 before → after | 2031 before → after |
|---|---|---|---|
| Physical average connectivity % | 83.43 → 83.72 | 81.74 → 81.43 | 80.41 → 78.08 |
| Physical majority-connected % | 100.00 → 100.00 | 99.31 → 99.31 | 100.00 → 98.11 |
| Physical full-collapse ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Global coverage % | 24.12 → 23.64 | 30.55 → 27.70 | 24.64 → 24.56 |
| Globally discovered survivors | 2 → 2 | 2 → 2 | 3 → 3 |
| Unfinished-task replacements | 0 → 0 | 0 → 0 | 0 → 0 |
| Relay/exploration conflicts | 0 → 0 | 0 → 0 | 0 → 0 |
| Accumulated ownership inconsistencies | 0 → 0 | 0 → 0 | 0 → 0 |
| Final ownership inconsistencies | 0 → 0 | 0 → 0 | 0 → 0 |
| Stranded drone-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Final stranded drones | 0 → 0 | 0 → 0 | 0 → 0 |
| Path searches | 2222 → 1851 | 3038 → 2214 | 3101 → 3478 |
| Frontier completions | 10 → 10 | 11 → 13 | 13 → 15 |
| Actual field point-contact pair-ticks | 0 → 0 | 0 → 0 | 0 → 0 |
| Field charging violations | 0 → 0 | 0 → 0 | 0 → 0 |

All approved ownership invariants and the Step 4 field-contact result remain intact for these runs. Coverage, path counts, connectivity and completed tasks can change because corrected global knowledge changes later planning and allocation inputs; those changes are shown without tuning unrelated policies to compensate. The field-contact definition and docking exception are imported from the unchanged Step 4 probe.

## 18. Step 4 → Step 5 performance

| Seed/stage | Mean ms | p50 ms | p95 ms | p99 ms | Max ms |
|---|---|---|---|---|---|
| 2026 Step 4 | 12.421 | 12.372 | 23.572 | 29.058 | 96.087 |
| 2026 Step 5 | 12.980 | 13.683 | 22.083 | 27.098 | 63.417 |
| 2027 Step 4 | 10.879 | 9.478 | 21.687 | 25.184 | 53.815 |
| 2027 Step 5 | 11.773 | 10.000 | 24.819 | 30.276 | 69.739 |
| 2031 Step 4 | 10.903 | 9.073 | 20.191 | 28.766 | 87.690 |
| 2031 Step 5 | 11.734 | 11.210 | 20.905 | 25.488 | 78.019 |

Mean update changes: **2026: +4.5% (+0.558 ms), 2027: +8.2% (+0.894 ms), 2031: +7.6% (+0.831 ms)**.

Existing coordination cost remains separately visible:

| Seed | Reservation ms/update before → after | Collision gate ms/update before → after |
|---|---|---|
| 2026 | 4.853 → 4.839 | 0.044 → 0.043 |
| 2027 | 4.725 → 5.135 | 0.051 → 0.055 |
| 2031 | 5.293 → 5.468 | 0.056 → 0.058 |

No reservation code was optimized or changed. Differences in its measured cost reflect different mission states/workloads and timing variation. The comparison above uses fresh runs of the same instrumented harness; it does not subtract Step 4's historical closure timings or the older Phase 1 baseline. Timed simulations ran sequentially. A short focused-test process overlapped the before-run implementation window; these are single-run observations with ordinary host scheduling/GC variation, not isolated repeated performance trials.

Latency brackets the actual mission update, excluding post-update physical-event accounting, ownership checks and the Step 4 safety probe. It includes sensor/sync instrumentation and the existing component-timer wrappers. Probe overhead can differ with sync-call frequency, so this is an instrumented incremental comparison, not a precise isolated estimate of production-only communication overhead. The new graph refresh and synchronization checks are real added work; changed trajectories also change A* and reservation workloads. p50/p95/p99/max are retained rather than inferring tail behavior from the mean.

## 19. Reproducibility

Seed 2026 was repeated for 3,600 ticks. **All 29 non-timing fields match**, including the nested communication counters, physical network metrics, mission counters, final state hash and knowledge hash. Both reservation/gate call counts also match. The before runs reproduce every comparable non-timing Step 4 closure field and state hash for all three seeds.

Simulation-state hash (both final Step 5 runs): `1922b572df80b8b6cfd33c62e541a960ce8ee941fccfc4a01b8f26e456d949ae`.

Knowledge hash (both runs): `a913722ef296e7dd5cbfbf54b2c4cc88c30aa5083100bee91f1d8e608778ef57`.

The established state hash covers fog, globally found survivors, weather, drone positions/states/batteries/paths/queues. The additional hash covers each drone's known cells, pending cells, local survivor list, pending survivor IDs, and global fog/found IDs. Neither is a hash of every Python object or a cross-platform guarantee. First/repeat mean latency is 12.980/13.095 ms; timing is excluded from equality. See `reproducibility_check.json` for all comparisons.

## 20. Intentional behavior changes

Delivery is blocked during grace and when offline-autonomy policy is disabled. Both observation and pending-data publication use the post-movement graph in Swarm. Local survivor recording no longer consults global discovery state as an information oracle. Offline survivor alerts wait for upload. Duplicate buffered-cell merges no longer inflate the heatmap. FAILED/STRANDED radios no longer relay. Disconnected base-bus gossip stops and generic outboxes persist until reconnection. Zero connectivity is no longer healthy by default. These changes alter mission trajectories while preserving the existing motion, planning, ownership and collision contracts.

## 21. Remaining confirmed limitations

Radio connectivity is an ideal range graph with instantaneous multi-hop routing, no obstacles/interference/delay/bandwidth, and no separate radio power model. Synchronization is an atomic abstraction. Counters sample graph state in discrete phases rather than integrating radio contact continuously along motion segments. Base-connected map gossip and generic messages retain their periodic broadcast cadence; observation publication is immediate at the sensing/delivery boundary.

The simulator/central allocator still has global geometry, agent state and command authority; task commands are not transported by the radio model. Diagnostic/debug displays can expose ground truth and per-drone private state. UI finder attribution remains based on local survivor lists rather than a first-uploader provenance ledger. This tranche protects operational discovery sets and discovery alerts, not every omniscient simulator/debug surface. Expanding that boundary would require a larger architecture/UI task and was not done.

Offline cell sets discard repeated-visit timing/counts, and local buffers survive power/failure transitions in simulator memory. Generic outboxes have no bounded-capacity/acknowledgment model; current discovery delivery does not depend on that unused generic protocol. Standalone callers must supply a current communication graph. None of these abstractions should be advertised as realistic distributed networking.

## 22. Remaining unverified risks

The tested seeds and fixtures do not establish behavior for every map, fleet size, failure sequence, externally edited pose or platform. Normal benchmarks do not exercise random radio hardware failures. Long-run repeated partition patterns, externally produced unbounded message traffic and replay restoration of all local buffers were not exhaustively tested; replay changes are outside this tranche. Existing Step 4 finite-body, starvation and deadlock limitations remain unchanged. These are coverage limits, not newly reproduced defects or reasons to expand scope automatically.

## 23. Git diff summary

The working tree already contains approved uncommitted Phase 1 and Step 4 work. This scope is compared against `step5_step4_baseline`, not original Git HEAD:

| Source/test/harness file | Added | Removed |
|---|---|---|
| core/communication.py | 29 | 18 |
| core/drone.py | 38 | 21 |
| core/map.py | 1 | 1 |
| core/swarm.py | 11 | 3 |
| benchmarks/step5.py | 150 | 0 |
| tests/communication_tests.py | 295 | 0 |

Production/test/harness subtotal: **524 added lines and 43 removed lines across six files** (four production files, one new test module, one new benchmark). This report and saved Step 5 result artifacts are additional new files. `source_manifest.json` retains baseline/final hashes, and `step5_only.diff` separates this tranche from earlier work. Existing tests, configuration, geometry, reservation implementation, pathfinding, Step 4 benchmark and all other unmodified baseline source files pass preservation checks. `git diff --check` passes. No commit, push or PR was created.

## 24. Accurate claims ADSS can make

ADSS now separates radio reachability, delayed communication policy, local observations and synchronized global discovery. It demonstrates first-disconnected-tick publication gating at the sensing boundary, deterministic reconnect merges, idempotent map/survivor discovery, explicit relay/failure/power assumptions, and reproducible seeded runs. All measured final disconnected publication counts and field point-contact counts are zero, with prior ownership invariants preserved.

It cannot claim realistic RF/packet networking, distributed consensus, a fully decentralized knowledge/planning architecture, lossless temporal scan history, universal collision freedom or exhaustive correctness for all experiments. The report's empirical zero counts refer to the measured fixtures/runs and explicit contract.

## 25. Recommendation and stop boundary

The next original-roadmap candidate is **Step 6 — simulation clock, RNG and configuration**. Recommend separating simulation time from rendering, isolating random streams and making experiment configuration reproducible, with regression baselines that preserve the now-approved contracts. This is a recommendation only. **Step 6 has not started. Work stops after Step 5 validation and this report, pending approval.**

## Evidence and reproduction

Results are in `benchmarks/results/step5/`: `red.txt`, `phase_boundary_red.txt`, `alert_red.txt`, `focused.txt`, `full_suite.txt`, `before.json`, `after.json`, `repeat.json`, `reproducibility_check.json`, and `source_manifest.json`. Partial JSON files are checkpoints, not additional independent experiments. The same benchmark script was copied to the frozen baseline tree before measurement.

Commands: `python -m pytest -q -s`; `python benchmarks/step5.py --label step5-after --output benchmarks/results/step5/after.json`; repeat with `--seeds 2026` and a separate output. The Step 4 snapshot and scoped patch are retained under `local evidence directory` as `step5_step4_baseline` and `step5_only.diff`. Python 3.13.7 / pygame 2.6.1 on the existing Windows host were retained.
