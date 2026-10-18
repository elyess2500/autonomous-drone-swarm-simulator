# Getting started

## Reference environment

Validated locally: **CPython 3.13.7, Windows x64**, Pygame 2.6.1 and NumPy 2.3.4. Runtime versions are pinned in [requirements.txt](../requirements.txt); tests add pytest 8.4.2 and PyYAML 6.0.3 through [requirements-test.txt](../requirements-test.txt) and [constraints-test.txt](../constraints-test.txt).

Other Python versions, macOS and Linux execution are not validated support claims. Linux functional checks are configured in CI but have not run on the hosted service. The earlier clean-environment install is recorded in the [Step 12 report](step12_engineering_report.md); Step 14 reused that environment and checked its installed dependencies.

## Install and launch

From the root of a clone/download, in PowerShell:

```powershell
python --version
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
python main.py
```

If activation is restricted, use `.venv\Scripts\python.exe` instead of `python` for subsequent commands; no shell-policy change is necessary. The conventional POSIX activation is `source .venv/bin/activate`, but that command is not evidence of tested platform compatibility.

A graphical desktop is needed for the application. Minimum supported window is 1100×760; 1400×850 and 1920×1080 have visual evidence. [Controls and interpretation](user_guide.md)

## Headless API

Run this Python example from the repository root, with the runtime environment active. It needs no display, dummy SDL driver or Pygame initialization.

```python
from dataclasses import asdict
from core.experiment import ExperimentConfig
from core.simulation import make_simulation

configuration = ExperimentConfig.capture()
world, swarm, mission, seed = make_simulation(
    2026, experiment_config=configuration
)
for _ in range(300):
    mission.update()

print(seed, mission.clock.tick, mission.experiment.identity)
print(asdict(mission.analytics.sample(mission)))
print(swarm.accounting.snapshot())
print(mission.outcome, mission.summary())
saved_replay = mission.export_replay()
print(saved_replay)
```

One call advances one fixed tick. Metrics/accounting queries are detached observations. Explicit stepping can continue after mission success; the final summary/duration stay frozen. Recording uses the existing CSV/replay paths; operations close their own file handles. Export what you need and release the returned objects; there is no engine worker thread or graphical lifecycle to shut down.

To compare sequential seeds, call the factory afresh for each one, optionally reusing the immutable configuration. Do not reuse a swarm or ledger. Specify the seed explicitly for reproducibility; a missing seed may resolve from defaults or generate one, so retain the returned value.

## Configuration boundary

Set simulation defaults in [config.py](../config.py) before capturing a new experiment, or load an exact canonical snapshot with `ExperimentConfig.from_json(text)`. Capture is a no-argument API, not a keyword override builder. Existing missions keep their snapshot. Output directories and presentation settings deliberately remain runtime settings.

The snapshot does not include source revision or the whole interpreter environment: record source and dependency versions alongside the seed/config for serious comparisons. Direct component calls outside Mission need `with mission.experiment.activate():` to use the intended settings context.

## Record and play back

Normal outputs use `logs/` and `replays/`; pytest redirects them to temporary directories. Replay filenames are unique unless explicit overwrite is requested. In the live app, `E` exports and `L` loads the latest JSON; Replay Viewer on the menu also loads the latest saved replay.

Programmatically, `mission.load_replay(saved_replay)` attaches a detached player; subsequent `mission.update()` calls advance playback while live time remains fixed. For independent viewing, `core.replay.load(path)` validates a payload and `core.replay.ReplayPlayer(payload)` creates the player. Seeking never restores live objects. There is no supported checkpoint/resume capability.

## Tests and troubleshooting

```powershell
python -m pip install -r requirements-test.txt
python -m validation.sanity --static
python -m validation.sanity
python -m pytest -q -m fast
```

See [Validation](validation.md) for STANDARD, HEAVY and release gates.

- Import errors: run from the repository root and check `python -m pip --version` points to the intended environment.
- Pygame's `pkg_resources` deprecation warning is known; pinned setuptools retains its validated provider. Do not hide a failing assertion behind that warning.
- Replay rejection: retain the original file/error. Version 2 playback is validated; malformed, truncated or incompatible files must fail rather than be patched into live state.
- Slow updates: 60 Hz describes simulation time, not a real-time promise. See [performance](performance.md).
- No replay found: export a live run first. A missing file is not permission to substitute a new world.
