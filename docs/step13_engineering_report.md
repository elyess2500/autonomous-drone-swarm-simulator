# Step 13 engineering closure — UI and presentation

**Manual-QA polish — 2026-10-03.** The menu labels were centered nine pixels above their button centers because `draw_text(anchor="center")` was passed `rect.y + 10`. The one-line production fix passes `rect.centery`; the existing helper centers the actual rendered font rectangle on both axes. Fonts, colors, button bounds and the rest of the layout are unchanged.

Three new parametrized regressions cover all five labels at 1100×760, 1400×850 and 1920×1080, with each selected state and no selection. They also verify unchanged authoritative simulation projections across menu draws. There is no separate hover rendering path. All **23 focused UI cases pass** (the original 20 plus these three), after all three new cases first failed against the old implementation. Other button-style controls were inspected: fleet cards intentionally use two text rows and do not share this single-label center-anchor pattern.

Actual screenshots at all three sizes were inspected; all five selected variants are saved per size. [Updated default menu](evidence/step13/menu_alignment/menu_1400x850_selected1.png). Evidence and current hashes are in `benchmarks/results/step13/menu_alignment/`. Core/config and every other acceptance input remain unchanged. This menu-only coordinate fix does not invalidate the earlier live/replay matrices or 10,800-tick smoke, so they were not rerun. The 333-test full-suite result below is the preserved pre-polish acceptance result, not a newly claimed full-suite run after adding three cases. Original closure manifests remain historical; the polish manifest records the current delta. No Step 14 work, commit or push occurred.

Evidence closure: 2026-10-02.

## 1. Executive summary

Step 13 is complete: the interface now separates mission overview, a selectable fleet/inspector, published map, communication/routes and a small ledger-backed event feed. Replay has an explicit detached identity and seek timeline. Settings ordering and unpublished-survivor presentation defects are fixed.

**333 tests pass**, including all 313 Step 12 cases and 20 new UI cases. Both seven-condition presentation matrices pass; the expanded matrix checks every tick and every render. The real seed-2026 3,600-tick before/after capture runs match exactly across nine authoritative groups. All core modules and config.py remain byte-identical to the frozen baseline. No Step 14/15, commit, push, reset or discarded approved work occurred.

The final sequential acceptance run completed while the conversation was interrupted. Its artifacts and hashes were recovered and verified; expensive completed jobs were not repeated. Remaining closure work only generated this report and checked scope/evidence.

## 2. Frozen Step 12 baseline

Before UI changes, 84 source/test/UI/validation/setup/documentation files were copied and hashed. Step 11 and Step 12 evidence directories were preserved separately, including the 313-test result, bounded golden/repeat and seven-condition presentation results. The freeze location is recorded in `benchmarks/results/step13/baseline_location.txt`; hashes, initial Git status and cumulative diff are in the same Step 13 evidence directory.

Final comparison is against this approved worktree snapshot, not Git HEAD: HEAD also differs from the approved Steps 1–12 work. Original evidence is unchanged. No golden was regenerated.

## 3. Original UI architecture

`main.run_app` owns Pygame initialization, application modes, input, pause/update scheduling and output actions. `ui.presentation` composes live rendering and camera/menu overlays. Dashboard/minimap and detached replay each had render classes/functions; Map/Drone also retain compatibility render methods. `core.simulation.make_simulation` already supplies the independent engine.

An older duplicate `main()` loop was no longer the script entry point. It now delegates to the same supported graphical controller. No engine construction, simulation update, clock, RNG, accounting or replay storage mechanism was redesigned.

## 4. UI audit findings

Working foundations included keyboard navigation, camera follow, pause, offscreen tests, detached replay and authoritative data sources. Baseline captures showed minimap/status/map overlap, very small low-contrast secondary text, bright sensor discs, dense docking/radio diagnostics and no useful selected-drone energy inspector.

Two failing live regressions reproduced settings display order differing from handler order, and survivor markers appearing from terrain revelation without survivor publication. A third failing regression reproduced that same publication leak in replay. The old frontier-debug renderer also showed omniscient survivor information without a clear normal/debug boundary. Fixed-position layout and limited replay controls were usability weaknesses; not every design difference was treated as a simulation bug.

## 5. Baseline screenshots

All baseline images come from a real seed-2026 simulation, not fabricated mission results. They include menu/settings at tick 0, active mission at 60, paths at 180, communication at 360, first returning/charging observation at 538, pause/overlays/dense zoom at 900, first published survivor at 1,794 and completed sampled playback at 3,600.

See [baseline contact sheet](evidence/step13/before_contact_sheet.png) and individual PNGs under `benchmarks/results/step13/before/`. `capture.json` records each represented tick and authoritative state hashes. The privacy regressions separately use deliberate test fixtures with revealed terrain and unpublished survivor knowledge.

## 6. Design goals

Keep the map readable, distinguish key states quickly and make detailed inspection optional. Prioritize published mission information, physical connectivity and modeled energy readiness over raw debugging text. Retain Pygame and existing controller/engine boundaries. Every presentation setting is observational; explicit application actions such as new mission and operator rescue retain their existing meaning.

## 7. Visual system

A small UI-owned palette uses navy backgrounds, slightly lighter panels, off-white primary text, muted secondary text, teal emphasis, amber warnings and rose failures. Consistent section headings, fleet tiles, dividers and spacing replace the default dense debug header. Text and glyphs supplement state colors. Animated weather flashes and discovery particles are no longer part of normal map composition; weather remains visible as information.

## 8. Main layout

Top identity/status, aspect-preserving map, 340-pixel side panel, bounded event area and footer shortcuts form the layout. The side panel can be hidden; the viewport then uses the available area. The minimap moves into a bounded viewport corner and appears when zoom makes navigation useful. Layout rectangles are calculated from actual window dimensions, without changing experiment dimensions/configuration.

## 9. Top/status bar

Shows ADSS identity, controller mode, mission outcome, represented simulation time/tick, seed, shortened experiment identity, weather, zoom and display FPS. The update contract is explicitly labeled “1 tick/update = 1/60 s.” FPS is presentation throughput, not simulation dt or a claim of real-time speed. `I` exposes the full identity in a UI-owned message.

## 10. Simulation viewport

Logical world coordinates remain unchanged. Rendering scales/crops only the view and preserves map aspect ratio. Normal drone labels use constant-size screen text, remain inside the viewport and avoid other normal labels; when a cluster has no available label position, optional text is suppressed while its exact glyph and fleet entry remain available. No positions are moved for visual separation.

## 11. Drone visualization

Drone glyphs use true positions, a selected ring, readable IDs and state labels for selected/exceptional states. `!` indicates physical disconnection, which is independent of delayed LOST_COMM behavior. Selecting a map glyph or fleet tile opens the inspector; right click clears selection. Co-located agents can still share glyph positions by the approved docking contract.

## 12. Drone-state visual language

| State / role | Cue |
| --- | --- |
| IDLE | Muted circle / IDLE |
| SCANNING | Teal diamond / SCAN |
| RETURNING | Amber triangle / RETURN |
| CHARGING | Blue square / CHARGE |
| Departure-ready idle | Blue square / READY |
| Relay anchor | Lavender square / RELAY |
| LOST_COMM | Amber diamond / LOST and radio status |
| FAILED | Rose cross / FAILED |
| STRANDED | Rose square / STRANDED |
| AVOIDING | Lavender triangle / AVOID |

READY and RELAY are derived display labels, not new drone states or policy transitions. Exceptional state labels take precedence over relay decoration. Replay currently labels stored drone states directly; it does not invent missing role/readiness information in old recordings.

## 13. Selected-drone inspector

Shows ID/state, normalized battery percentage, actual physical radio status, role, assigned frontier/sector, target, next waypoint, relay anchor, remaining route/queue counts, last energy decision/charge/reserve/margin, traffic wait/backoff status and counts of pending private cells/reports. It does not reveal private survivor locations.

The inspector reads already-recorded energy diagnostics; it never calls `EnergyPolicy.estimate` or triggers a decision. Values are labeled as last-decision values, not newly recomputed current guarantees. Wheel scrolling over the panel exposes lower rows at minimum height. Fleet pagination supports more than eight entries without pushing the inspector outside the panel.

## 14. Map/world visualization

Unknown space is dark; published terrain distinguishes obstacles, striped no-fly cells and blue wind terrain. Base/shared docking has a square marker and docking radius. Published survivors have S identifiers and diamond markers. Optional scan intensity, frontier/sector, reservation and route layers use existing data; none changes terrain, ownership or route generation.

## 15. Knowledge versus ground-truth handling

Default terrain follows global fog. Survivor markers require membership in globally published `mission_found`, even when surrounding terrain is visible. The same publication rule applies to replay. Frontier display no longer invokes the omniscient survivor-debug routine in the supported live composition.

`G` enables a conspicuous **DEBUG / GROUND TRUTH** mode that reveals the world and labels unpublished markers TRUTH; it is off initially. Normal pending diagnostics show counts only, and the feed excludes local survivor events. Drone positions/states are explicitly **simulator telemetry**, including offline agents, not a physically delivered telemetry-network model. This is a visualization boundary; global/local knowledge and communication policy are untouched.

## 16. Communication visualization

An optional subdued overlay shows actual direct base links plus the existing relay tree, rather than every possible radio edge. Fleet LINK/OFFLINE labels, disconnected map suffixes, relay labels and the inspector distinguish physical connectivity from LOST_COMM policy. No RF behavior, link reliability or delivery timing is invented.

## 17. Task/path visualization

Selected agents show their remaining executable route and target; `T` exposes all routes. `F` displays assigned frontier markers and sector bounds. Inspector fields distinguish frontier, sector and relay work. Reservations and decision strings remain optional diagnostics. The view uses existing path order and waypoint index without planning, smoothing or modifying tasks.

## 18. Energy visualization

Battery is a percentage of that battery's actual capacity. CHARGE versus READY separates charging from waiting to depart. The inspector reports last estimated total charge, configured reserve and signed decision margin, or “No valid route.” Help explains abstract charge units and uncertainty. No joules/physics claim, estimator call, reserve change or energy-policy decision is introduced.

## 19. Mission overview

Coverage, globally published survivors, task completions and unavailable counts come from the existing analytics sample; physical connectivity and charging counts are derived directly from current drones. Outcome comes from Mission. No duplicate cumulative counters or animated approximations become a source of truth. Survivor rescue remains unsupported, and no rescue count is fabricated.

## 20. Event feed

Displays at most three recent selected records from the existing bounded accounting ledger: publication, task completion/cancellation, energy return, charging/readiness, departure, partition/reconnect, LOST_COMM entry, backoff/blockage, failure/stranding and mission completion. Each uses the stored simulation tick and actor.

Local survivor observations and high-volume collision waits are excluded from the normal feed. There is no new journal, event consumption, synthetic event, increment or simulation mutation. This is a filtered recent view, not a complete incident log or guaranteed persistence of an important event on screen.

## 21. Controls

Start/demo/menu, pause/resume, explicit new mission, export/load and operator rescue remain controller actions. New selection, dashboard/event/minimap/debug toggles and identity/help are UI-owned. No speed multiplier was added: active application cycles retain fixed simulation updates. Pause, resize and quit-while-paused are covered by a controller fixture.

Replay output errors and export paths are shown as UI messages instead of being written into swarm alerts. `main()` now delegates to `run_app()` so callers use one controller. Automatic camera follow on discovery and demo presentation remain existing behavior; neither changes drone decisions.

## 22. Keyboard shortcuts

| Input | Action |
| --- | --- |
| P / Escape | Pause/resume / pause then menu |
| M / R | Menu / new mission |
| E / L | Export / load latest replay |
| Arrows or WASD; +/- or wheel | Pan; zoom (wheel over inspector scrolls it) |
| Space / Q | Follow next / reset camera |
| C / T / F / S | Links / all routes / work / sensors |
| H / V / D | Heatmap / reservations / decisions |
| B / J / N / G | Dashboard / events / minimap / DEBUG ground truth |
| I / ? or F1 | Full identity / help |
| [ / ] | Fleet page |
| Y | Existing explicit operator rescue; changes live state, disabled in replay |
| Replay Home / Left / Right | Restart playback / seek backward or forward one second |
| Settings arrows, Enter, 1–9 | Select, toggle, direct first-nine toggles |

## 23. Camera/navigation

Preserves the existing smoothed camera and zoom bounds. Screen/world inverse transforms match the camera's integer crop and zoom-out letterboxing. Selection uses those transforms and a screen-space pick radius. Reset clears pan/zoom/follow; minimap clicks center/clamp the target view. Camera state lives in UI and consumes no simulation RNG. This is pan/zoom navigation, not arbitrary camera projection support.

## 24. Settings

A single ordered `SETTINGS` definition drives both labels and controller keys. Eleven presentation choices include dashboard, feed, minimap and explicit ground truth. The screen states that the active experiment is immutable and these controls affect presentation only. It does not pretend to offer experiment editing or silently mutate global experiment values. The last two entries use arrows/Enter rather than nonexistent two-digit key shortcuts.

## 25. Replay UI

Detached playback has its own PLAYBACK header, playhead/time, represented snapshot tick, weather/publication count, stored drone-state list, progress/seek bar and completed status. Home and Left/Right/click seeking call the existing `ReplayPlayer.seek` API. P controls playback pause through the controller; R explicitly starts a new mission.

The view holds sampled snapshots between samples and discloses a recorded prefix when export extends beyond it. It never applies snapshots into live objects, resumes live simulation, restores checkpoints or changes the storage schema. End-of-replay remains completed; seeking is an explicit viewer action.

## 26. Legend/help

A bounded operator guide explains map symbols, publication/debug boundaries, radio versus simulator telemetry, selection/navigation, controls, replay, abstract charge units and operator rescue. It is available through ?/F1 during live/replay presentation. It does not intercept simulation decisions or implement a new mission policy.

## 27. Window-size/responsive behavior

Validated 1100×760, default 1400×850 and 1920×1080. Resize enforces a minimum 1100×760 without changing `config.py` or experiment identity. The viewport scales with aspect preserved, sidebar stays bounded, inspector scrolls, and the event area/footer remain separate. Menus/overlays center against the actual surface. This is tested-size support, not arbitrary DPI/resolution certification.

## 28. Text/number formatting

Coverage uses one decimal; battery uses integer percent; connectivity uses connected/total; time is mm:ss from fixed ticks; energy uses one decimal with explicit charge/margin labels. Identity is shortened in the header and available in full through I. Target/waypoint coordinates appear only in detailed inspection. Width-aware text truncation and bounded fleet/detail areas prevent long values from claiming adjacent panels.

## 29. Color/accessibility decisions

State shapes and text supplement color; failed/stranded/return/relay/ready differ visibly. Palette calculations recorded in `visual_qa.json` give primary text/background contrast 16.17:1 and secondary text/panel 7.71:1; warning/danger text on the main panels also has strong calculated contrast. These are palette calculations, not whole-application accessibility certification, color-vision user testing or hardware display measurements.

## 30. UI architecture boundaries

New composition/adapters live in `ui/console.py`; `ui.presentation` retains the public render entry and delegates normal live composition. Controller selection, help, scrolling, fleet page, error message and visible widget rectangles live on the presentation-owned Dashboard object. Existing Dashboard/Minimap and core render helpers remain as compatibility code; no UI field was added to an authoritative drone/swarm/map object.

The engine still imports no UI through its supported headless path. Pygame may be imported by legacy render-capable core modules; graphical initialization is still unnecessary for simulation execution.

## 31. Presentation-only derived data

Layout rectangles, formatting, state styles, filtered event tuples, inspector rows and transforms are calculated without writing core state. No policy queries are cached/skipped or newly invoked. Existing analytics are queried purely; energy uses stored diagnostics. Global presentation random draws remain independent of simulation-owned streams. Optional debug visibility changes pixels, not what agents know or do.

## 32. Production files changed

| File | Purpose |
| --- | --- |
| main.py | Single controller entry; resize, selection, new UI toggles, shared settings order, UI messages and replay input |
| ui/presentation.py | Delegate live drawing; shared settings; centered overlays/menu and contrast adjustments |
| ui/replay_view.py | Published-only detached viewer, timeline, existing-API seek controls |
| ui/console.py (new) | Pure presentation adapters/layout/map/fleet/inspector/events/help |

**No `core/*` or `config.py` changes.** Pathfinding, allocation, radio, collision/reservations, energy/cache, success/outcome, accounting, fixed clock/RNG and replay storage remain unchanged. Existing `ui/dashboard.py` and `ui/minimap.py` are also unchanged.

## 33. Tests added/modified

Added `tests/ui_tests.py`: 13 test functions yielding 20 collected cases through parametrization. Coverage: settings/handler order; live and replay unpublished-survivor regressions; three layout sizes; four camera zoom transforms/picking/reset; public/debug survivor adapter; state/energy formatting without estimator queries; bounded nonconsuming events; detached seeking; three observer scenarios; presentation-only settings; compatibility controller; pause/resize/quit-while-paused.

All tests are explicitly STANDARD/graphical. Every existing Step 12 test file is byte-identical, including acceptance thresholds. `benchmarks/step13.py` adds scenario capture, isolated rendering timings and the expanded per-tick matrix. Existing validation/harness code and goldens are unchanged.

## 34. Focused UI-test result

**20/20 UI cases pass**. The final focused job combines them with 45 preserved replay/persistence cases: **65 passed**, zero failures/errors/skips in 29.655 s (JUnit timing). Earlier tranche runs passed 2 then 10 combined checks; red artifacts preserve two live failures and one replay failure before fixes.

## 35. FAST result

**282 passed** in 42.638 s. This is the unchanged FAST selection, with other tiers explicitly deselected. It is not a full-suite claim.

## 36. STANDARD result

**50 passed** in 66.967 s: 30 preserved additions plus 20 UI cases. Together with FAST, all 332 non-heavy tests pass. These sequential tier timings are separate from full-suite time.

## 37. HEAVY/full-suite result

**333 passed**, zero failures/errors/skips. Pytest console time is 472.60 s; JUnit measures 472.566 s. The only warning is the already documented Pygame/pkg_resources deprecation. All 313 prior node IDs are present and passing. The HEAVY smoke ran within this full suite; it was not needlessly repeated.

## 38. 10,800-tick smoke result

PASS. Seed 2026 smoke takes 368.806 s including setup/call/teardown. Coverage 1.24% → 50.49%; survivors 5/5; relaunch succeeds; no final stranded, stuck zero-battery returning, or LOST_COMM drones. Average connectivity 78.7%, majority-connected fraction 99.9%, full-collapse ticks zero.

Forced recovery succeeds with maximum lost streak 827. The 29-cell offline buffer synchronizes to zero pending; survivor knowledge is private before sync and public afterward. No field-charging violation; zero emergency recoveries. Captured output exactly matches Step 12. No simulation speedup is inferred from shorter test-suite wall time.

## 39. Deterministic/golden result

Approved compact golden comparisons pass at every tick through tick 60 for seeds 2026, 2027 and 2031. The original golden checksums/projection remain unchanged. Step 13 newly executes this bounded gate; it does not claim a newly repeated full three-seed 3,600-tick release differential. Prior approved long-horizon evidence remains preserved and the release command remains available.

## 40. Seed-repeat result

Each of the three bounded seed runs was repeated. Covered trace/final state, knowledge, RNG, experiment identity, accounting, metrics, summary, outcome, replay and CSV repeat fields match exactly. The seed-2026 3,600-tick capture before/after comparison provides an additional same-policy long-horizon check; it is distinct from the bounded three-seed repeats.

## 41. Presentation-independence result

The established seven-condition 180-tick matrix passes (headless, normal 60/30/144 FPS settings, reduced render frequency, overlays off, presentation noise). All nine final authoritative groups match.

The expanded seven-condition 180-tick matrix additionally varies 1100×760/1400×850/1920×1080, camera pan/zoom, rotating selected drones, inspector scroll, all UI toggles including DEBUG ground truth, dashboard/event/minimap visibility, help and unrelated presentation RNG. Every tick's authoritative projection matches its headless reference; every render is bracketed by an exact mutation check. Each condition exercises three hardware failures and six weather changes. FPS settings do not sleep/pacing-benchmark a real display.

Replay seek/draw isolation is covered separately by focused fixtures and preserved replay presentation tests, rather than pretending a live matrix is a replay test.

## 42. Replay/persistence result

All 45 preserved replay cases pass in focused and complete runs, including schema validation, private/public snapshots, atomic/unique persistence, timing and detached state. New replay privacy and seek-isolation cases pass. No checkpoint continuation, schema change, live-state application or automatic live resume was added.

## 43. Headless result

Cold `validation.sanity` passes with graphical initialization/input/Surface/Clock and UI/main imports forbidden. The existing longer headless tests also pass in STANDARD/full/reverse runs. New presentation modules are not imported by the supported engine entry point. Dependencies did not change.

## 44. Test-isolation result

All **332 non-heavy cases pass in reverse order** in 102.430 s. Preserved process cleanup restores config/RNG/environment and Pygame lifecycle. All final acceptance jobs use the previously clean Step 12 pinned venv with third-party pytest plugin autoload disabled; no dependency reinstall was needed because requirements/pins are unchanged. This is bounded order coverage, not exhaustive permutation proof.

## 45. Rendering-performance methodology

Before/after capture runs use the same seed-2026 configuration and real final tick 3,600 state. Each render mode has five warm-up calls followed by 30 `perf_counter` samples. Inspection occurs outside the timer; no simulation update, disk save or display flip is included in these render samples. Measurements run sequentially, separately from acceptance tests.

Modes: normal links; overlays off; all seven original overlays; and dense zoom 1.8 with overlays. UI composition intentionally differs: the new inspector is selected, while the old UI lacked it, and removed default diagnostic/omniscient drawing is not identical visual work. These are representative UI costs, not a controlled proof of an algorithmic optimization or hardware-independent speed guarantee. The baseline capture precedes the later responsive/matrix harness additions; no baseline simulation policy changed.

## 46. Rendering-performance results

| Mode | Version | Mean ms | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- | --- |
| normal | Step 12 | 8.146 | 7.990 | 9.102 | 9.404 | 9.513 |
| normal | Step 13 | 6.939 | 6.869 | 7.334 | 7.497 | 7.564 |
| off | Step 12 | 6.801 | 6.642 | 7.628 | 8.051 | 8.194 |
| off | Step 13 | 6.931 | 6.831 | 7.325 | 7.471 | 7.530 |
| overlays | Step 12 | 27.748 | 27.548 | 32.610 | 34.250 | 34.559 |
| overlays | Step 13 | 7.870 | 7.875 | 8.299 | 8.420 | 8.429 |
| dense | Step 12 | 24.900 | 23.815 | 31.325 | 31.938 | 31.943 |
| dense | Step 13 | 9.142 | 8.426 | 11.865 | 12.597 | 12.735 |

Normal/major-overlay/dense rendering is lower in this observation; overlays-off mean is slightly higher. Do not generalize a single short timing trial into a causal or universal speedup claim. The simulation was not optimized to compensate for the UI.

Separately, the existing 180-tick **headless update** samples from the presentation validation are:

| Run | Mean ms | p50 | p95 | p99 | Max |
| --- | --- | --- | --- | --- | --- |
| step12 | 17.083 | 8.713 | 24.084 | 166.387 | 683.954 |
| step13 | 11.754 | 5.898 | 13.100 | 112.594 | 484.165 |

These short-horizon update observations are not combined with render times, and are not new clean 3,600-tick simulation benchmarks. Core source is unchanged; different host timing cannot establish that UI work made the engine faster.

## 47. Manual visual-QA methodology

Actual generated PNGs were inspected through the image viewer at full/native and contact-sheet scale, including three supported sizes, selected inspection, normal operational map, extreme overlays/debug, help and detached playback. Matched baseline categories come from the same real simulation ticks; no favorable state was manufactured.

Automated semantic/controller tests exercise geometry and input behavior. This visual review is not a claim of human usability studies or physical mouse/keyboard/hardware testing. `visual_qa.json` records findings, limitations and palette contrast calculations.

## 48. Manual visual-QA findings

The overlapping minimap/status block is removed. Mission overview and selected detail are visually separated. The minimum-height inspector discloses scrolling; the tested large layout maintains bounded panels. Replay clearly labels playback/completion and exposes a timeline. Settings ordering is consistent and its explanatory text has improved contrast. Normal map labels avoid each other and remain inside the viewport.

Optional all-decision text can still overlap at a dense shared dock. World-layer labels can be cropped by camera edges. Co-located glyphs retain their real position, and the fleet list is the alternate selection surface. These known cosmetic limits do not justify expanding this tranche.

## 49. Before/after screenshots

| Category | Tick | Step 12 | Step 13 |
| --- | --- | --- | --- |
| 01_menu | 0 | [Before](evidence/step13/before/01_menu.png) | [After](evidence/step13/after/01_menu.png) |
| 02_active | 60 | [Before](evidence/step13/before/02_active.png) | [After](evidence/step13/after/02_active.png) |
| 03_paths | 180 | [Before](evidence/step13/before/03_paths.png) | [After](evidence/step13/after/03_paths.png) |
| 04_communication | 360 | [Before](evidence/step13/before/04_communication.png) | [After](evidence/step13/after/04_communication.png) |
| 05_survivor | 1794 | [Before](evidence/step13/before/05_survivor.png) | [After](evidence/step13/after/05_survivor.png) |
| 06_energy | 538 | [Before](evidence/step13/before/06_energy.png) | [After](evidence/step13/after/06_energy.png) |
| 07_paused | 900 | [Before](evidence/step13/before/07_paused.png) | [After](evidence/step13/after/07_paused.png) |
| 08_replay | 3600 | [Before](evidence/step13/before/08_replay.png) | [After](evidence/step13/after/08_replay.png) |
| 09_overlays | 900 | [Before](evidence/step13/before/09_overlays.png) | [After](evidence/step13/after/09_overlays.png) |
| 10_dense | 900 | [Before](evidence/step13/before/10_dense.png) | [After](evidence/step13/after/10_dense.png) |
| settings | 0 | [Before](evidence/step13/before/settings.png) | [After](evidence/step13/after/settings.png) |

[Before contact sheet](evidence/step13/before_contact_sheet.png) · [After contact sheet](evidence/step13/after_contact_sheet.png)

Additional evidence: [minimum size](evidence/step13/after/size_1100.png), [default size](evidence/step13/after/size_1400.png), [1080p size](evidence/step13/after/size_1920.png), [operator guide](evidence/step13/after/help.png), [small debug matrix](evidence/step13/matrix_small.png). Original PNGs and per-capture state records remain available. Selection is new presentation state; it never changes the represented simulation.

## 50. Confirmed UI bugs fixed

Red → green evidence exists for settings order and unpublished-survivor markers in live/replay views (`ui_red.txt`, `replay_ui_red.txt`). The supported normal frontier composition no longer calls omniscient survivor-debug display. Visual evidence confirms minimap/header overlap removal; bounded layout tests protect the replacement. Camera reset now actually resets pan as well as follow/zoom. Resize, inspection, explicit debug labeling and seeking improve previously limited capabilities rather than being described as policy bugs.

## 51. Simulation behavior-equivalence evidence

All nine authoritative groups match at the end of the seed-2026 3,600-tick before/after runs, and all eleven shared screenshot state/tick records match. They cover state, knowledge, simulation RNG, experiment identity, accounting, metrics, summary, outcome and completion reason. Expanded per-tick/around-render projections additionally cover reservations/recovery and energy diagnostics via the unchanged Step 11 projector.

The full smoke output matches Step 12 exactly. Core/config, old tests, goldens and old benchmark projectors are byte-identical. No policy/cadence/reserve/collision/radio/accounting threshold was changed or relaxed. Exact evidence covers these configurations and horizons, not every possible future UI interaction or custom world.

## 52. Git diff/source validation

Final closure verifies all 70 acceptance input hashes and all 84 frozen baseline hashes, unchanged Step 11/12 evidence, preserved test inventory, matrix/capture equivalence and source scope. New production code is only `ui/console.py`; the only changed existing production files are `main.py`, `ui/presentation.py`, `ui/replay_view.py`. Tests/harness/report/evidence are separate.

The scoped executable/test/harness diff is six files, **+839 / -365 lines**: main +62/-230; presentation +29/-110; replay view +59/-25; new console +338; new tests +201; new harness +150. This report and local closure/evidence files are listed separately by the final manifest. Counts are against frozen Step 12, not cumulative HEAD.

`git diff --check` and scoped whitespace/EOF checks include new files; final results and hashes are in `final_closure_checks.json` and `final_artifact_hashes.json`. No commit/push/reset/discard or Step 14/15 work occurred.

## 53. Remaining UI limitations

Dense optional decision strings may overlap; shared docking glyphs may coincide; some cropped world labels remain partial. The replay list discloses additional rows rather than implementing a full paginated replay inspector. Current playback labels stored states directly, so live derived READY/RELAY presentation is richer. The event feed is intentionally filtered and short, not a full journal browser.

Old Dashboard/Minimap/core render helpers and UI debug helpers remain compatibility code; the new publication/label/layout contract applies to the supported live console and detached viewer, not arbitrary direct calls to legacy helper methods. The UI is simulator instrumentation, not a realistic received telemetry client. No experiment editor, speed multiplier or arbitrary-resolution guarantee was added.

## 54. Remaining unverified risks

Hosted GitHub CI and Linux runtime remain unverified; neither was a prerequisite and no push was performed. Other DPI settings, platforms/fonts, large-swarm manual usability and physical display/input accessibility have not been certified. The bounded matrices do not exhaust all input sequences or custom map/configuration shapes. Short rendering samples are susceptible to host load and font/cache effects; they are not frame-rate guarantees.

## 55. Accurate UI/presentation claims

ADSS now provides a clearer supported Pygame operator interface with published-survivor boundaries, explicit debug ground truth, useful selected-drone energy/task/radio inspection, filtered authoritative events, responsive tested-size layout and detached seekable sampled playback. Exact tests demonstrate observer-only rendering under the exercised conditions and preservation of approved simulation outcomes.

It cannot claim received-telemetry realism, exhaustive absence of visual overlap, accessibility certification, arbitrary DPI support, real-time performance, checkpoint continuation, or untested hosted/platform success.

## 56. Recommendation for Step 14

Review Step 13 and approve Step 14 separately. For the later experimental/research tranche, start with explicit questions, recorded configurations, repeated seeds and the existing headless/metrics/differential contracts; avoid treating attractive screenshots or short render timings as scientific evidence. Define that tranche's scope before implementation. No research framework, experiment campaign, Step 14 or Step 15 was started here.
