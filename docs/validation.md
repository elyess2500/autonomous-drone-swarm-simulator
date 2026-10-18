# Validation and reproducible development

This contract was introduced in Step 12. It does not alter simulation policy.
Current Step 14 collection is **336 tests: 282 FAST, 53 STANDARD additions,
1 HEAVY**. Collection is not an assertion that a fresh 336-test full run occurred.
The last full run passed 333 cases in Step 13; its later menu-only polish passed
23 focused UI cases, including three additions. Step 14 reran FAST: **282 passed
in 44.28 seconds**; no expensive full/smoke rerun was needed for documentation.
The tested reference is **CPython 3.13.7, Windows x64, Pygame 2.6.1, NumPy 2.3.4**.
Other Python versions are not claimed supported until validated. GitHub-hosted
Windows/Linux execution remains unverified until these workflows actually run.

## Install

Create a clean environment with CPython 3.13.7:

```text
python -m venv .venv
```

Activate with `.venv\Scripts\activate` on Windows or
`source .venv/bin/activate` in a POSIX shell, then:

```text
python -m pip install -r requirements-test.txt
python -m pip check
python -m validation.sanity
```

Runtime-only installation uses `requirements.txt`. The test file includes runtime
dependencies, pytest 8.4.2 and PyYAML 6.0.3. `constraints-test.txt` pins the small
pytest dependency closure, not the developer machine's unrelated packages.
Setuptools 80.9.0 is retained because Pygame 2.6.1 imports `pkg_resources`; its
deprecation warning is known. No runtime library was upgraded in this tranche.
This is a tested version set, not a claim of a security vulnerability audit or
byte-identical installations across operating systems. Pip itself is not locked.

## Tiers and commands

Tiers are exclusive test classifications. STANDARD confidence combines FAST and
STANDARD additions. Plain pytest still runs every test, including HEAVY.

| Purpose | Command | What it proves |
| --- | --- | --- |
| FAST | `python -m pytest -q -m fast` | Inexpensive movement/planner/ownership/radio/energy/cache/accounting/persistence contracts |
| STANDARD | `python -m pytest -q -m "fast or standard"` | FAST plus bounded simulation, repeat/golden, context isolation and presentation integration |
| STANDARD additions only | `python -m pytest -q -m standard` | Avoids repeating FAST in the same CI job |
| HEAVY tests | `python -m pytest -q -m heavy -rP` | The 10,800-tick mission and long recovery/buffering smoke |
| Full suite | `python -m pytest -q -rP --audit-inventory` | Every collected contract, including the smoke |
| Cold headless boundary | `python -m validation.sanity` | Import, construct, advance, inspect and persist without UI/SDL initialization |
| Static sanity | `python -m validation.sanity --static` | In-memory Python compilation and basic workflow/configuration checks |
| Collection audit | `python -m pytest --collect-only -q --audit-inventory --inventory=artifacts/collection.json` | No approved 302 node IDs omitted; every new test explicitly classified |
| Bounded differential/repeat | `python -m validation.differential --ticks 60 --seeds 2026 2027 2031 --repeat` | Exact per-tick approved Windows golden plus repeated-run equality |
| Graphical tests | `python -m pytest -q -m graphical` | Surface/font/render/controller contracts; requires an explicit graphics strategy |
| Longer presentation matrix | `python -m validation.presentation --ticks 180` | Seven conditions, observer assertions and final authoritative equality |
| Reverse order | `python -m pytest -q -m "not heavy" --test-order reverse` | Cross-file state leakage detection |
| Deterministic shuffle | `python -m pytest -q -m fast --test-order shuffle --order-seed 2031` | Reordered inexpensive contracts without consuming simulation RNG |

The initial 302-test profile took 489.58 seconds: FAST-classified original tests
41.525 s, STANDARD additions 67.060 s, and the smoke 378.972 s (phase totals).
Classification considers measured duration **and dependencies/contracts**: graphics
are STANDARD even when individually cheap; >2 s integration cases are STANDARD;
the smoke is HEAVY. These are observations, not machine-independent deadlines.
For the approved pre-polish Step 13 source, FAST took 42.638 s, STANDARD additions
66.967 s (50 cases), and the HEAVY smoke 368.806 s; the full 333-case suite took
472.60 s. The three menu-alignment additions passed within a 23-case UI run in
4.51 s. These are distinct runs, not a synthetic timing for today's entire suite.
See the [Step 12 report](step12_engineering_report.md) and
[Step 13 report/addendum](step13_engineering_report.md).

The small marker taxonomy is `fast`, `standard`, `heavy`, `graphical`, and
`deterministic`. Original test families are explicitly mapped in
`validation/test_contracts.json`, with measured duration, contract and dependency
notes. A new test needs exactly one tier marker. Add semantic markers when useful.
Do not auto-retier tests from noisy current durations. Measure and review changes.
`--inventory=PATH` writes every collected node's tier/markers, baseline cost,
dependency flags, actual setup/call/teardown durations and outcomes. Deselected
tests have no measured duration. Dependency flags are review annotations, not a
runtime dependency tracer; per-test temporary output setup always uses filesystem.

## Headless and graphical boundaries

The supported engine API is `core.simulation.make_simulation`. Pygame imports are
allowed; graphical initialization, Surface/presentation Clock creation, input,
main/UI imports are prohibited in the cold headless gate. The existing stronger
300/360-tick cold-process fixtures remain STANDARD. No dummy SDL driver is used
to pretend headless execution works.

Windows STANDARD CI sets `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` **only
for graphical testing**. This validates software/offscreen drawing and scripted
controller behavior, not a real monitor, GPU, audio device or user interaction.
For local Windows offscreen tests in PowerShell:

```powershell
$env:SDL_VIDEODRIVER = 'dummy'
$env:SDL_AUDIODRIVER = 'dummy'
python -m pytest -q -m graphical
Remove-Item Env:SDL_VIDEODRIVER, Env:SDL_AUDIODRIVER
```

Normal hidden-window presentation testing remains available with those variables
unset. Linux CI selects `(fast or standard) and not graphical`; deselection is
explicit, not reported as full graphical coverage. On Linux the bounded test
compares two same-platform runs, not the Windows golden. No macOS claim is made.

## Deterministic baseline policy

`tests/golden/step11-v1/` is a versioned ~529 KB approved golden bundle. It contains:

- SHA-256 roots of the Step 11 per-group hashes at **every tick 0..3600**, for seeds
  2026/2027/2031; final authoritative/replay/CSV hashes and values.
- A manifest of schema, seed/config overrides, runtime versions, checksums and
  original source hashes.
- A compressed, trusted repository source fixture used only to reproduce the
  expected raw state at the **first divergent tick**.

Initial golden data was derived from the approved Step 11 results, not generated
from unreviewed Step 12 behavior. Tests verify bundle checksums and the projection
source contract; CRLF/LF-only projector conversions are allowed. The unchanged
`benchmarks/step11.py` differential harness remains available. The new gate adds
compact portable references without requiring developer-specific directories.

On failure, the gate saves seed/tick, expected/actual roots, actual raw projection,
reference output/log, first differing group and exact field. If the reference
cannot reproduce the golden, this is reported explicitly; the test still fails.
Reference code runs in a temporary directory with the current interpreter. It is
trusted source under repository review, **not** an arbitrary-object checkpoint
loader. Raw-state reconstruction is for diagnostics only, never live resume.

Tests never overwrite goldens. Updating them requires a separate reviewed change:
identify the intended policy/schema/environment change, preserve old evidence,
run the old/new differential to identify the first change, generate a new version
from approved source, record source/config/environment/checksums, review changed
state/events, then explicitly change the default bundle. An unexplained failing
hash is never permission to regenerate expected results. A changed projector
fails closed; changed simulation source alone does not imply changed behavior.
Source provenance is recorded rather than using “any source edit” as a behavior
failure. The reference claims only the explicit projection, not all Python state.

## Release / milestone validation

Run the full suite, long presentation matrix, and:

```text
python -m validation.differential --ticks 3600 --seeds 2026 2027 2031 --repeat --output artifacts/milestone
```

The original Step 11 harness still supports an explicit reference checkout's
traces, `--reference`, and `--dump-tick` for diagnostics. Optional performance work:

```text
python benchmarks/step11.py --mode profile --output artifacts/profile
python benchmarks/step11.py --mode clean --output artifacts/timing
python benchmarks/step11.py --seeds 2026 --ticks 180 --drones 16 --output artifacts/scale16
python benchmarks/step11.py --seeds 2026 --ticks 180 --drones 32 --output artifacts/scale32
```

Run timing/profiling/scaling sequentially, separately from tests. Compare only
comparable methodology; profiling time is not clean update latency. No wall-time
number blocks a PR. These are retained milestone tools, not a new research
framework or automatically scheduled performance suite. Step 14 adds no research
campaign and does not regenerate golden data.

## CI and failure semantics

`.github/workflows/reliability.yml`: PR/push/manual, Windows FAST then STANDARD;
Linux functional compatibility, no graphics. `.github/workflows/heavy.yml`:
weekly Monday 07:23 UTC or manual, full suite and 180-tick presentation matrix;
manual `milestone=true` adds full three-seed differential/repeats.

Install/import, tier selection, correctness, headless/persistence and deterministic
failures fail their job. Heavy failures fail the heavy job; repository branch
protection is not configured by these files. There are no performance thresholds.
Workflows have read-only repository permissions, pinned action commit IDs,
bounded job timeouts, and no `pull_request_target` execution. Pip caching covers
downloads keyed to requirements/constraints; no simulation state is cached.

Failure-only uploads retain `artifacts/` for 14 days, including JUnit, inventory
and deterministic divergence files when available. Successful runs do not upload
large traces. Pytest capture/JUnit and Actions logs retain seed/error context.
Use `ADSS_FAILURE_DIR` to choose a persistent failure directory for local pytest
golden checks; default temporary evidence paths are printed in failures.

Local checks used actionlint plus structural YAML checks. Hosted green checks
cannot be claimed until a user-authorized push actually runs these workflows.
No push was performed. Linux wheels resolved, but this machine has no installed
Linux/WSL runtime; functional Linux execution remains a CI validation target.

Official references used for configuration: [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[setup-python](https://github.com/actions/setup-python),
[checkout](https://github.com/actions/checkout), and
[actionlint](https://github.com/rhysd/actionlint).

## Isolation and maintenance

Pytest wraps each case with config/RNG/environment/cwd/context restoration,
temporary CSV/replay destinations and Pygame/font-cache cleanup. Failure-free,
normal/offline-enabled fixture defaults explicitly preserve the old full-suite
collection defaults; tests that exercise failures override them locally. The two
legacy test modules no longer mutate config on import. Standalone smoke/docking
entry points still set their own explicit scenario settings.

Use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for CI-like execution; the clean test
environment has no unrelated auto-loaded plugins. Test ordering uses a private
`random.Random`, not simulation/global RNG. No test seeds or restores live
production experiments on behalf of the engine. Per-agent energy caches remain
instance-owned and are covered by unchanged Step 11 tests.

Before submitting, run the appropriate tiers and `git diff --check`. Do not
reformat unrelated production files or relax assertions to fit a duration target.
The benchmark `results/` directories contain historical evidence/orchestration,
including real machine paths; CI never depends on those paths or imports those
scripts. Normal output goes to ignored `artifacts/` or pytest-managed temporary
directories. The full suite must continue to include every approved regression.
