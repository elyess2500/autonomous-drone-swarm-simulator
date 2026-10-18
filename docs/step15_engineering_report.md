# Step 15 — Controlled research experiments

Collection: 2026-10-06. Closure: 2026-10-07. Final planned phase; results are confined to the preregistered ADSS study.

## 1. Executive summary

Forty paired headless runs across eight new seeds compared radio ranges of 90/180/360 pixels and swarm sizes of 4/8/16 for 900 ticks (15 simulated seconds). The approved simulator policy remained unchanged. 90 versus 180 px: paired mean coverage difference -7.309 percentage points, adjusted marginal interval [-8.792, -5.879]; supported difference. 360 versus 180 px: paired mean coverage difference +3.131 percentage points, adjusted marginal interval [+1.354, +4.811]; supported difference. 4 versus 8 drones: paired mean coverage difference -4.823 percentage points, adjusted marginal interval [-6.096, -3.564]; supported difference. 16 versus 8 drones: paired mean coverage difference +3.146 percentage points, adjusted marginal interval [+2.235, +3.912]; supported difference. Mean effects and paired bootstrap uncertainty are reported alongside raw seed values; timing and mission outcomes remain separate. Results are confined to this early-search model and convenience seed set.

## 2. Frozen Step 14 baseline

Frozen before research: 104 approved worktree files copied, 540 prior evidence files hashed, Git status/diff saved. Seventy executable/runtime/golden/workflow inputs identify the reference. Python 3.13.7, Windows 11 build 26300, Pygame 2.6.1, NumPy 2.3.4; Intel i7-11370H, 4 cores/8 logical processors, 16,856,203,264 bytes RAM. No earlier evidence was overwritten.

## 3. Research objective

Investigate effects inside the validated model, not prove that ADSS is good. Engineering tests and research observations are separate.

## 4. Candidate-question audit

Existing range and count knobs are explicit ExperimentConfig fields. Range also changes risk/relay policy; count changes agent/relay/failure exposure. The existing composite mission-efficiency score is not a research endpoint. See the question audit.

## 5. Selected research questions

Communication range and swarm size: each offers a clean existing intervention with interpretable early-search outcomes.

## 6. Deferred questions

Energy-policy control lacks a clean existing alternative; disabling safety was rejected. Separate density pressure and expensive 32-drone cases were deferred. Waits/backoffs are secondary size outcomes.

## 7. Preregistered hypotheses

Four nondirectional coverage contrasts were fixed before pilot/main results. H0 is zero paired mean difference; H1 nonzero. Engineering expectations were kept separate and not rewritten after results.

## 8. Experimental protocol

[Research protocol](research_protocol.md), immutable v1 copy, pilot summary and main hash lock precede main collection. The manifest contains full conditions and deterministic run order.

## 9. Independent variables

Range 90/180/360 px at eight drones; count 4/8/16 at 180 px. Reference is shared, not counted twice.

## 10. Dependent variables

Final published coverage is primary. Survivors, connectivity, private buffering/upload, task/energy/collision events and computational latency are secondary. Rescue is unsupported.

## 11. Controlled variables

Map dimensions/terrain generation, clock, all remaining policy parameters, weather/failure defaults and persistence cadence are fixed. No operator recovery occurs.

## 12. Seed strategy

Eight fixed new main seeds 41001–41008 paired across conditions. Pilot 49001/49002 excluded. World hashes match within each seed. Convenience selection limits population inference.

## 13. Run duration

900 updates, 15 simulated seconds, all conditions; no warm-up discarded. This studies initial exploration, not long-run completion.

## 14. Stopping/exclusion rules

Fixed horizon even after success; no significance stopping. Crash/invalid artifacts must be retained, investigated and never silently excluded. No main failures or exclusions occurred.

## 15. Pilot design

Seven 600-tick exploratory runs: all five conditions at 49001 and reference/16 drones at 49002.

## 16. Pilot results

All pilots completed and paired worlds matched. Coverage 4.91–12.46%, survivors 0–1; this identified sparse secondary publication without a hard coverage floor.

## 17. Protocol changes after pilot

No condition, seed, hypothesis, primary endpoint, statistical method, exclusion/threshold or proposed 900-tick horizon changed. A pre-main addendum locks that decision and runtime estimate. One recording limitation is disclosed: the protocol mentioned timing replay export, but the locked runner retained normal in-memory sampling without invoking an end-of-run export. No export-cost estimate is available; this does not change simulation updates or research endpoints.

## 18. Final campaign design

Forty unique runs, five conditions times eight seeds; condition order rotates by seed. Reference is shared across the two comparisons.

## 19. Computational budget

Pilot estimate: 637.2 update seconds (10.6 min), with about 25 min practical allowance. Actual main update total: 917.1 s; raw timing separates observation/output. No multi-hour campaign or 32-drone extension was launched.

## 20. Experiment runner

Manifest-driven headless runner outside simulator policy. It validates source, constructs explicit config, steps Mission, observes existing state/events, times CSV transparently, publishes atomic raw files and validates resume.

## 21. Output schema

Schema 1 records run/config/source/harness identity, environment, metrics, counts, exposure/delay observations, sampled time series, per-tick latency, final projection hashes and artifact checksums. Failed attempts have explicit status/tick/error records.

## 22. Reproducibility contract

Exact frozen source/config/runtime plus seed defines the tested reproduction claim. One 900-tick reference repeat matches covered non-timing state/accounting/RNG/knowledge/metrics/diagnostics. Timing and unique file paths are intentionally excluded.

## 23. Raw artifact integrity

Raw JSON/checksum pairs and original CSV are retained. Resume validates identities/checksums without rewriting completed results. Failure injection is a tooling test, not a research exclusion. Main raw files were never manually edited.

## 24. Analysis methodology

Deterministic analysis reads complete declared pairs, validates world/checksum identities, exports raw per-seed tables and computes paired effects. Pilot is not included.

## 25. Statistical methods

Paired nonparametric percentile bootstrap over seed blocks. No normality assumption, tick pseudo-replication or p-value-based stopping.

## 26. Confidence intervals

20,000 resamples, independent NumPy PCG64 seed 1502026. Both 95% and adjusted 98.75% intervals saved. Small-n percentile intervals are approximate.

## 27. Effect sizes

Primary effects are paired mean differences in coverage percentage points, with raw differences, median and sample SD. Secondary effects retain natural units.

## 28. Multiple-comparison handling

Four primary contrasts use Bonferroni-adjusted marginal 98.75% intervals; nominal familywise 95% is not a guarantee of actual bootstrap coverage. Secondary analyses are descriptive, without familywise claims.

## 29. Experiment 1 results

90 versus 180 px: paired mean coverage difference -7.309 percentage points, adjusted marginal interval [-8.792, -5.879]; supported difference. 360 versus 180 px: paired mean coverage difference +3.131 percentage points, adjusted marginal interval [+1.354, +4.811]; supported difference.

| Contrast versus reference | Mean difference (pp) | 95% CI | 98.75% CI | Primary classification |
| --- | --- | --- | --- | --- |
| range_90 | -7.309 | [-8.471, -6.162] | [-8.792, -5.879] | SUPPORTED difference |
| range_360 | +3.131 | [+1.729, +4.469] | [+1.354, +4.811] | SUPPORTED difference |
| swarm_4 | -4.823 | [-5.837, -3.824] | [-6.096, -3.564] | SUPPORTED difference |
| swarm_16 | +3.146 | [+2.443, +3.771] | [+2.235, +3.912] | SUPPORTED difference |


## 30. Experiment 1 interpretation

Range effects include policy adaptation. Do not infer realistic RF or isolate delivery from trajectories/accepted work. Sparse/censored publication outcomes limit secondary interpretation.

## 31. Experiment 2 results

4 versus 8 drones: paired mean coverage difference -4.823 percentage points, adjusted marginal interval [-6.096, -3.564]; supported difference. 16 versus 8 drones: paired mean coverage difference +3.146 percentage points, adjusted marginal interval [+2.235, +3.912]; supported difference.

| Condition | n | Coverage mean % (SD) | Survivors mean | Connected mean % | Task completions mean | Pending map exposure mean |
| --- | --- | --- | --- | --- | --- | --- |
| 90 px / 8 drones | 8 | 5.21 (1.40) | 0.000 | 92.63 | 3.88 | 19.76 |
| 180 px / 8 drones | 8 | 12.51 (0.77) | 0.750 | 96.91 | 6.62 | 4.15 |
| 360 px / 8 drones | 8 | 15.65 (1.86) | 1.000 | 98.64 | 5.88 | 0.00 |
| 180 px / 4 drones | 8 | 7.69 (0.95) | 0.250 | 98.02 | 3.62 | 0.04 |
| 180 px / 16 drones | 8 | 15.66 (0.70) | 0.875 | 94.18 | 7.88 | 28.84 |


## 32. Experiment 2 interpretation

Count effects represent whole-swarm early progress versus contention/search cost, not independent identical workers or physical fleet scalability.

## 33. Experiment 3 results if selected

Not selected; no energy-policy intervention was implemented.

## 34. Experiment 3 interpretation if selected

No third-question conclusions are manufactured from engineering fixtures.

## 35. Negative/null results

Survivor publication is sparse (per-run counts and null/censored times are retained). 0/40 runs reach mission success at the fixed horizon. Absence of long-run successes/stranding within 15 seconds cannot establish eventual completion or energy safety. Primary intervals that include zero indicate insufficient evidence of a difference, not equivalence. Secondary results do not acquire confirmatory status because they look favorable.

## 36. Trade-offs

The paired tables show separate mission, coordination and computational outcomes; none is collapsed into a score. A larger available fleet can increase early coverage while increasing waits, searches and cost. Short radio range also changes the region and work the policy accepts. These adaptive responses prevent a simple interpretation that more connectivity always means more exploration.

## 37. Computational-performance results

| Condition | Mean update ms | Mean p50 | Mean p95 | Mean p99 | Worst max | Mean excluding CSV ms |
| --- | --- | --- | --- | --- | --- | --- |
| 90 px / 8 drones | 36.628 | 32.653 | 48.990 | 84.018 | 2439.765 | 36.438 |
| 180 px / 8 drones | 13.254 | 7.428 | 26.648 | 68.001 | 602.820 | 13.055 |
| 360 px / 8 drones | 8.786 | 6.892 | 14.452 | 33.085 | 522.805 | 8.601 |
| 180 px / 4 drones | 3.886 | 3.280 | 5.991 | 17.017 | 70.827 | 3.694 |
| 180 px / 16 drones | 64.819 | 42.838 | 132.864 | 366.494 | 3736.303 | 64.618 |

Main collection spent 917.1 seconds in simulation updates; pilot projected 637.2 seconds. Per-seed raw latency arrays preserve variation. The reference repeat matches all covered non-timing fields, while its timing differs; see the reproducibility artifact. This is not a real-time guarantee or a profiler-derived attribution of runtime to one subsystem.

Across main runs, measured CSV calls total 6.965 s within updates; post-update observation totals 4.862 s outside them. Analysis and plotting took 3.43 s separately. Reference seed 41001 mean update time was 9.977 ms originally and 8.274 ms on repeat; maxima were 472.825 and 649.005 ms. Exact behavioral equality with different timing demonstrates host/run variability, not an optimization. Table p50/p95/p99 values are means of the eight run-level quantiles; worst max is the largest observed tick. Individual values, SD and quartiles remain in the processed tables. No direct comparison to historical uninstrumented optimization timings is made.

## 38. Figures

Two figures in PNG/SVG/PDF: raw paired coverage/connectivity/update cost, and primary coverage effects with adjusted intervals. Axes state units/n; thin lines show actual seed pairing, shapes distinguish summaries. No smoothing. Rendered PNGs were inspected.

## 39. Tables

Per-run CSV, condition mean/median/SD/quartiles, paired effects/intervals, survivor delay censoring table, compact Markdown table and analysis provenance JSON are reproducible from raw.

## 40. Threats to internal validity

Intervention isolation is protected by config diffs and source/world hashes; latent simulator bugs remain possible. Timing order/host noise and endogenous relay/failure responses are disclosed.

## 41. Threats to construct validity

Coverage is publication visibility, not rescue or reachable flight-area coverage. Radio/energy/collision constructs are abstract. Pending buffers can count the same cell for multiple agents.

## 42. Threats to external validity

Eight generated worlds, one map/settings family, 15 seconds, centralized coordinator, no real flight/RF/hardware: external generalization is limited.

## 43. Statistical-conclusion limitations

Small convenience sample, discrete sparse survivors, approximate bootstrap, shared reference, secondary multiplicity and single timing pass limit conclusions.

## 44. Research claims classification

| Classification | Conclusion |
| --- | --- |
| SUPPORTED difference | range_90: paired mean coverage difference -7.309 percentage points, adjusted marginal interval [-8.792, -5.879]; supported difference. |
| SUPPORTED difference | range_360: paired mean coverage difference +3.131 percentage points, adjusted marginal interval [+1.354, +4.811]; supported difference. |
| SUPPORTED difference | swarm_4: paired mean coverage difference -4.823 percentage points, adjusted marginal interval [-6.096, -3.564]; supported difference. |
| SUPPORTED difference | swarm_16: paired mean coverage difference +3.146 percentage points, adjusted marginal interval [+2.235, +3.912]; supported difference. |
| MIXED / descriptive | Mission progress and computational/coordination costs move differently; see raw paired observations. |
| UNSUPPORTED | This 15-second study does not establish eventual mission success, physical safety or long-run energy robustness. |
| EXPLORATORY | Secondary publication, connectivity and buffering mechanisms are descriptive; no multiplicity-controlled secondary claims. |


## 45. README changes

A small bounded early-search results section links the paper/protocol. The larger engineering claims and limitations remain.

## 46. Portfolio changes

One appended research component describes controlled paired experiments, preserved raw data and reproducible uncertainty; existing accomplishments remain.

## 47. Production-code changes

None. Core, config, main, UI, existing validation/tests, dependencies and goldens remain byte-identical to the approved frozen inputs. No new policy toggle.

## 48. Test changes

No existing tests changed. Three runner reliability tests, two hand-calculated analysis tests and one analysis-path regression live outside the default simulator suite. The first analysis attempt failed while recording relative input provenance; the failure and focused regression were saved, the path conversion was corrected, and analysis was regenerated. No raw data, endpoint or statistical calculation changed.

## 49. Regression validation

Runner/analysis checks: 6 passed. FAST: 282 passed in 46.48 s (JUnit duration; console 46.59 s). Cold headless/static checks pass. Current default inventory remains 336 collected, not a fresh full-suite claim. No STANDARD/HEAVY/smoke rerun was needed.

## 50. Source/hash validation

All 104 frozen files, 540 prior evidence files and 74 protected executable/test/infrastructure inputs retain their hashes. The experiment source identity covers its recorded 70-input subset; the full 74-input closure scope is checked separately. Forty main runs and one repeat validate identities and original CSV checksums. All 12 repeated derived tables/figure files are byte-identical. Preregistration, manifest and runner hashes match the pre-main lock. See [closure checks](evidence/step15/closure_checks.json) and [source/artifact manifest](evidence/step15/final_source_artifact_hashes.json).

## 51. Git diff/whitespace validation

Git diff --check and scoped text whitespace/EOF checks pass; immutable raw serialization is preserved without EOF normalization. Public local links/images and path privacy pass. The only modified baseline files are README.md and docs/portfolio_summary.md; new research tools, reports and artifacts are inventoried in the [scoped diff](evidence/step15/scoped_diff.json). This comparison is against frozen Step 14, not the cumulative earlier worktree diff.

## 52. Remaining simulator limitations

All approved point-agent/radio/charge/replay/outcome limitations remain. No rescue, real-time guarantee, hardware flight control or checkpoint continuation.

## 53. Remaining research limitations

Short horizon, n=8, limited settings, descriptive secondary endpoints, approximate intervals and observational timing. Weather starts Clear and first changes at tick 900, so this is not a sustained adverse-weather study. No policy superiority or long-run completion claim. The separate plotting pins match the used environment; a fresh plotting environment installation and cross-platform reproduction were not validated.

## 54. Reproduction commands

See [research artifact guide](../research/README.md) and [research report](research_report.md) for runner, repeat, analysis and separate plotting-environment commands. Use fresh output destinations; do not overwrite data.

## 55. Artifact inventory

Protocol/lock; full condition/environment manifests; seven pilot, 40 main and one repeat run; original CSV/checksums; processed CSV/JSON; figures; tooling checks; source/diff/hash evidence; research and closure reports.

## 56. Accurate public claims

ADSS supports a small reproducible controlled simulation study with explicit paired interventions and bounded effect estimates. It is not thereby certified research-grade or transferable to physical drones.

## 57. Final research conclusions

90 versus 180 px: paired mean coverage difference -7.309 percentage points, adjusted marginal interval [-8.792, -5.879]; supported difference. 360 versus 180 px: paired mean coverage difference +3.131 percentage points, adjusted marginal interval [+1.354, +4.811]; supported difference. 4 versus 8 drones: paired mean coverage difference -4.823 percentage points, adjusted marginal interval [-6.096, -3.564]; supported difference. 16 versus 8 drones: paired mean coverage difference +3.146 percentage points, adjusted marginal interval [+2.235, +3.912]; supported difference. Conclusions apply to this early-search scenario set only; secondary tradeoffs require cautious interpretation.

## 58. Final roadmap status

Steps 1–14 remain approved; Step 15 study and closure are submitted for review. This is the final planned roadmap phase. No Step 16, feature work, commit, push, reset or discard. Stop for approval.
