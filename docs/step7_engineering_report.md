# ADSS — Step 7 engineering report

Date: 2026-09-28. Scope: P0/P4 replay and persistence correctness. Steps 1–6 remain approved. Step 8 has not begun.

## 1. Executive summary

ADSS now saves versioned, self-contained **sampled playback** files and plays them through a detached view. Loading no longer combines recorded drones with another live world, changes the live simulation clock, or silently resumes forward execution. Checkpoint restoration and deterministic continuation are explicitly unsupported. Output publication is atomic, generated names are unique, and explicit replay paths require explicit overwrite.

The full suite passes **202 tests**, preserving all 157 approved cases and adding 45 replay/persistence cases. All six playback matrix conditions match, including different initially constructed worlds, headless/rendered playback and changed FPS/render frequency. All **33 non-timing forward benchmark fields** match before versus after for all three seeds and match the independent seed-2026 repeat. Recording overhead and persistence costs are reported separately below.

## 2. Original replay defects reproduced

The initial 12 regressions all failed on unchanged Step 6. Loading a seed-2026 recording into seed 999 left seed-999 map/fog/world active while replacing some drone fields. The v1 file contained no world or configuration from which to correct this. One playback update applied the next sample; the default six-tick sample spacing therefore jumped six simulation ticks per application update. Loading then playback mutated the live clock, weather, positions, states, batteries and selected metrics while leaving paths, ownership, buffers and most other state live.

At the last sample the playback flag was cleared, and the next normal update resumed an inconsistent hybrid world. Validation only required a root dictionary with a `frames` key. Empty, unknown-version and wrong-type payloads could be accepted until later failure or silently interpreted. These were confirmed defects, not reasons to replace the simulation architecture.

## 3. Original persistence/output defects reproduced

CSV and default replay filenames used second-resolution timestamps plus seed. Same-seed/same-second creation reused paths and `open(..., 'w')` truncated previous content. Explicit replay saves overwrote existing files without an explicit overwrite argument. Serialization wrote directly to the destination, so a failed write left a partial final JSON artifact. These cases have saved failing tests in `red.txt`.

Later validation found and reproduced acceptance of boolean drone ID `False` as ID zero; IDs now require actual integers. A byte-retention test also proved that export could append a later snapshot after the recorder stopped. Recording now latches its stopped state; exported-prefix extent remains truthful. Their evidence is in `focused_nested.txt` and `retention_red.txt`.

## 4. Terminology

**Playback** displays stored sampled state on a separate timeline. **Checkpoint restoration** would reconstruct executable simulation objects at a stored tick. **Deterministic continuation** would additionally guarantee that future updates match the original run from that checkpoint. This implementation supports only the first. Seeking to a stored view is not a checkpoint, and restarting a fresh mission is not continuation.

## 5. Final replay contract

Replay is immutable-by-public-API sampled-state playback. A payload contains a static world and snapshots of published/private state. The player owns a validated deep copy; `world`, `configuration` and `current` return detached copies. Nothing is applied to the live Map, Swarm, Drone, Experiment or SimulationClock. The renderer consumes only replay data and never calls live drone/map/swarm behavior.

Tick zero is recorded. Normal snapshots retain the configured six-tick cadence; export includes the current tick when retention is still available. Between snapshots, the viewer holds the preceding state and labels its recorded tick. It does not invent interpolated positions, events, discoveries or collision behavior. Explicit API seeking is supported within the recorded interval; no new seek-control UI was added.

## 6. Schema/version contract

JSON root `version: 2`, `kind: "adss.sampled-playback"`, capability flags `playback=true`, `checkpoint=false`, `continuation=false`, `tick_hz: 60`, and sampling model `hold-previous-snapshot` identify the format. Required data includes experiment metadata, static world, nonempty increasing-tick snapshots, recorded-through tick and export tick. Runtime metadata records Python and NumPy versions.

Validation checks version/type/capabilities, experiment identity, dimensions and terrain values, zone bounds, drone IDs/states/positions/battery bounds, paths/queues, encoded mask lengths, survivor IDs, communication data, required ownership/statistics fields and timeline structure. JSON duplicate keys, non-finite numbers, malformed/truncated text and incompatible kinds/versions are rejected. Validation completes before a loaded player replaces any existing player. Legacy v1 is rejected with an explanation because missing world/private state cannot be recovered truthfully. There is no pickle, arbitrary object deserialization or silent migration.

Files are limited to 128 MiB, 262,144 map cells and 18,001 snapshots. The recorder also respects the configured frame limit and a 64 MiB canonical-frame retention budget. Once retention stops, it remains stopped. The file distinguishes the retained prefix from the later export tick, and the viewer labels a shortened prefix. These are retention/resource limits, not a promise that arbitrary untrusted input has negligible parsing cost.

## 7. Experiment/config metadata

The Step 6 canonical experiment payload is embedded: resolved seed, RNG scheme version, configuration schema, fixed tick rate and complete captured settings, plus its SHA-256 identity. Loading reconstructs the immutable configuration representation and recalculates the identity; seed/config tampering that leaves the identity unchanged fails validation. The target live mission may have a different seed/configuration because the player uses the saved values exclusively.

Experiment identity remains the Step 6 configuration/seed identity; it is not a signature of file authenticity, source code or every Python object. Runtime versions are provenance, not a cross-version continuation guarantee. CSV files have a versioned metadata sidecar carrying experiment identity/configuration, tick rate and the associated CSV basename; row `frame` values identify sample ticks.

## 8. World/map playback

The file embeds grid dimensions, terrain grid, zone geometry and survivor ground truth. The player never regenerates a world. The app's existing menu setup can construct an unused live mission before opening a replay; that mission remains parked and is never used as the playback world. Per-snapshot fog and heatmap are stored as explicit base64 encodings: little-bit-order packed fog and little-endian int16 heatmap. Global discovered survivor IDs are stored separately. The player retains the map's actual recorded values, including the existing heatmap dtype semantics; this tranche does not redefine heatmap analytics.

World geometry is static within this recording format. Export detects edits to terrain/zone geometry after recording began and fails with an actionable error instead of pairing earlier frames with a different world. Start a new recording for an edited scenario. Changes to fog, heatmap and discovery state are represented in snapshots.

## 9. Drone/swarm state playback

Snapshots include drone positions/velocities, current/previous states, battery level/max/charging, path/waypoint/scan queue, targets, sector/frontier IDs, relay role/anchor/lease, selected recovery and scan timers, task assignments, sector ownership/bounds/completion, frontier descriptions and cumulative swarm diagnostics. Mission state, statistics and full metric values are copied without changing their existing calculations.

Reservation tick and aggregate conflict/wait/backoff counters are recorded as diagnostic projections. Reservation claims, forecast internals, committed movement endpoints and recovery-controller maps are not restored. The player does not perform planning, allocation, movement, collision checks, charging or discovery. Recorded paths and private data remain inspectable through `current`; the minimal viewer displays terrain/fog, discovered survivors, drone states/positions/batteries, weather and timeline labels rather than pretending to run the full live dashboard.

## 10. Communication and local knowledge

Each snapshot stores direct/relay node IDs, contact age and signal quality; local known map cells; pending offline map cells; local survivor IDs; pending survivor IDs and pending survivor metadata; offline status and synchronization counters. Local/pending cell masks use the same documented bit encoding as fog. Tests retain a pending discovery that is absent from global state and verify its exact round trip.

Playback reads this information without delivering messages, merging discoveries, rebuilding radio graphs or changing live connectivity. Generic message inbox/outbox queues and full offline path/scan event history are not checkpointed. Step 5 delivery policy remains untouched. Recorded private knowledge is diagnostic replay data, not a publication event in the live mission.

## 11. RNG handling

The resolved seed and RNG derivation version are metadata. PRNG internal states are deliberately not saved/restored for this playback-only format. No new simulation RNG or random-stream architecture was introduced. A focused test checks that load, seek and playback leave every existing live experiment stream and drone AI RNG state unchanged. Output UUIDs use system randomness, separate from simulation RNG streams.

## 12. Timing semantics

One `ReplayPlayer.advance()` represents one 1/60-second timeline tick, capped at the final recorded tick. `current.frame` identifies the last actual snapshot at or before that playhead. For example, the initial snapshot is held at ticks 1–5 and the tick-six snapshot appears at playhead six. Snapshot spacing is not mistaken for playback speed. The original live Mission clock never advances during playback.

The app calls one playback advance per running loop, matching the Step 6 explicit-update contract. Pausing skips advances. Different presentation FPS affects wall-clock throughput, not the state/timeline after equal advance counts. This is not an automatic real-time accumulator or video-rate guarantee. Rendering can be disabled or called at any frequency without changing the player timeline.

## 13. End behavior

At the last recorded tick, status becomes `completed`; further advances do nothing. The mission remains in replay mode, so subsequent updates cannot fall through into live execution. `R` explicitly creates a new mission; loading another replay creates a fresh detached player. Pausing, returning to the menu and rendering the completed view do not resume the original live objects. Interactive rescue commands are blocked while replay is active. Failed menu replay loading returns to the menu instead of silently starting a new live run.

## 14. Checkpoint/continuation non-support

`restore_checkpoint()` and `resume_live()` explicitly raise `NotImplementedError`; checkpoint/continuation payload kinds/capabilities are rejected. No restored executable state is exposed. Deterministic continuation needs considerably more than the Step 6 seed/configuration: current RNG positions, AI RNG state, object ownership references, reservation claim/backoff/controller state, all task/recovery/negotiation timers, communication queues, analytics accumulators, history used by policy and controller lifecycle state. These are spread across several modules.

Reconstructing and validating that object graph would be a separate architecture tranche. Re-running from seed was not substituted for restoration. This decision meets the approved conservative scope: truthful playback rather than an unverified resume claim.

## 15. Output uniqueness and atomic writes

Generated replay and CSV names contain UUID4 suffixes. Existing explicit replay paths raise `FileExistsError` unless `overwrite=True` is provided. Publication writes a temporary sibling, flushes and fsyncs it, then atomically links it to a new destination without clobbering; explicit overwrite uses `os.replace`. Temporary files are cleaned up on failures. Parent directories are created explicitly. The tested NTFS host supports the required hard-link operation; unsupported filesystems fail safely rather than falling back to a racy overwrite.

CSV header creation is atomic and exclusive. Each unique CSV has one writer; a row update publishes the prior complete contents plus the new row by atomic replacement. This avoids a partially appended visible final row. It costs a whole-file rewrite and does not implement a new analytics/event architecture. Metadata creation failure removes that instance's newly created empty CSV header.

Atomicity applies per file. CSV plus metadata is not a multi-file transaction; a process crash can leave an orphan header or temporary file. fsync is not a portable guarantee of directory-entry durability through sudden power loss. Multiple simultaneous writers to the same CSV are unsupported; separate logger instances receive separate names. Failure tests verify prior artifacts remain unchanged and no partial new final JSON is published.

## 16. Production files changed

| File | Purpose |
|---|---|
| `core/persistence.py` | Shared unique names, atomic file publication and JSON serialization. |
| `core/replay.py` | Explicit playback schema/capture/validation, bounded decoding and detached player. |
| `core/mission.py` | Record tick zero and sampled state; truthful retention/export; delegate load/update to detached playback. |
| `core/analytics.py` | Unique atomic CSV I/O and metadata sidecar; reject legacy incomplete export; delegate validated replay loading. Metric calculations are unchanged. |
| `ui/replay_view.py` | Minimal renderer of saved world/state only. |
| `main.py` | Route replay to its view, advance it independently of live completion, prevent rescue/live fall-through, and handle failed menu loading. |

Movement, A*, ownership, collision/reservation algorithms, communication policy, experiment clock/RNG architecture, configuration and previously approved tests remain unchanged. No Step 8 metrics redesign or research experiment was started.

## 17. Tests added

`tests/replay_tests.py` adds **45 cases**, grouped around identity/config/schema round trips and mismatch rejection; different-world playback; public/private map and survivor state; drone state/path/battery snapshots; one-tick pacing; live-state/RNG isolation; EOF and unsupported continuation; seek/reload behavior; headless/rendered/FPS variants; unique same-second outputs; explicit overwrite; directory creation; malformed/truncated/duplicate-key data; invalid nested types/ranges; atomic serialization/publication/CSV failure; snapshot alias prevention; and frame/byte retention limits.

The initial 12-case failing evidence is preserved. The boolean-ID and retained-tail failures were reproduced before their scoped fixes. No existing test was weakened.

## 18. Focused results

The initial corrected suite passed 12/12. The expanded preserved-plus-new focused run passed 197 tests before the final additions. The final replay-specific suite passed **45 tests in 7.89 seconds**. All final additions also run in the complete suite below. Dedicated logs distinguish the initial red cases, nested-validation failure, retention failure and passing final focused run.

## 19. Complete suite and smoke

Final command: `python -u -m pytest -q -s`. **202 passed in 233.31 seconds**, with only the existing pygame/pkg_resources deprecation warning. Source hashes bind this result to final production code and confirm every prior test file is preserved.

```text
frames=10800
coverage_end=0.5164
survivors_found=4/5
relaunch_succeeded=True
stranded=[]
connectivity_min_connected=4/8
connectivity_avg_ratio=0.741
connectivity_majority_ratio=0.997
connectivity_full_collapse_frames=0
forced_lost_comm={'recovered': True, 'max_lost_streak': 805, 'final_state': 'returning', 'frames_since_contact': 0, 'recovery_label': 'base (timeout)'}
offline_autonomy={'was_offline_autonomous': True, 'offline_cells': 29, 'unsynced_before_reconnect': 29, 'pending_after_sync': 0, 'synced_cells_visible': True, 'comm_mode': 'SYNCING', 'field_charging_violation': False}
offline_survivor={'survivor_idx': 4, 'detected_offline': True, 'global_before_sync': False, 'global_after_sync': True, 'synced_survivors': 1, 'field_charging_violation': False}
```

The smoke retains its original thresholds and exercises docking/relaunch, communication recovery, the 29-cell offline map buffer and survivor synchronization. The long smoke is not instrumented with every standalone contact/delivery probe; measured zero-contact/publication claims below refer to the three benchmark runs and dedicated fixtures.

## 20. Replay validation matrix

One seed-2026 recording spanning 180 ticks and 31 snapshots was loaded and advanced under six conditions. FPS is a presentation setting; dummy-driver software surfaces use the actual detached viewer.

| Initial live seed | FPS setting | Render every N advances (0 = headless) | Final playhead / snapshot | Hashes/timeline match | Live unchanged |
|---|---|---|---|---|---|
| 2026 | 60 | 0 | 180 / 180 | True | True |
| 999 | 60 | 0 | 180 / 180 | True | True |
| 999 | 60 | 1 | 180 / 180 | True | True |
| 999 | 30 | 1 | 180 / 180 | True | True |
| 999 | 144 | 1 | 180 / 180 | True | True |
| 999 | 60 | 7 | 180 / 180 | True | True |

Every condition matches world hash, full sampled-state hash, fog/heatmap/global-survivor hash, experiment identity and the entire sequence of playhead/state hashes. The full sampled-state hash includes private knowledge and drone/swarm projections. The private-buffer unit fixture independently verifies pending offline discoveries. Matrix world hash: `53daec196315f8505c97f56d430d71b2fd523bcf5ec322eff36827a282d655ac`. Timeline hash: `2925417d593f0b058fa2cfcb48aa3aa6e1f45df5ff2202f742fbc684d2cc2a15`.

## 21. Before/after correctness

| Reproduced issue | Step 6 | Final Step 7 |
|---|---|---|
| Seed-2026 replay in seed-999 context | Recorded drones over live seed-999 world | Saved world/state used; live world untouched |
| Default six-tick sampling | One sample, approximately six ticks per update | One timeline tick per advance; prior snapshot held |
| Playback EOF | Flag cleared; next update resumes live | Completed detached view remains active |
| Same-seed/same-second outputs | Collision/truncation | Unique exclusive publication |
| Explicit existing replay path | Silent overwrite | Error unless overwrite explicitly requested |
| Serialization failure | Partial final artifact | No new partial final artifact |
| Unknown/missing schema | Weak acceptance | Validated rejection before player replacement |

Normal forward behavior is unchanged for the measured seeds:

| Seed | Coverage % before = after | Survivors | Physical avg / majority % | Path searches | Contacts / leaks / ownership violations |
|---|---|---|---|---|---|
| 2026 | 25.526 | 2 | 78.43 / 100.00 | 2435 | 0 / 0 / 0 |
| 2027 | 28.479 | 2 | 82.08 / 98.03 | 3384 | 0 / 0 / 0 |
| 2031 | 21.839 | 3 | 85.50 / 100.00 | 1038 | 0 / 0 / 0 |

Full communication-collapse ticks and stranded drone-ticks also remain zero in all three runs. The comparison checks all available non-timing fields, not just this compact table.

## 22. Step 6 → Step 7 performance

Fresh sequential runs after final tests, same Step 6 harness and Step 5 contact/delivery instrumentation, seeds 2026/2027/2031, 3,600 ticks, failures disabled, offline autonomy enabled:

| Seed/stage | Mean ms | p50 ms | p95 ms | p99 ms | Max ms |
|---|---|---|---|---|---|
| 2026 Step 6 | 10.366 | 10.687 | 15.747 | 19.533 | 53.453 |
| 2026 Step 7 | 10.577 | 10.782 | 17.006 | 23.895 | 97.530 |
| 2027 Step 6 | 14.902 | 15.175 | 26.395 | 31.909 | 83.280 |
| 2027 Step 7 | 15.421 | 15.574 | 26.862 | 34.256 | 80.110 |
| 2031 Step 6 | 12.305 | 13.245 | 20.204 | 23.802 | 50.844 |
| 2031 Step 7 | 12.795 | 13.952 | 21.800 | 30.123 | 70.495 |

Mean changes: **2026: +2.0% (+0.212 ms), 2027: +3.5% (+0.519 ms), 2031: +4.0% (+0.490 ms)**. Normal forward recording is enabled in both stages. The added copied/encoded state and canonical byte accounting add work on sample ticks; CSV publication performs whole-file replacement once per simulation second. Rendering is excluded; existing probe overhead is included. These single runs characterize observed incremental cost, not a statistically isolated attribution. No reservation construction or unrelated performance system was optimized. Exploratory before timings are retained separately and excluded from this table.

Separate 180-tick recording cost: 1,061,108 bytes, **76.595 ms** save (validation, encoding, fsync/publication), **57.978 ms** load/validation. Detached player construction including file load/validation/deep copy ranged **93.414–106.725 ms**. Mean advance cost ranged **0.0043–0.0114 ms**, excluding rendering and matrix hash/copy checks. Larger files will have different costs; these are not constant-time or maximum-size benchmarks.

## 23. Reproducibility

All **33 non-timing fields** match Step 6 before versus Step 7 after for every benchmark seed, including experiment/configuration identity, state/knowledge hashes, communication counters and collision/task counters. Reservation component call counts match as well. A separate seed-2026 final run matches those same fields.

Final established state hash: `f9e960c453c5210473b8f9c6ba0b6b05bcc826792d6c5b601ab9c8c9021b2553`.

Final established knowledge hash: `036b750d4c7e3c68400e6a6a18120819cebe775587a75f9569e198c8be6d2d88`.

Equal playback advance sequences yield equal recorded timelines in every matrix condition. This is reproducible **playback**, not deterministic continuation from restored state. Filenames intentionally differ through UUID uniqueness.

## 24. Remaining confirmed limitations

Playback is sampled with hold-last-state semantics, so it does not show every intermediate movement or event, and cannot establish continuous collision safety from replay alone. World geometry is static per recording. Retention limits can preserve only a prefix and are explicitly represented. The viewer is intentionally smaller than the live dashboard; stored paths/private knowledge are inspectable data, not fully recreated live overlays. Visual inspection of the saved matrix image confirmed the recorded-world view and completed-timeline labels; labels on closely clustered drones can overlap, a known limitation of this minimal viewer.

There is no checkpoint or executable resume, no RNG-state restoration, no v1 migration, no multi-file transaction and no multi-writer CSV protocol. The format preserves selected counters/timers and existing statistics rather than correcting their meaning; metric/event semantics remain Step 8 work. Interactive playback speed in wall time still depends on the application's render-loop pacing, under the Step 6 equal-tick contract. Atomic row replacement can become expensive for very long CSV files. Experiment identity is not cryptographic content authenticity.

## 25. Remaining unverified risks

Maximum-sized files, long-retention memory use, arbitrary valid configuration combinations, hostile resource-exhaustion inputs, concurrent writers to one path, network filesystems and abrupt power-loss durability are not exhaustively tested. File-size/dimension limits and structured validation reduce accidental failure modes but do not constitute a hardened untrusted-file sandbox. Cross-version/schema migration requires explicit future handling. No cross-platform or checkpoint-continuation guarantee follows from the current matrix.

## 26. Git diff summary

Prior approved work remains uncommitted in the same checkout. This scope is compared with the frozen Step 6 snapshot, not original Git HEAD:

| File | Added | Removed |
|---|---|---|
| core/analytics.py | 27 | 28 |
| core/mission.py | 52 | 68 |
| main.py | 27 | 2 |
| core/persistence.py | 40 | 0 |
| core/replay.py | 256 | 0 |
| ui/replay_view.py | 35 | 0 |
| tests/replay_tests.py | 258 | 0 |
| benchmarks/step7.py | 61 | 0 |

Scoped source/test/harness total: **756 additions and 98 deletions across 8 files**, plus this report and result artifacts. All prior test and unrelated source hashes match. `git diff --check` passes. No commit, push or PR was created. The standalone diff is `step7_only.diff` in the task artifact directory.

## 27. Accurate claims ADSS can make

ADSS supports versioned, self-contained sampled-state replay with embedded experiment/world metadata, recorded public/private discovery state, explicit tick pacing, detached playback, API seeking and stable end behavior. It rejects the tested malformed/incompatible files, avoids silent output overwrite, and publishes complete artifacts atomically on the supported local filesystem. Its tested forward trajectories and all approved regression contracts remain preserved.

It does not support restored executable checkpoints, deterministic continuation, video recording, complete per-tick event history, replay-derived continuous safety proofs or universally crash-durable distributed storage. The empirical claims are scoped to the saved fixtures, seeds and supported host.

## 28. Recommendation and stop boundary

The original roadmap's next tranche is **Step 8 — P0/P1: Metrics, events, and mission outcome**. Recommend beginning with hand-calculated event/accounting fixtures, idempotent metric sampling, explicit completion/failure policy and consistency between final summaries and persisted output. This is a recommendation only. **Step 8 has not begun. Step 7 work stops pending approval.**

## Evidence and reproduction

Evidence is under `benchmarks/results/step7/`: initial and later red logs, focused/full-suite logs, before/after/repeat JSON, replay matrix JSON/PNG, source manifests and `reproducibility_check.json`. Partial files are checkpoints, not independent trials. The frozen Step 6 source and scoped diff are under `local evidence directory`.

Commands: `python -m pytest -q -s`; `python benchmarks/step6.py --output benchmarks/results/step7/after.json` (repeat adds `--seeds 2026`); `python benchmarks/step7.py --output benchmarks/results/step7/replay_matrix.json`. Run the same forward harness in the frozen Step 6 source for before. Python 3.13.7 / pygame 2.6.1 on the existing Windows host were retained.
