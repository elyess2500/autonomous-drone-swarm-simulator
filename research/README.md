# ADSS controlled study: research artifacts

This directory contains Step 15 experiments using the approved Step 14 simulator. Research data is separate from engineering regression evidence. Read the [preregistered protocol](../docs/research_protocol.md) before interpreting results.

## Layout

- [protocol](protocol): immutable pre-results protocol, pilot decision and main hash lock.
- [manifests](manifests): complete condition configurations, fixed seed/run order, source identities and runtime.
- [raw](raw): per-run immutable JSON/checksum pairs and original CSV artifacts; pilot/main/repeat directories remain separate.
- [analysis](analysis): deterministic paired analysis and plotting code plus analysis-only dependency pins.
- [processed](processed): per-run tables, summaries, effect estimates and analysis provenance.
- [figures](figures): raw paired observations and primary coverage effects in PNG/SVG/PDF.
- [tables](tables): compact human-readable result tables after analysis.

The simulator source and runtime/test dependencies are unchanged. The separate analysis environment needs NumPy/Matplotlib only; it is not an intervention in the simulation.

## Reproduce

From repository root, using the pinned simulation environment described in [getting started](../docs/getting_started.md):

```powershell
python experiments/run_step15.py --manifest research/manifests/pilot.json --output research/raw/pilot
python experiments/run_step15.py --manifest research/manifests/main.json --output research/raw/main
```

Existing complete files are checksum/identity validated and skipped, never silently replaced. To execute fresh runs, use a new repository-relative output directory, for example `research/raw/reproduction`. Output must remain within the checkout so artifact references stay portable. The runner rejects mismatched frozen source. A failed/incomplete attempt is retained and blocks reuse of its directory; investigate and choose a separately documented attempt destination.

For independent analysis, create a separate environment rather than changing the validated simulation environment:

```powershell
python -m venv artifacts/analysis-env
artifacts/analysis-env\Scripts\python.exe -m pip install -r research/analysis/requirements.txt
artifacts/analysis-env\Scripts\python.exe research/analysis/analyze.py --manifest research/manifests/main.json --raw research/raw/main --output research/processed --figures research/figures
```

Only derived analysis files may be regenerated. Never manually edit raw measurements or the locked manifest. Reproduction against a new raw directory needs the matching `--raw` argument; timings will vary but authoritative non-timing state should repeat under the recorded runtime/source/config.

## Checks and interpretation

```powershell
python -m unittest experiments.test_step15 experiments.test_analysis_step15 -v
python -m validation.sanity
python -m pytest -q -m fast
```

The runner tests are engineering checks, not additional research replicates. Main seeds are 41001–41008; pilot seeds are 49001/49002. Each unique main condition has eight replicates; the shared reference supports both questions without double-counting runs.

Primary comparisons use paired coverage differences, 20,000 percentile-bootstrap resamples, analysis seed 1502026 and 98.75% marginal intervals for the four-contrast family. Secondary outcomes are descriptive. Publication delays not observed by the horizon are censored. No survivor-rescue outcome exists.

Update timing includes the existing recorder; the measured CSV-call component is additionally reported separately. Research observation/output, analysis and plotting are outside update time. Small-seed bootstrap uncertainty is approximate and does not represent physical drones or all possible worlds.

Source identities cover exact file bytes, including line endings. Preserve the frozen repository bytes when reproducing; the runner intentionally rejects a normalized or edited checkout rather than silently claiming the same source. The reference platform is Windows/CPython 3.13.7; cross-platform equality is unverified.

Analysis and plots were generated using the recorded matching dependency versions in an existing environment. The separate-environment commands are provided for isolation; a fresh installation of that plotting environment was not exercised in this tranche. A first analysis attempt exposed a relative-path provenance error, corrected with a tooling regression. No raw observations or statistical methods changed. The protocol also mentioned timing replay export; the runner retained ordinary in-memory recording but did not request end-of-run export, so no replay-export timing is reported.
