# Step 12 engineering closure — reliability, environments and CI

Evidence date: 2026-10-01.

## 1. Executive summary

Step 12 is complete. **313 tests pass**: all 302 approved tests plus 11 infrastructure checks. The simulation source is unchanged. The long gameplay smoke, headless boundary, presentation independence, bounded approved-golden comparison and repeat checks pass in a fresh pinned environment.

The new reliability system has measured FAST/STANDARD/HEAVY selections, strict classification and collection audits, portable deterministic references, diagnostic failure artifacts, isolated test state, documented installation and local commands, and two GitHub Actions workflows. FAST passed 282 cases in 43.252 s; STANDARD additions passed 30 in 69.207 s. The full suite passed in 530.599 s.

Local workflow checks passed. **No GitHub-hosted run or Linux runtime success is claimed.** No push, commit, reset, discarded work, simulation optimization or Step 13 work occurred.

## 2. Frozen Step 11 baseline

The approved Step 11 source was copied before changes to the external directory recorded in `benchmarks/results/step12/baseline_location.txt`. Its 52 source/test/harness/setup/report files were SHA-256 hashed. All Step 11 evidence was copied, including the 302-test closure, 10,800-tick smoke, timing/profile data, differential traces, repeat and presentation results. Initial Git status/diff are saved separately. Nothing under the Step 11 evidence directory was overwritten.

Step 12 evidence lives under `benchmarks/results/step12/`. The freeze was also used for the original-duration run, ensuring later test-infrastructure edits could not alter that measurement.

## 3. Reliability audit

The existing suite provided substantial coverage but no tier selection, CI, pinned test installation or portable approved-reference bundle. All tests ran together; one smoke dominated runtime. `requirements.txt` used open lower bounds, pytest was undeclared, and the developer environment contained many unrelated packages/plugins.

Two legacy test modules assigned config values at import: `battery_docking_tests.py` and `gameplay_smoke.py`. Failing cold-import regressions reproduced these mutations. They are now local test fixtures/standalone entry-point settings. Rendering tests also leave presentation state initialized by design; test-boundary cleanup now closes it and clears cached fonts. That was a lifecycle risk found by inspection, not a newly claimed simulation bug.

Other risks included repository-relative default CSV/replay destinations, Pygame font handles surviving shutdown, global RNG/environment/cwd modifications, and benchmark scripts whose evidence directories contained developer-specific paths. Production headless construction already worked and did not require redesign.

## 4. Dependency and environment audit

| Component | Validated value | Role |
| --- | --- | --- |
| CPython | 3.13.7 | Reference interpreter |
| OS | Windows 11 x64, build 26300 | Local reference machine |
| Pygame | 2.6.1 | Runtime/render package; import permitted headlessly |
| NumPy | 2.3.4 | Runtime arrays/RNG |
| setuptools | 80.9.0 | Pygame pkg_resources provider |
| pytest | 8.4.2 | Tests |
| PyYAML | 6.0.3 | Validation/workflow parser |
| pip | 25.3 original; 25.2 clean venv bootstrap | Installer, not runtime behavior |

Runtime external imports are Pygame and NumPy; other simulator imports use the standard library/local modules. PyYAML and pytest are development dependencies. UI surfaces/fonts, display/input and presentation clocks belong to graphical paths; cold engine execution requires none. `SDL_VIDEODRIVER`/`SDL_AUDIODRIVER` affect graphical tests only. `PYTEST_DISABLE_PLUGIN_AUTOLOAD`, `PYGAME_HIDE_SUPPORT_PROMPT` and `ADSS_FAILURE_DIR` are documented validation settings.

CSV/replay defaults are `logs/` and `replays/`; pytest redirects them to temporary directories. Seeds/configuration are explicit in deterministic tools; ExperimentConfig remains unchanged. Benchmark/evidence scripts are not imported by CI except the named reusable benchmark harnesses.

## 5. Original test-suite timing profile

The frozen baseline passed **302 tests in 489.501 seconds** with per-case JUnit durations and pytest duration reporting. Saved artifacts: `baseline_suite.xml`, `baseline_suite.txt`, `baseline_durations.json`.

Measured original phase totals by proposed classification: FAST 274 cases / 41.525 s; STANDARD 27 cases / 67.060 s; HEAVY 1 case / 378.972 s. Wall time includes collection/setup overhead. The reference host also performed light editing/install work; these observations guide tiers, not performance guarantees or claims of simulation speed changes. The old Step 11 20:55 full-suite result is preserved, not used to claim a Step 12 speedup.

## 6. Slowest tests

| Original test | Seconds |
| --- | --- |
| tests/gameplay_smoke.py::test_gameplay_smoke | 378.972 |
| tests/headless_tests.py::test_sequential_headless_seeds_and_config_context_do_not_leak | 15.162 |
| tests/headless_tests.py::test_cold_engine_inspection_csv_replay_and_clean_termination | 4.266 |
| tests/headless_tests.py::test_existing_execution_does_not_need_graphical_initialization | 3.465 |
| tests/experiment_tests.py::test_presentation_does_not_change_simulation[normal-30] | 3.371 |
| tests/experiment_tests.py::test_presentation_does_not_change_simulation[noisy-60] | 3.228 |
| tests/experiment_tests.py::test_presentation_does_not_change_simulation[normal-60] | 3.211 |
| tests/experiment_tests.py::test_presentation_does_not_change_simulation[delayed-60] | 3.178 |
| tests/experiment_tests.py::test_presentation_does_not_change_simulation[normal-144] | 3.147 |
| tests/headless_tests.py::test_display_rendering_is_observer_and_matches_headless[overlays_off-60] | 2.733 |
| tests/headless_tests.py::test_display_rendering_is_observer_and_matches_headless[normal-60] | 2.421 |
| tests/headless_tests.py::test_display_rendering_is_observer_and_matches_headless[normal-144] | 2.302 |

File totals: accounting 5.774 s, docking 0.212, communication 0.598, energy 1.410, experiment 29.700, gameplay smoke 378.972, headless 41.112, motion 0.160, pathfinding 0.168, performance/cache 0.555, replay 26.829, reservation 0.498, task lifecycle 1.569. Parametrized presentation families are classified together, not split based on timing noise.

## 7. Validation-tier design

Tests have exactly one exclusive cost tier: FAST, STANDARD additions, or HEAVY. Normal STANDARD confidence is FAST + STANDARD. Plain pytest remains exhaustive. Original families were classified from measured per-case cost plus graphical dependencies and protected contracts: >2-second integration or graphical families are STANDARD; the mission smoke is HEAVY; inexpensive contracts are FAST.

No loop, assertion, seed, threshold, reservation horizon or policy cadence was shortened. New infrastructure cases explicitly declare their tier. The mapping is reviewed metadata; it is never rewritten automatically from current noisy timings.

## 8. FAST tier contract

Protect inexpensive movement, A*/Dijkstra cases, ownership, radio boundaries, energy/reserve/cache correctness, accounting, persistence validation and deterministic helpers. FAST includes cheap cold construction and collection/golden integrity/selection checks. It runs without a display driver substitution. Passing FAST is fast feedback, not completion of integration or mission validation.

## 9. STANDARD tier contract

Combine FAST with the STANDARD additions to cover 300/360-tick cold execution, sequential experiment independence, configuration/seed integration, graphical observer/replay/controller cases and a 60-tick approved golden + repeat. Windows CI runs these additions after FAST without repeating it. The graphical portion uses explicit offscreen SDL; normal hidden-window behavior is additionally checked by the longer matrix.

## 10. HEAVY tier contract

The existing 10,800-tick gameplay smoke remains intact, including forced communication recovery, the 29-cell offline buffering fixture, private survivor synchronization, connectivity and genuine recharge/relaunch checks. It is selected with `-m heavy`. Scheduled/manual heavy CI runs the full suite (therefore includes this test) plus the longer presentation matrix. Final local HEAVY acceptance used its execution inside the full suite, avoiding an unnecessary duplicate smoke run.

## 11. RELEASE / RESEARCH tier contract

Milestones add the three-seed 3,600-tick exact golden differential and repeat, full presentation validation and optional explicit scaling/profile/clean-timing commands. Existing Step 11 benchmark tools remain unchanged. No research framework was built and no performance threshold blocks a PR. Profiling, scaling and timing must run separately and sequentially; the manual workflow's milestone input opts into the expensive differential.

## 12. Pytest marker and selection design

Registered markers are `fast`, `standard`, `heavy`, `graphical`, `deterministic`; strict marker/config checking is enabled. Existing family rules are in `validation/test_contracts.json`; new tests must declare exactly one tier. Conflicting or missing classifications fail collection. Parametrized cases inherit their reviewed family rule.

`--audit-inventory` requires all 302 approved node IDs at full collection. The Windows PR workflow explicitly runs that audit before selection. `--test-order reverse` and `--test-order shuffle --order-seed N` change order using a private RNG. Full collection is never implicitly reduced. Unit fixtures prove removal/unknown-tier/conflicting-tier detection.

## 13. Machine-readable test inventory

`--inventory=PATH` records collected node ID, file, markers, tier, contract, baseline duration, graphical/deterministic/long-simulation/filesystem annotations, actual setup/call/teardown durations and outcomes. Deselected cases have null runtime duration. `collection.json` and each final run's `*_inventory.json` preserve the evidence.

Dependency flags are reviewed annotations, not automatic transitive dependency tracing. Every pytest case also uses temporary-directory infrastructure. The registry retains approved node IDs as an omission guard; changing those identifiers requires an explicit review rather than silent test disappearance.

## 14. Dependency reproducibility contract

Runtime requirements now pin the installed/approved versions of Pygame, NumPy and setuptools. `requirements-test.txt` includes runtime plus pytest/PyYAML, with `constraints-test.txt` pinning the small relevant pytest dependency closure (colorama, iniconfig, packaging, pluggy, Pygments). Unrelated globally installed libraries were not frozen. `.python-version` records 3.13.7.

Conventional requirements files are sufficient; no packaging/build-system migration was introduced. This is version-pinned reproducibility, not a hash-locked artifact supply chain. Pip bootstrap versions may differ. No library upgrade or dependency-vulnerability-free claim is made.

## 15. Supported and tested Python versions

The tested deterministic reference is CPython **3.13.7 on Windows x64**. CI requests that exact patch version. README's unsupported broad “Python 3.10+” claim was replaced. No other interpreter version or macOS execution was validated. Linux dependency availability was investigated, but runtime compatibility still awaits execution of the configured Linux job.

## 16. Clean-environment validation

A new venv was created outside the worktree, without system-site packages. `python -m pip install -r requirements-test.txt` and `python -m pip check` succeeded. Creation + installation/check took **31.92 seconds**. Exact packages/commands are in `clean_environment.json`, `clean_install.txt`, and `jobs.json`.

All final tier, ordering, full-suite, headless, presentation and golden checks ran with that venv interpreter, not accidentally available global packages. CI-like runs disabled third-party pytest plugin autoload. No dependency was added to the runtime solely for test execution except retaining setuptools already required by the validated Pygame resource import.

## 17. CI architecture

Two readable GitHub Actions workflows were added. `reliability.yml` has Windows contracts and Linux functional compatibility jobs. `heavy.yml` runs the full suite and longer matrix, with an optional milestone differential. Jobs use read-only contents permissions, pinned official action commit SHAs, exact Python setup, dependency installation/check, bounded timeouts and failure-only artifact upload. Pip download caching is keyed to requirement/constraint files; generated simulation state is never cached.

## 18. CI trigger strategy

PR/push/manual triggers run normal reliability checks. Weekly Monday 07:23 UTC and manual triggers run the heavy workflow. Manual `milestone=true` adds 3 × 3,600 ticks with repeats. No event triggers a deployment, package publication, telemetry, commit or push. Branch protection/required-status settings are repository administration and were not changed.

## 19. OS and platform strategy

Windows is the authoritative deterministic reference. Linux is a functional/headless target with same-platform repeat comparison, not equality to the Windows golden. Linux graphical tests are explicitly deselected. No macOS matrix was added.

Local WSL investigation found no installed Linux subsystem. Foreign-platform pip resolution succeeded for the pinned CPython 3.13 Linux wheels (`linux_feasibility.txt`, `linux_wheel_resolution.json`). That proves package availability, not Linux import/runtime/test success. Both hosted Windows runner behavior and Linux functional execution remain unverified; failures must be diagnosed rather than tolerated by weakening Windows hashes.

## 20. Headless CI contract

`python -m validation.sanity` installs an import guard against main/UI and replaces graphical initialization, Surface/Clock and input APIs with failing sentinels. It constructs/steps/inspects the core engine and loads exported replay in temporary storage, asserting no display/font initialization. It uses no dummy driver. Existing longer Step 9 cold-process regressions remain in STANDARD and full validation. Pygame package imports are permitted; this does not claim a Pygame-free core.

## 21. Graphical-test strategy

Graphical dependencies are marked explicitly, including font/surface-only tests. Windows STANDARD/full CI uses SDL dummy video/audio locally verified on this host. This is offscreen software presentation/controller coverage, not real monitor/GPU/audio/user-input validation. The local 180-tick matrix additionally used the normal hidden display path with driver variables unset.

Linux CI explicitly selects non-graphical tests; deselected tests are not reported as passed. No silent “display unavailable” skip was added, and full local pytest still includes graphical assertions.

## 22. Determinism gates

Existing clock, RNG isolation, extra presentation draws, world/weather/failure/planner randomness, ExperimentConfig identity and sequential-mission isolation tests are retained. A new bounded approved-golden/repeat test compares all covered simulation groups through tick 60, including energy diagnostics and accounting. Seven-condition observer assertions remain; the longer matrix wrapper now also hard-fails missing conditions or unequal final groups.

## 23. Differential-regression strategy

The Step 11 harness is byte-identical. The new `validation.differential` gate compares compact golden roots at every tick, with the same projection covering drones, world, private/global knowledge, tasks, reservations/recovery, energy, metrics/events, summaries, RNG and identity. Ordinary CI uses 60 ticks; release uses 3,600 ticks / three seeds.

On first mismatch it saves actual state and reruns the bundled trusted approved source only to that tick, identifying the first differing group and exact nested field. If reference reconstruction differs from the stored golden or fails, that is recorded and the gate still fails. Replay/CSV and final authoritative values are also checked for full-horizon runs. This remains sampled replay/diagnostic validation, not checkpoint continuation.

## 24. Golden/baseline artifact policy

`tests/golden/step11-v1` is a ~529 KB versioned bundle generated from approved Step 11 traces/final results and source. It stores 3 × 3,601 per-tick roots, final authoritative/replay/CSV values, source/config/runtime metadata and checksums, plus compressed trusted reference source for failure diagnosis. It has no developer-directory dependency.

Tests only read this bundle. Checksums detect corruption; the projector source must match (CRLF/LF-only conversion is permitted). Future changes require reviewed versioned golden updates, documented policy/environment cause, first-divergence analysis and new source/config/hashes. Changed source alone is provenance, not proof of a behavior change; a failing expected hash never automatically rewrites a baseline. This policy is documented in `docs/validation.md`.

## 25. Failure-artifact strategy

CI sets `ADSS_FAILURE_DIR=artifacts/differential`. A divergence produces seed/tick/root hashes, raw actual/expected projections, reference log, first group/field difference and reference-versus-golden status in a unique directory. JUnit/inventory reports and presentation results provide broader diagnostics. Artifacts upload only on failure, retain 14 days, and do not upload large successful traces by default.

Missing dependency failures remain actionable import errors in logs. Selection failures name missing/unknown tests. Reference-diagnostic failure cannot turn the underlying mismatch into success. Temporary local pytest evidence is printed in failures; set the environment variable to preserve it beyond temporary-directory cleanup.

## 26. Test-isolation findings

Cold-import tests failed before the two legacy modules' settings were moved from import time into fixtures/standalone entry points, then passed. This is a behavior-neutral test-infrastructure fix. No simulation policy defect was found or repaired.

An autouse test context now redirects output and restores configuration/RNG/environment/cwd/active experiment context, clears the presentation font cache and shuts down Pygame. A focused exception fixture verifies restoration. All non-heavy tests pass in reverse order, FAST passes a deterministic shuffle, and the docking file passes in an isolated pytest process. No remaining order-dependent failure appeared in these runs; this is bounded evidence, not every possible permutation.

## 27. RNG and global-state isolation

The old full-suite collection implicitly set normal mode, offline autonomy and failure probability zero. The new test fixture establishes those same baseline settings explicitly per test, while scenario fixtures can override them. Module collection itself leaves configuration unchanged. Python and NumPy global RNG states are restored; shuffle ordering uses a private RNG. Experiment context is unwound even on exceptions. These are test boundaries, not changes to simulation RNG/config architecture. Energy caches remain per-agent/per-mission; their existing isolation/query-purity tests pass.

## 28. Filesystem and persistence reliability

Pytest CSV/replay output is directed to per-test temporary directories. Cold subprocess tests already use their own temporary paths. Known standalone/app entry points still intentionally use configured logs/replays defaults. CI writes only expected reports under ignored `artifacts/` and pytest-managed storage.

Existing unique filename, overwrite refusal/explicit overwrite, atomic CSV/replay, interrupted-write, malformed/truncated/incompatible replay, optional extension and detached playback regressions all pass. No persistence production code or schema was changed. Tests do not depend on developer-specific absolute locations.

## 29. Path portability

Validation locates the repository from `__file__`, uses pathlib/subprocess argument lists and resolves divergence paths before invoking the reference subprocess. Reference ZIP entries are checked to stay inside the extraction directory and verified against source hashes. CI and runtime validation contain no machine-local path dependency. Saved local evidence legitimately records the actual paths used; historical evidence/orchestration is not a CI import dependency.

## 30. Static and quality checks

Python sources are compiled in memory for syntax validation; cold imports run separately. Local workflow structure checks enforce read-only permissions, pinned actions, timeouts and no privileged PR-target trigger. **actionlint 1.7.12 passed both workflows**, using a release archive verified against its published checksum. The optional shellcheck integration was disabled; no shellcheck coverage is claimed.

Repository `git diff --check`, scoped whitespace/source checks and final hashes are recorded at closure. No broad formatter, new linter backlog, type-checking migration or claim of full typing was introduced.

## 31. Dependency hygiene

Direct runtime and test versions are explicit; only the relevant small test dependency closure is constrained. Fresh `pip check` reports no broken requirements. The runtime has no pytest/PyYAML import dependency. Setuptools is explicitly retained for Pygame's deprecated resource API. The warning is documented, not hidden. This is a basic dependency/reproducibility audit, not a CVE scan or major-version upgrade project.

## 32. CI failure semantics

Install/import, FAST/STANDARD correctness, headless/persistence, collection completeness and deterministic mismatch are hard job failures. Smoke/heavy regressions fail the heavy job. Whether these jobs block merging depends on separately configured branch protection. Latency changes are informational. Existing subprocess/job timeouts remain hang guards, not FPS/performance acceptance thresholds. No continue-on-error masks correctness failures.

## 33. Local developer commands

The complete command reference is [docs/validation.md](validation.md). The essentials:

```text
python -m venv .venv
python -m pip install -r requirements-test.txt
python -m pytest -q -m fast
python -m pytest -q -m "fast or standard"
python -m pytest -q -m heavy -rP
python -m pytest -q -rP --audit-inventory
python -m validation.sanity
python -m validation.sanity --static
python -m validation.differential --ticks 60 --seeds 2026 2027 2031 --repeat
python -m validation.presentation --ticks 180
python -m pytest -q -m graphical
git diff --check
```

Activate the venv before the install/test commands. Release: increase differential to 3,600 ticks. Existing Step 11 profiling/scaling commands remain explicit optional tools, never noisy timing gates.

## 34. FAST runtime

**282 passed in 43.252 seconds** (pytest JUnit wall time); outer process wall time 44.00 s. No graphical driver substitution. This is meaningfully faster than the full suite and fits the reference-machine fast-feedback target without weakening assertions.

## 35. STANDARD runtime

STANDARD additions: **30 passed in 69.207 seconds**, outer wall 69.67 s. FAST plus additions total 112.46 s across the two sequential pytest invocations. That sum is the CI sequence measurement, not a separate timing trial of the cumulative `-m "fast or standard"` command. Reversed all-non-heavy execution took 112.150 s.

## 36. HEAVY runtime

The unchanged 10,800-tick smoke used **409.402 seconds** across setup/call/teardown inside the final full suite. Its original measured baseline was 378.972 s. No speedup or regression is inferred from these separate trials. HEAVY was verified through this full-suite execution rather than duplicating the same expensive smoke.

## 37. Full-suite runtime

Final **313 passed in 530.599 seconds**; outer process 531.21 s. Original frozen suite: 302 tests / 489.501 s. The final suite adds infrastructure cases and cleanup. These are reliability scheduling measurements, not new simulation performance benchmarks.

## 38. Failure-injection results

| Fault | Expected detection | Recovery/final state |
| --- | --- | --- |
| Legacy module import changes sentinel config | 2 focused regressions failed before fix | Both pass after fixture relocation |
| Missing installed dependencies via Python -S | Nonzero process exit; ModuleNotFoundError pygame | Normal fresh-env headless gate passes |
| Truncated golden data | Checksum ValueError | No automatic rewrite; original bundle unchanged |
| Wrong expected tick-zero root in memory | FIRST divergence seed2026 tick0; expected/actual/reference artifacts | Approved reference equals actual; injected expectation identified |
| Tiny position field change | First group drone_0; exact $.drone_0.px difference | Detached diagnostic files verified |
| Removed baseline node / unknown tier / conflicting tier | Selection audit raises named error | Complete collection passes |
| Missing presentation condition / changed RNG hash | Matrix wrapper hard failure with field | Complete seven-condition matrix passes |
| Malformed/truncated replay | Preserved Step7 validation errors | Full persistence suite passes |

Intentional faults exist only as scoped negative-test inputs/monkeypatches. None remain in production, golden files or workflow configuration.

## 39. Production files changed

**None.** All `core/*.py`, `ui/*.py`, `main.py` and `config.py` bytes match the frozen approved Step 11 baseline, including the energy cache. Simulation policy, time/RNG, paths, allocation, radio, collision, replay, accounting and success criteria were not changed.

## 40. Test and infrastructure files changed

Added `.python-version`, test requirements/constraints, two Actions workflows, `validation/` tools/registry, `tests/conftest.py`, `tests/reliability_tests.py`, and the compact versioned golden bundle. Updated `requirements.txt`, `pytest.ini`, `.gitignore`, README, and the two legacy test modules' setup boundaries. Added `docs/validation.md`, this report, and separate Step 12 evidence/orchestration. Existing benchmark workload scripts remain unchanged; no evidence directory is a CI dependency.

## 41. Tests added or modified

Eleven new cases cover two legacy import-isolation variants; process-state restoration through exceptions; golden integrity/no rewrite; exact failure-field artifacts; bounded golden/repeat; missing dependency failure; omitted/unknown/conflicting tier rejection; approved contract classification; missing/changed presentation matrix; and injected wrong golden tick with reference reconstruction.

Existing tests retain their assertions and loop lengths. Only the two legacy modules move top-level scenario settings into fixtures/direct-entry setup. `tests/conftest.py` adds consistent isolation/selection and measured inventory hooks. Original test-function ASTs are checked at closure to confirm their bodies were not weakened.

## 42. Final FAST result

PASS: 282 tests; all other tiers explicitly deselected. `fast.txt`, `fast.xml`, `fast_inventory.json` preserve the result. No unknown-marker warnings.

## 43. Final STANDARD result

PASS: 30 additions, including offscreen graphical tests and the approved Windows bounded golden. FAST also passed separately, so all 312 non-heavy cases passed. Artifacts: `standard.txt`, XML and inventory.

## 44. Final HEAVY result

PASS: the unchanged gameplay smoke ran successfully inside `full_final`, including its additional long recovery and offline-sync scenarios. The heavy CI job is configured to run this via full pytest. Hosted execution is not claimed.

## 45. Complete-suite result

**313 passed, zero failures/errors/skips** in the final clean environment. The known Pygame/setuptools deprecation warning remains. All 302 original node IDs are present; no assertion or acceptance threshold was relaxed. Artifacts: `full_final.txt`, XML, inventory and `jobs_complete.json`.

## 46. 10,800-tick smoke result

PASS at seed 2026. Coverage grows from 1.24% to 50.49%; all 5 survivor zones are discovered. Actual relaunch succeeds; no drones finish stranded, stuck at zero battery while returning, or in LOST_COMM. Average connectivity is 78.7%, majority-connected fraction 99.9%, and full-collapse ticks zero.

The forced communication-recovery fixture recovers after a maximum 827-tick lost streak. The offline map fixture buffers 29 cells and publishes them on reconnect with zero pending afterward. The survivor fixture remains private before synchronization and globally visible afterward, with one synchronized report. Neither fixture charges in the field. Emergency recoveries are zero. Every captured smoke output line exactly matches the frozen baseline; no new acceptance threshold was invented. Full output is preserved in `full_final.txt`.

## 47. Deterministic and repeat result

The clean-environment CLI compared seeds 2026/2027/2031 for 60 ticks each against the approved golden and repeated each run exactly. Tick-trace, final authoritative state, replay and CSV results match across repeats. The existing Step6/9/11 deterministic, config/RNG and sequential-experiment tests also pass, including reversed order.

## 48. Presentation-matrix result

All seven established conditions pass at 180 ticks: headless, normal 60/30/144 FPS settings, reduced rendering, overlays off and unrelated presentation draws. Observer assertions run around each render; the wrapper verifies all nine final authoritative groups. This matrix uses equal simulation ticks without FPS sleeps, not a monitor pacing benchmark. The saved result is compared with the approved Step 11 matrix at closure.

## 49. Differential result

The new three-seed bounded gate passes exact per-tick roots and repeat equality. The full three-seed 3,600-tick Step 11 differential evidence is preserved and its roots are the release golden. Because no simulation or projection code changed, the completed Step 11 long runs were not unnecessarily repeated here. The full-horizon command remains available and is wired to manual milestone CI, with final replay/CSV checks. This distinction is explicit: Step 12 newly executed bounded differential, retained approved full-horizon evidence.

## 50. Replay and persistence result

All existing replay/persistence, optional energy/accounting extension, unique/atomic output and detached playback tests pass in the clean environment, including reverse-order validation. Cold sanity also exports/loads replay without UI. No checkpoint continuation or new persistence schema was implemented.

## 51. Headless result

Cold sanity passes with graphical APIs replaced by failures and main/UI imports blocked. Longer Step 9 cases pass without display, Surface/Clock/input or UI construction. Headless execution does not require Pygame initialization; render-capable core modules still import the Pygame package.

## 52. Clean-environment result

Installation, pip consistency check, static/import sanity, FAST, STANDARD, order checks, complete suite, matrix and golden/repeats all pass with the new isolated venv. Exact interpreter/package inventory is saved. Windows offscreen and normal hidden-window graphics were exercised separately. No accidental global dependency was needed.

## 53. CI workflow validation result

PASS locally: both YAML workflows parse, structure/security invariants pass, action references resolve to the recorded official commits, and actionlint 1.7.12 reports exit 0. Negative dependency/selection/determinism/presentation paths are tested. GitHub-hosted jobs have **not run**, and no push or trigger was performed. Linux wheel resolution passes, but Linux runtime/graphics and hosted runner behavior remain unverified.

## 54. Git diff and source-hash validation

Closure verifies all frozen source hashes, all source/test/harness/CI files captured before the final acceptance run, production-byte equality, unchanged original test-function ASTs, and unchanged Step 11 evidence. Repository-wide `git diff --check` and scoped whitespace checks include new/untracked infrastructure and documentation. Machine-readable scoped additions/deletions and binary sizes, final Git status and final artifact hashes are in `final_closure_checks.json` / `final_artifact_hashes.json`.

The overall HEAD diff contains approved Steps 1–11 work. Step 12 scope is measured against the frozen Step 11 copy, not attributed from that cumulative diff. No staging, commit, push, reset or removal of approved work occurred.

Scoped deliverables excluding this closure report and local evidence/orchestration: **26 files, +3,431 / -22 text lines, and 525,380 bytes across four compressed binary files**. The golden manifest adds 4,037 bytes, making the complete bundle 529,417 bytes. The generated test inventory accounts for 2,370 added lines. Per-file counts, including this report, are recorded in the closure JSON.

Hash validation confirms 69 pre-validation files, all 52 frozen files, all 25 unchanged production modules, 206 unchanged original test-function ASTs (302 collected cases including parametrization), and 115 unchanged Step 11 evidence files. `git diff --check` exits 0; Git emits only existing LF/CRLF conversion notices. Scoped checks cover new files after line-ending normalization.

## 55. Remaining confirmed reliability limitations

Hosted CI and Linux execution are not validated locally. Windows is the only tested golden platform/interpreter patch set. Dummy SDL is not physical-display coverage. Version pins do not provide package-content hash locking or a vulnerability audit. Pygame still depends on deprecated pkg_resources. There is no production performance improvement or real-time guarantee in Step 12.

The golden projects specified authoritative state, not all Python memory; it is not a resume format. Diagnostic reference reruns may be slow when divergence occurs late. Metadata dependencies are reviewed annotations. Existing watchdog timeouts can still be reached on unusually slow runners. Branch-protection administration remains outside these workflow files.

## 56. Remaining unverified risks

Hosted Windows graphics/font availability, Linux floating/runtime behavior, other Python/NumPy versions, real hardware presentation, arbitrary test-order permutations and future dependency availability are not established by this local run. The future default-branch scheduled workflow only runs after an authorized push. Review legitimate environment differences rather than automatically changing goldens or weakening assertions. No known Step12 simulation-policy divergence remains.

## 57. Accurate reliability claims

ADSS now has locally validated, evidence-based test tiers; fresh pinned installation; automated cold headless and bounded exact-reference gates; versioned portable goldens with useful failure diagnostics; test-state/output isolation; preserved full smoke and prior contracts; and syntax-validated CI ready for user-authorized publication.

It cannot yet claim green GitHub-hosted runs, tested Linux/macOS support, cross-platform deterministic equality, exhaustive state-space correctness, vulnerability-free dependencies or guaranteed execution latency. Every such boundary is documented rather than hidden behind skips or relaxed thresholds.

## 58. Recommendation for the next roadmap step

Stop and review Step 12. Before relying on hosted status checks, authorize a push separately and inspect the first Windows/Linux runs; configure branch protection only after the intended jobs are confirmed. Treat any platform mismatch as a diagnosable compatibility issue, not permission to regenerate expectations. Proceed with Step 13 only after explicit approval of its scope. No Step 13 implementation, further performance optimization or policy work was performed.
