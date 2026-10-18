# Claims and evidence

This is the source-of-truth index for current documentation. Historical reports describe their own closure, not necessarily the current test inventory. Results establish the covered configurations and projections, not universal proofs.

| Public claim | Implementation | Regression / approved evidence | Boundary |
| --- | --- | --- | --- |
| Corrected A* labels and explicit results | [pathfinding](../core/pathfinding.py) | [planner tests](../tests/pathfinding_tests.py), [Phase 1](phase1_engineering_report.md) | Dijkstra comparison is for stated costs; smoothing/coordination is not globally optimal |
| Stable centralized Contract-Net-inspired ownership | [swarm](../core/swarm.py) | [lifecycle tests](../tests/task_lifecycle_tests.py), [Phase 1](phase1_engineering_report.md) | Not distributed CNP |
| Tick-time point-agent deconfliction | [intelligence](../core/intelligence.py), [geometry](../core/geometry.py) | [reservation tests](../tests/reservation_tests.py), [Step 4](step4_engineering_report.md) | Shared dock, finite backoff, no physical/deadlock guarantee |
| First-disconnected-tick publication gating | [communication](../core/communication.py), [drone](../core/drone.py) | [communication tests](../tests/communication_tests.py), [Step 5](step5_engineering_report.md) | Ideal graph and abstract synchronization |
| Deterministic fixed-tick configuration/RNG | [experiment](../core/experiment.py) | [experiment tests](../tests/experiment_tests.py), [Step 6](step6_engineering_report.md), [Step 13](step13_engineering_report.md) | Tested presentation conditions; no cross-platform proof |
| Self-contained detached sampled playback | [replay](../core/replay.py), [persistence](../core/persistence.py) | [replay tests](../tests/replay_tests.py), [Step 7](step7_engineering_report.md) | No checkpoint/continuation |
| Explicit event/metric/outcome semantics | [accounting](../core/accounting.py), [analytics](../core/analytics.py), [mission](../core/mission.py) | [accounting tests](../tests/accounting_tests.py), [Step 8](step8_engineering_report.md) | Bounded log; rescue unsupported; no invented failure policy |
| Headless construction and stepping | [factory](../core/simulation.py) | [headless tests](../tests/headless_tests.py), [Step 9](step9_engineering_report.md) | Pygame imports remain; no graphical initialization required |
| Route-aware charge admission and readiness | [energy](../core/energy.py), [battery](../core/battery.py) | [energy tests](../tests/energy_tests.py), [Step 10](step10_engineering_report.md) | Abstract units, next waypoint, uncertain future traffic/weather |
| Measured pure-cost optimization with exact tested behavior | [energy](../core/energy.py) | [performance tests](../tests/performance_tests.py), [Step 11](step11_engineering_report.md) | Single paired timings; maxima worsened |
| Portable deterministic gates and pinned test environment | [validation](../validation), [requirements](../requirements-test.txt) | [reliability tests](../tests/reliability_tests.py), [Step 12](step12_engineering_report.md) | Hosted Actions/Linux execution unverified |
| Observer-only operational UI and published survivor markers | [presentation](../ui/presentation.py), [console](../ui/console.py), [viewer](../ui/replay_view.py) | [UI tests](../tests/ui_tests.py), [Step 13](step13_engineering_report.md) | Tested sizes/interactions; legacy helper calls are not the supported view |

## How to quote the evidence

- Prefer “zero observed field point contacts in the measured probes” over “collision-free.”
- Prefer “336 collected tests; 333 passed in the last full run, followed by 23 passing post-polish UI cases” over claiming a new 336-test full pass.
- Prefer “exact per-tick covered-state equality for three 3,600-tick seeds” over a formal determinism claim.
- Prefer “38.8–49.9% lower mean update time in paired trials” with tail caveats over a guaranteed speedup.
- Prefer “locally validated GitHub Actions workflows” over “CI passed.”

The [validation guide](validation.md) is the maintained command reference. Detailed local evidence is preserved under benchmark results; source/test/golden gates do not require a developer-specific frozen directory. Historical reports are provenance, not installation instructions.
