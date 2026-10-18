# Step 15 preregistered protocol

Registration v1, 2026-10-06, before pilot/main collection. Simulator: frozen approved Step 14, no production changes. The machine-readable pilot manifest and later locked main manifest embed the complete ExperimentConfig, source identity and runtime. This file's pre-main version is retained in research/protocol.

## Question audit and selection

| Candidate | Existing intervention | Decision |
| --- | --- | --- |
| RQ1 radio range | DRONE_COMM_RANGE, part of immutable experiment identity | Select: interpretable joint effect on reachability, policy and published search |
| RQ2 energy-policy control | No clean alternative-policy switch; disabling safety is not a credible matched control | Defer; no new policy toggle |
| RQ3 swarm size | NUM_DRONES, owned per-agent RNG | Select: early progress versus coordination/runtime cost |
| RQ4 deconfliction pressure | Count or terrain-density changes | Treat waits/backoffs as secondary swarm-size outcomes; defer separate terrain campaign |

Radio range changes both physical reachability and existing communication-aware allocation/relay behavior. The estimand is this total configured-system effect, not a pure network-only effect. More drones changes available agents, failure exposure and derived relay demand, not just independent search capacity. No safety or energy rule is disabled.

## Hypotheses fixed before results

**RQ1 primary:** H0: paired mean final published coverage difference is zero for 90 versus 180 pixels, and 360 versus 180 pixels. H1: those differences are nonzero. Engineering expectation: smaller range increases disconnection/private buffering and may reduce publication, but adaptive allocation can change the sign of mission progress.

**RQ3 primary:** H0: paired mean final published coverage difference is zero for 4 versus 8 drones, and 16 versus 8 drones. H1: those differences are nonzero. Engineering expectation: added agents may improve early coverage, with more contention/search overhead; neither productivity nor safety superiority is presumed.

Only final published coverage is a confirmatory primary endpoint. Connectivity, survivors, offline buffering/upload, tasks, energy and timing are secondary descriptive outcomes. No post-hoc substitution of the primary endpoint is allowed.

## Planned design and pilot decision

Five unique conditions form two shared-control comparisons:
- range_90: 8 drones, 90 px radio range;
- reference: 8 drones, 180 px;
- range_360: 8 drones, 360 px;
- swarm_4: 4 drones, 180 px;
- swarm_16: 16 drones, 180 px.

The shared reference is not simulated twice or counted as independent evidence. Default map is 72×52 cells, 14 px/cell; communication spans approximately 6.43/12.86/25.71 cells. Default weather, enabled failure probability, energy, collision, allocation and replay sampling remain unchanged. All conditions use the same map dimensions and fixed 60 Hz tick rate.

Main seeds fixed now: **41001, 41002, 41003, 41004, 41005, 41006, 41007, 41008**. They are a deterministic convenience sample, not a random sample of all possible worlds. None is a historical engineering seed. Paired world hashes must match. Agent count may change mission dynamics without changing terrain/zone generation.

Pilot: all five conditions at seed 49001, plus reference and swarm_16 at seed 49002, **600 ticks each**. Pilot is exploratory and excluded from all main estimates. Planned main horizon is **900 ticks (15 simulated seconds)** with no discarded warm-up; startup is part of early exploration. After pilot, retain 900 if estimated five-condition/eight-seed collection is practical and coverage varies. If a horizon/sample change is needed, record a versioned amendment before any main run, preserving these hypotheses and seeds rather than tuning for favorable outcomes.

32 drones is deferred based on approved Step 11 startup stalls; no need to repeat that expensive engineering scaling case for this initial study. This is an early-search study, not evidence for long-run completion/energy exhaustion.

## Measurement and units

Save full authoritative MissionMetrics, accounting counts/hash, energy diagnostics, final projection group hashes, world hash, config identity, weather/RNG state hashes and per-tick update latencies. No arbitrary composite intelligence/efficiency score will be analyzed.

Additional observation-only summaries:
- connectivity exposure = mean post-update connected drones / deployed drones over ticks 1..T;
- disconnected agent-ticks = sum of deployed minus connected, including unavailable radios;
- majority connectivity = fraction of ticks with strictly more than half connected;
- pending map/survivor exposure = mean sum of per-drone pending set sizes (duplicates across agents count);
- new pending map entries = sum of positive per-agent set additions between adjacent tick boundaries; repeat observations after sync can count again, not unique global cells;
- successful upload totals = existing per-drone offline_synced_cells / offline_synced_survivors;
- local disconnected survivor reports = existing survivor_local events with disconnected reason;
- per-survivor first-local-to-global publication delay, in ticks, pooled across drones; unreported by horizon is right-censored, never silently zero;
- first publication/time-to-10%-coverage: tick or null if not reached; report attainment, not uncensored time-to-event inference.

Derivations: coverage gain = final minus initial percentage; completion/award and cancellation/award fractions = null for zero awards; publication fraction = published zones / total zones, null if zero zones. Distinguish events from unique targets, waits from contacts, and charge from joules. No survivor-rescue outcome exists.

## Timing boundaries

Sequential headless runs; no rendering/profiler/concurrent tests. Time construction, each Mission.update, post-update observation, replay export and research-file write separately. A transparent instance wrapper times the existing CSV logger call without skipping it. Report inclusive update and update minus measured CSV-call wall time; subtraction is not pure CPU time and includes in-memory replay sampling. Research output/analysis/rendering is outside update. Record per-run mean/p50/p95/p99/max; timing is secondary observational evidence subject to host noise. Repeat one reference run; do not claim general real-time performance.

## Stopping, failure and resume

Run exactly T updates even if mission success occurs; retain frozen summary and live outcome separately. Never stop at significance. No operator/manual recovery. Policy-defined automatic recovery remains enabled and counted.

A crash, invalid/nonfinite output, world-pairing mismatch or missing event sequence is a recorded failed run with seed/condition/tick and traceback. Preserve failed/partial attempts; investigate before continuation. Do not exclude adverse outcomes. A complete valid artifact is never overwritten; resume verifies artifact checksum, run/config/source/harness identity and expected tick. A necessary corrected rerun gets a separate attempt directory and an explained manifest amendment. If primary pairs are incomplete, show missingness and do not quietly re-label n.

## Analysis plan

Per condition: n, mean, median, sample SD and IQR plus all seed values. For four predeclared coverage contrasts, effect size is paired mean difference in percentage points. No normality assumption or p-value fishing. Use paired nonparametric percentile bootstrap, **20,000 resamples**, NumPy PCG64 analysis seed **1502026**. Resample whole paired seed blocks, not ticks/drones.

Report ordinary 95% intervals and **98.75% Bonferroni-adjusted marginal intervals** for the family of four primary contrasts (nominal familywise 95%, approximate bootstrap coverage with only eight seeds). These are not exact simultaneous-coverage guarantees. Secondary outcomes get descriptive paired differences and 95% intervals explicitly without multiplicity-controlled hypothesis claims. No composite score, no optional stopping and no exploratory subgroup promoted to primary.

Classification: supported primary difference only if its adjusted interval excludes zero; otherwise unsupported evidence of difference, not proof of equivalence. Mixed describes tradeoffs across outcomes. Unexpected relationships remain exploratory. Small n/discrete outcomes and convenience seeds limit inferential interpretation.

## Output and reproducibility

Schema 1 raw JSON: status, manifest/run/source/harness identities, experiment canonical config and seed, runtime, horizon, world hash, initial/final metrics, accounting, observation summaries, sampled time series, latency arrays, timing boundaries, final covered-state group hashes, artifact paths/checksums. Raw files are immutable after publication, atomic, with a separate SHA-256 checksum. Names are manifest/condition/seed scoped, never timestamp-only.

A checked-in manifest fixes complete conditions, seed order and deterministic interleaved execution order (rotate conditions by seed to reduce monotonic order confounding). Source files and golden data remain unchanged. Reviewers can run the headless runner and regenerate analysis/tables/figures from raw outputs; no machine-local paths are required.

Hardware/runtime and source manifests are recorded separately. Analysis RNG is independent of simulation RNG. Engineering checks verify tooling/baseline integrity but are not research observations. Research outcomes are not proof of simulator correctness.
