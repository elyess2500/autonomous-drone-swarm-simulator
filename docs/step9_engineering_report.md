# Step 9 engineering closure: incremental headless/rendering separation

Scope: Step 9 only. Steps 1–8 remain approved and preserved. No Step 10 implementation.

## 1. Executive summary

ADSS now exposes simulation construction through `core.simulation.make_simulation`, independently of `main` and the UI package. Rendering helpers have moved to `ui.presentation`; the existing application imports compatibility aliases. The factory, render helpers and both application loops retain their original function/class bodies. This is structural extraction, not new simulation behavior.

**Step 9 is complete: 14 focused cases and all 249 suite tests pass.** The 10,800-tick gameplay smoke passes with unchanged approved behavior. Three fresh 3,600-tick before/after runs, the 2026 repeat and all seven presentation conditions match the compared authoritative state exactly. The standalone engine runs without graphical initialization or UI imports; Pygame remains an imported dependency in compatibility drawing helpers.

Only three production files are in this tranche. Simulation update timing was observationally higher in the fresh trial (pooled mean 12.966 -> 13.500 ms); no causal overhead or speedup is claimed. Rendering and display-flip timings are reported separately. No production changes were made during closure, and Step 10 has not begun.

## 2. Original architecture/dependency audit

| Component/dependency | Classification | Before Step 9 and disposition |
| --- | --- | --- |
| `main.make_simulation` → Experiment, Map, Swarm, Mission | Simulation-domain construction in application module | Extracted unchanged to `core.simulation`; old import remains supported |
| Importing the old factory → dashboard, minimap, replay viewer | Accidental coupling | Removed from supported engine import path; reproduced with an import blocker |
| `main` → Pygame initialization, display, events, keys, frame limiter | Application/controller | Retained; both controller bodies unchanged |
| `main` → Camera, Particle, draw helpers, live frame composition | Presentation-only implementation in controller | Extracted unchanged to `ui.presentation` |
| Mission → Swarm, world, clock, environment, metrics, accounting | Simulation-domain | Unchanged; one forward update is one fixed tick |
| Swarm → Drone, planner, communication, reservations, ownership | Simulation-domain | Unchanged |
| Map → NumPy arrays, world generation, discovery | Simulation-domain | Unchanged |
| Map → Pygame, tile surface/cache, drawing methods | Retained mixed concern | Imported, but no surface is constructed until drawing requests it |
| Drone → Pygame, state colors, draw methods and trail data | Retained mixed concern | Drawing stays optional; no graphical initialization in construction/update |
| `core.utils` → math plus fonts/drawing | Retained mixed concern | Font handles are created only when presentation requests them |
| Analytics/Accounting → query, event and sampled state | Simulation-domain and export | No UI dependency; unchanged semantics |
| Mission → replay capture, CSV logger, filesystem outputs | Persistence/export | Existing eager recording and output-directory behavior retained |
| ReplayPlayer → detached recorded state; replay viewer → Pygame | Persistence versus presentation | Existing separation retained; viewer does not need a live mission |
| Dashboard/minimap → surfaces, fonts, animation and camera state | Presentation-only | Never constructed by engine entry point |
| `pygame.init()` including possible audio initialization | Application lifecycle | Only application-controlled; cold headless tests forbid mixer initialization too |
| Screen dimensions, UI animation frames, presentation Clock | Presentation/controller | Remain outside headless progression; core draw helpers still reference presentation configuration |

No previously hidden simulation dependence on display initialization was found. The old factory could already execute 300 ticks without it; its **import location and UI dependencies** were the confirmed structural defects.

## 3. Accidental dependencies reproduced

Before production edits, two focused regressions failed: importing simulation construction while blocking `ui`, and importing rendering while blocking `main`. A third test forbidding graphical initialization while advancing 300 ticks already passed. `red.txt` records **2 failed, 1 passed**. This distinguishes unnecessary imports from an execution defect that did not exist.

## 4. Final engine/application/presentation contract

The engine creates experiments and owns world/drone state, fixed simulation time, RNG streams, mission updates, accounting, outcome and persistence-facing state. It requires neither input nor rendering.

The application owns Pygame lifecycle, menus, pause, input, camera controls, live/replay selection and scheduling update/render calls. Presentation draws the supplied state and may change presentation-local animation/cache state. It must not advance or author simulation behavior. No new framework, engine superclass, event loop or scheduling model was introduced.

## 5. Supported headless API

```python
from dataclasses import asdict
from core.experiment import ExperimentConfig
from core.simulation import make_simulation

world, swarm, mission, seed = make_simulation(
    2026, experiment_config=ExperimentConfig.capture())
for _ in range(3600):
    mission.update()

metrics = asdict(mission.analytics.sample(mission))
accounting = swarm.accounting.snapshot()
outcome = mission.outcome
summary = mission.summary()
replay_path = mission.export_replay()  # Optional explicit export.
```

No SDL dummy driver, `pygame.init()`, `Surface`, dashboard, camera or presentation clock is required. `benchmarks/step9.py` provides a small sequential measurement entry point; it is not a research framework.

## 6. Simulation construction semantics

The factory returns the existing `(Map, Swarm, Mission, resolved_seed)` tuple. It accepts an explicit seed and immutable `ExperimentConfig`; omission retains the established seed/config resolution. Construction runs inside the experiment's configuration context. The original `main.make_simulation` is an alias to the same factory, so existing callers retain their contract.

CSV creation and in-memory replay sampling remain enabled as before. Output directories remain runtime configuration. Writers open/close files per operation; there is no engine thread, display or persistent output handle to shut down. Export desired artifacts, then release the objects. This is not a newly introduced resource manager.

## 7. Simulation stepping semantics

`mission.update()` retains the fixed 1/60-second forward tick. The caller determines how many updates to request. Pause means not requesting forward updates. Explicit benchmark updates can continue after mission success; the established final summary/duration remain frozen. An attached replay player retains the existing detached-playback update path rather than advancing live simulation.

Presentation FPS controls application wall-clock pacing, not the state associated with an equal number of simulation updates. No catch-up scheduler or real-time throughput guarantee was added.

## 8. State/metrics inspection API

Use the returned domain objects for world/drone inspection, `mission.analytics.sample(mission)` for a pure metrics snapshot, `swarm.accounting.snapshot()` for detached accounting, `mission.outcome`/`completion_reason`, and `mission.summary()` for running/frozen final summary. Query tests check that modifying returned summary/accounting dictionaries cannot change authoritative state. Domain objects themselves remain mutable; this is not a read-only object system.

## 9. Rendering observer contract

The validation captures state before and after each measured draw. It checks recorded world/drone/swarm state, knowledge, RNG streams, accounting/event hash, all metrics, outcome and summary. Camera, particles, dashboard animation, minimap caches and Map's lazy tile surface/dirty flag may change. They are presentation state, excluded from behavioral comparison.

The hash covers explicit recorded fields plus world and simulation RNG state, not every Python attribute. Current renderer observation is tested, rather than enforced through a capability/security boundary.

## 10. Pygame dependency status

Pygame remains an installed and imported dependency of `core.map`, `core.drone` and `core.utils`, including type annotations and compatibility drawing helpers. **The core is not Pygame-free.** The supported execution path requires no graphical initialization or presentation objects. Cold subprocess tests block initialization, surface creation, fonts, mixer, presentation Clock and input polling, and remove dummy SDL environment variables.

## 11. UI dependency status

Importing and running `core.simulation` requires neither `main` nor any `ui` module. A cold-process import hook enforces this, and the standalone three-seed benchmark checks loaded modules and Pygame initialization flags on completion. Importing `ui.presentation` does not import the application/controller.

## 12. Replay boundary

Step 7 sampled playback remains detached. A focused test records headlessly, loads the replay, renders without advancing its playhead or changing the live mission, deletes the live mission, and continues rendering/seeking the player. Replay schema, timeline, export validation and end behavior are unchanged. Checkpoint restoration and deterministic continuation remain unsupported.

## 13. Metrics/accounting boundary

Step 8 files and semantics are unchanged. Headless and graphical conditions compare full metrics, ledger counts/hash, outcome, completion reason and summary. Rendering emits no simulation events in these checks. Rescue remains unsupported; success remains 98% coverage OR all nonempty survivor zones globally published; no terminal-failure policy was invented. Charging-state entries remain distinct from relaunches, and proximity episodes remain distinct from field contacts.

## 14. Batch experiment behavior

The cold-process fixture runs 2026/2027/2031/2026 sequentially for 300 ticks each. Between instances it deliberately completes the previous mission, emits an extra accounting event and attaches replay playback. The next mission still starts at tick zero, RUNNING, with fresh replay/accounting state. Repeated seed state matches; the three seeds have distinct experiment identities/state hashes.

An additional interleaved pair uses different configuration snapshots and verifies context restoration and equality against a fresh reference. Global Python/NumPy random state is unchanged by headless simulation. Concurrent threaded execution is not claimed or introduced.

## 15. Production files changed

| File | Change |
| --- | --- |
| `core/simulation.py` | New documented supported factory/API location; factory body copied unchanged |
| `ui/presentation.py` | Camera, particles, screen/overlay helpers and live-frame renderer extracted unchanged |
| `main.py` | Imports those definitions as compatibility aliases; controller bodies unchanged |

No other existing production file changes in Step 9. All 18 original top-level definitions compare AST-identical across their new locations, including both controllers; see `extraction_check.json`.

## 16. Tests added

`tests/headless_tests.py` adds 14 cases: two import boundaries; 300-tick forbidden-initialization execution; 360-tick cold inspection/CSV/replay/termination; sequential experiments and configuration isolation; compatibility aliases/detached queries; six presentation observer/equality variants; independent replay rendering; actual application Start/Pause/Resume/Quit smoke.

The actual-controller fixture preserves the existing boot mission followed by a new Start Mission instance and expects normal `SystemExit(0)` on quit. Test assumptions were corrected for those existing behaviors; no production fix was needed.

## 17. Focused test results

**14 passed, 1 dependency warning in 26.84 seconds.** The warning is Pygame's existing deprecated `pkg_resources` dependency. No focused production regression remained. See `focused.txt`.

## 18. Complete suite and smoke results

**249 passed, 1 existing dependency warning in 293.24 seconds (4:53).** The completed result was recovered from `full_suite.txt`; no redundant rerun was performed. This includes all 235 preserved tests and 14 new Step 9 cases, with no weakened thresholds.

The unchanged seed-2026 gameplay smoke ran **10,800 ticks**:

| Check | Result |
| --- | --- |
| Coverage | 1.24% -> 51.64% |
| Survivors globally found | 4/5 |
| Recharge/relaunch | Passed |
| Empty-battery returning / stranded / final LOST_COMM drones | None / none / none |
| Average connectivity | 74.1% |
| Majority-connected fraction | 99.7% |
| Minimum connected drones | 4/8 |
| Full communication-collapse ticks / recorded collapse events | 0 / 0 |
| Forced LOST_COMM recovery | Passed; longest streak 805 ticks |
| Offline map discoveries | 29 buffered and hidden before reconnect; all synchronized, zero pending afterward |
| Offline survivor | Hidden globally before reconnect; published afterward; one synchronized report |
| Offline charging outside docking zone | None in map/survivor fixtures |

The complete suite preserves movement, A*, task ownership, reservation/collision fixtures, communication/privacy and radio eligibility, clock/RNG/configuration isolation, detached replay/persistence, and accounting/outcome contracts. The new scripted application smoke also passes. The long smoke is not an independent continuous-contact probe; the separate 3,600-tick runs report zero existing-ledger field contacts.

The final production/test/harness manifest matches all five current files. The only changes after the focused/benchmark runs were a single trailing blank-line removal in each new production module; restoring that CRLF reproduces their earlier byte hashes exactly, and ASTs are identical. Cleanup occurred before the saved full-suite run completed. All 38 other captured baseline paths remain byte-identical. These provenance checks are recorded in `closure_validation.json`.

## 19. Headless validation results

Cold processes execute 300 and 360 ticks with graphical services forbidden and no dummy SDL drivers. The 360-tick fixture checks exactly six elapsed seconds, six CSV rows with final tick 360, matching replay/accounting/metrics, no initialized display/font/mixer and no created tile surface. All three standalone 3,600-tick runs and the 2026 repeat finish with `main`/UI absent and Pygame still uninitialized.

## 20. Graphical validation results

All six rendered variants use the native `windows` display driver with a hidden display-backed window, not a dummy SDL driver. Every measured draw passes the observer comparison. The scripted real application loop checks Start Mission, pause without tick progression, resume, and normal quit. These are automated execution checks, not a claim of human visual QA.

## 21. Headless/render equality matrix

Seed 2026, 180 simulation ticks per condition, failure probability 0.003, weather interval 30 ticks. Every run records **3 hardware failures and 6 weather changes**. All nine state groups match, with zero before/after-draw changes.

| Condition | Draw calls | Display | State / knowledge / RNG / experiment | Accounting / metrics / outcome / reason / summary |
| --- | ---: | --- | --- | --- |
| headless, 60 nominal FPS | 0 | none | Equal | Equal |
| normal, 60 nominal FPS | 180 | windows | Equal | Equal |
| normal, 30 nominal FPS | 180 | windows | Equal | Equal |
| normal, 144 nominal FPS | 180 | windows | Equal | Equal |
| reduced, 60 nominal FPS | 26 | windows | Equal | Equal |
| overlays_off, 60 nominal FPS | 180 | windows | Equal | Equal |
| noisy, 60 nominal FPS | 180 | windows | Equal | Equal |

The nominal FPS is passed through presentation/application configuration; matrix runs intentionally do not sleep to cap frame rate. They test equal-tick state semantics, not monitor refresh or achieved display FPS. The actual controller is exercised separately with scripted input.

## 22. Multi-experiment isolation results

The sequential 2026/2027/2031/2026 fixture passes, including deliberately contaminated previous instances and interleaved configuration contexts. Three 3,600-tick experiments also run sequentially through the supported factory in one process; repeated 2026 in a fresh process matches all nine authoritative comparison groups. No leaked mission completion, replay state, RNG state, accounting state or configuration context was observed.

## 23. Step 8 → Step 9 simulation performance

Milliseconds per simulation update:

| Seed | Version | Mean | p50 | p95 | p99 | Max |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2026 | Step 8 | 10.567 | 10.892 | 16.275 | 23.811 | 56.011 |
| 2026 | Step 9 | 10.759 | 10.985 | 17.144 | 26.617 | 60.473 |
| 2027 | Step 8 | 15.350 | 15.496 | 27.185 | 34.677 | 78.943 |
| 2027 | Step 9 | 15.980 | 16.351 | 27.587 | 36.377 | 104.540 |
| 2031 | Step 8 | 12.981 | 13.730 | 21.504 | 29.865 | 53.222 |
| 2031 | Step 9 | 13.761 | 13.947 | 24.348 | 33.955 | 95.667 |

Observed mean differences: 2026: +1.82%, 2027: +4.11%, 2031: +6.00%. The equal-length pooled mean is 12.966 -> 13.500 ms. This trial is slower; the extraction adds no simulation update operation, so the measurements alone do not establish a causal overhead. No speedup is claimed.

Methodology: fresh frozen Step 8 source versus current Step 9, identical `step9-uninstrumented-update-v1` probe, seeds 2026/2027/2031, 3,600 forward ticks each, failure probability zero, independent sequential runs on this Windows host. `perf_counter` surrounds `Mission.update` only; final hashing is outside timing. Existing CSV and sampled replay costs remain included. No tests run concurrently with these trials.

These are single trials per seed, not a statistical performance study. OS scheduling and filesystem effects remain uncontrolled. An earlier development-concurrent trial is retained as `before_during_development.json` but excluded from the comparison. Do not mix these timings with Step 8's older sensor/contact-instrumented benchmark results. No algorithm optimization or performance improvement is claimed.

## 24. Separate rendering/application performance

Milliseconds per draw (separate from simulation update):

| Mode / nominal FPS | Draws | Mean | p50 | p95 | p99 | Max | Mean display flip |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| normal / 60 | 180 | 24.288 | 23.751 | 29.643 | 34.140 | 40.019 | 0.033 |
| normal / 30 | 180 | 23.045 | 22.715 | 27.235 | 29.966 | 34.132 | 0.031 |
| normal / 144 | 180 | 23.072 | 22.801 | 26.689 | 29.723 | 30.568 | 0.029 |
| reduced / 60 | 26 | 27.287 | 26.462 | 34.252 | 36.390 | 36.959 | 0.029 |
| overlays_off / 60 | 180 | 5.272 | 4.854 | 8.745 | 9.690 | 11.894 | 0.027 |
| noisy / 60 | 180 | 23.138 | 22.929 | 27.333 | 29.858 | 31.394 | 0.031 |

All display-flip percentiles/maxima are retained separately in `presentation_matrix.json`. Reduced rendering performs 26 draws rather than 180; its per-draw cost is not a per-tick simulation cost.

Drawing measurements include camera update and live-frame composition, including dashboard/minimap/overlays when enabled. Display flip is timed separately. They exclude construction, particle creation, event dispatch, FPS sleep and state-hash validation. This measures representative rendering/application components, not total interactive application latency; hidden-window compositor behavior may differ from a visible foreground application.

## 25. Reproducibility results

Before/after: **zero differences across all nine authoritative groups for each of three seeds**. The separate 2026 repeat matches all nine groups. Every presentation condition also matches all nine groups, including full metric/accounting dictionaries and final/running summary, not just hash prefixes. See `reproducibility_check.json` and full JSON artifacts.

| Seed | State hash (prefix) | Knowledge hash (prefix) | Event hash (prefix) |
| --- | --- | --- | --- |
| 2026 | `e2f9e7bab923a82a` | `2fd4af695f2a41fa` | `f2ece15a163b2249` |
| 2027 | `92fab3397ec5bdb3` | `1e246af110a5dadb` | `6dc9b9ecffa7ca52` |
| 2031 | `495c0bd7df0a73af` | `983ad1c7d6152bb1` | `4f10c63eab87eb85` |

The Step 9 state hash covers the sampled frame, persisted world and explicit simulation RNG states. Knowledge has its own hash. Experiment identity retains Step 6's seed/config/RNG-version meaning and does not hash source code. This probe is broader than older benchmark hashes; compare only like methodology. No cross-platform floating-point or all-possible-state equivalence claim is made.


The fresh before/after mission samples also agree exactly:

| Seed | Coverage % | Local / published survivors | Tasks award / complete / cancel | Path searches | Ledger field contacts | Outcome |
| --- | ---: | --- | --- | ---: | ---: | --- |
| 2026 | 25.526 | 2 / 2 | 27 / 12 / 9 | 2435 | 0 | running |
| 2027 | 28.479 | 2 / 2 | 40 / 21 / 14 | 3384 | 0 | running |
| 2031 | 21.839 | 3 / 3 | 28 / 11 / 12 | 1038 | 0 | running |

These are existing ledger/sample metrics. This uninstrumented timing harness does not independently resample disconnected-publication or ownership violations; their focused regressions remain in the complete suite. Historical independent Step 8 probe results are not relabeled as new Step 9 measurements.

## 26. Intentional behavior changes

Only supported import locations and module ownership change. There are no intentional changes to trajectories, simulation timing, ownership, collision/communication policies, outcomes, accounting, replay or UI appearance. Old `main` imports remain usable. The headless path now avoids application/UI imports entirely.

## 27. Remaining architectural coupling

Map/Drone retain drawing helpers, colors, trails and visual caches; `core.utils` still mixes math and drawing. Presentation reads runtime layout configuration and domain objects directly. The application retains its legacy duplicate loop and boot-time mission creation. Existing benchmark entry points may still import `main` for compatibility. These are explicit incremental-separation limits, not new correctness findings requiring expansion of this tranche.

## 28. Remaining confirmed limitations

Pygame must be installed even for headless operation. Construction still creates CSV output and allocates replay recording; no no-op sink framework was added. The observer boundary is conventional/tested, not immutable access enforcement. Dropping an experiment does not automatically export its in-memory replay. Render layout for arbitrary configurations is not newly generalized. Replay remains sampled playback only.

## 29. Remaining unverified risks

Other platforms, Pygame versions, physical display drivers, very long repeated application restarts and concurrent threaded experiments were not exhaustively exercised. Future renderer code could mutate an uncovered domain attribute; field-based hash tests are not exhaustive serialization. Interactive human visual inspection and real monitor pacing are not established by hidden-display/scripted checks. These are verification limits, not reproduced regressions.

## 30. Git diff summary

Scoped comparison is against the frozen approved Step 8 working tree, not Git HEAD (which still contains earlier uncommitted tranches).

| File | Added lines | Removed lines |
| --- | ---: | ---: |
| `main.py` | 18 | 593 |
| `core/simulation.py` | 39 | 0 |
| `ui/presentation.py` | 583 | 0 |
| `tests/headless_tests.py` | 279 | 0 |
| `benchmarks/step9.py` | 138 | 0 |
| `docs/step9_engineering_report.md` | 299 | 0 |

Production scope: **3 files, +640 / -593**, principally relocated definitions. With tests and benchmark: **5 files, +1,057 / -593**, with this report: **6 files, +1,356 / -593**. Saved validation artifacts are additional evidence. The scoped patch includes the report; generated measurements/logs are evidence, not production changes.

All 38 other captured baseline paths retain their original hashes, including configuration, every preserved test, all prior core modules, dashboard, minimap, replay viewer and existing benchmarks. All 18 original top-level definitions remain AST-identical. Final manifests and checks are saved alongside the scoped patch. EOF-only whitespace cleanup changed no AST or behavior; its before/after hashes are recorded separately.

`git diff --check`: **exit 0**. Its only output is the existing `core/map.py` LF/CRLF normalization notice. A separate normalized scoped check covers the new/untracked files too, with no whitespace diagnostics. No simulation policy, analytics/accounting architecture, replay schema, RNG/clock model, UI appearance, reservation optimization or Step 10 work was changed.

## 31. Accurate architectural/headless claims

ADSS can construct, advance, inspect, record and run sequential experiments through a supported engine import without graphical initialization, UI construction, a display, input polling or a presentation clock. Current rendering preserves the compared authoritative state under the tested conditions. The extracted implementation preserves the approved simulation bodies and contracts. ADSS cannot claim zero Pygame imports, a strictly immutable renderer interface, checkpoint continuation or universal platform-independent determinism.

## 32. Recommendation for the next roadmap step

The original Step 10 is route-aware energy and coherent autonomy. If separately approved, begin with focused evidence for route/wind/weather-aware energy feasibility versus the current distance/battery policy, retain the established ownership/collision/communication boundaries, and measure policy changes. Recommendation only: **Step 10 has not begun.**

## Evidence and reproduction

Artifacts: `benchmarks/results/step9/`. Frozen Step 8 source: `external frozen baseline (step9_step8_baseline)`. The frozen source received only the common benchmark probe after capture. Python 3.13.7 / Pygame 2.6.1 on the existing Windows host.

```text
python -m pytest tests/headless_tests.py -q
python -m pytest -q -s
# In frozen Step 8 source, output to the current evidence directory:
python benchmarks/step9.py --entry legacy --ticks 3600 --seeds 2026 2027 2031 --output before.json
# In current source, run sequentially:
python benchmarks/step9.py --ticks 3600 --seeds 2026 2027 2031 --output benchmarks/results/step9/after.json
python benchmarks/step9.py --ticks 3600 --seeds 2026 --output benchmarks/results/step9/repeat.json
python benchmarks/step9.py --matrix --ticks 180 --seeds 2026 --output benchmarks/results/step9/presentation_matrix.json
```
