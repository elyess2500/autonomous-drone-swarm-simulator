# First-tranche validation

Run from the repository root, without another simulation or test run competing
for CPU:

```powershell
python benchmarks/tranche1.py --label local --seeds 2026 2027 2031 --ticks 3600 --output local-results.json
```

The harness uses the normal map and eight-drone mission, headless, with failure
probability zero, demo mode disabled and offline autonomy enabled. Weather,
battery, radio, analytics and replay sampling remain active. CSV output goes to
a temporary directory. It measures `Mission.update` with `perf_counter`; counter
wrappers are included, while post-update invariant checks are excluded.

Interpretation:

- Frontier awards/completions are swarm counters; completion means finishing the
  assigned local scan packet, not revealing an entire sector.
- Unfinished-task replacements count frontier acceptance while a previous
  frontier ID and nonempty queue still exist. Explicit cancellations before a
  later award are reported separately by reason in the corrected implementation.
- Path searches count actual calls from the drone module, including return-path
  feasibility checks, initialization, reroutes and new assignments.
- Relay/task conflicts count attempts to give frontier/sector work to an active
  relay. They are not radio outages or physical collisions.
- Orphaned ownership is the sum of inconsistent sector/frontier/drone projections
  over all ticks, plus a separate final-tick count. It is not a count of distinct
  tasks. Tests additionally compare all projections to the authoritative registry.
- Connectivity is the fraction of drones with a graph path to base, averaged
  over ticks. Minimum connectivity is the worst tick.
- Update latency is in milliseconds. These are local single-run distributions,
  not confidence intervals or universal throughput claims. Different corrected
  trajectories do different amounts of work, so mission latency is not an
  isolated A* microbenchmark.
- The final state hash covers fog, survivor discoveries, weather, and each
  drone's position, state, battery, path and queue. Repeated identical hashes and
  counters provide evidence of headless reproducibility; they do not prove that
  rendering or every platform preserves random-number consumption.

Saved baseline results were captured before production changes at `b400109`.
Step 1 and Step 2 intermediate results use seed 2026; the final comparison uses
all three baseline seeds. See the Phase 1 engineering report for limitations and
the full-suite validation history.
