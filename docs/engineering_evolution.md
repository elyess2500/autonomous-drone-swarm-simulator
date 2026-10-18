# Engineering evolution

ADSS evolved through narrow, separately reviewed tranches. The recurring method was to reproduce a defect, specify a contract, implement the smallest fix, then compare tests and measured behavior. This history explains decisions; the current [architecture](architecture.md) and [algorithms](algorithms.md) are the primary implementation guides.

| Work | Engineering lesson | Detailed record |
| --- | --- | --- |
| Steps 1–3: movement, A*, ownership | Execution and planning must agree; stale heap entries and task replacement churn need concrete regressions | [Phase 1](phase1_engineering_report.md) |
| Step 4: reservations and execution | Sparse waypoints and search cost are not a trajectory/time contract; forecasts need enforcement | [Step 4](step4_engineering_report.md) |
| Step 5: discovery boundaries | Delayed LOST_COMM policy must not leak observations during grace ticks | [Step 5](step5_engineering_report.md) |
| Step 6: clock/RNG/config | Reproducibility needs simulation-owned time/randomness and explicit configuration identity | [Step 6](step6_engineering_report.md) |
| Step 7: playback/persistence | A recording must embed its world; playback is different from continuation | [Step 7](step7_engineering_report.md) |
| Step 8: accounting/outcome | Count logical mutations; distinguish discovery from rescue and sampled state from events | [Step 8](step8_engineering_report.md) |
| Step 9: headless boundary | Structural UI separation can be incremental without removing every core render helper | [Step 9](step9_engineering_report.md) |
| Step 10: route energy | A nearby goal may require an expensive detour; charging readiness is not physical departure | [Step 10](step10_engineering_report.md) |
| Step 11: measured optimization | Reuse pure geometry while preserving decisions, side effects, RNG and event ordering | [Step 11](step11_engineering_report.md) |
| Step 12: reliability | Test collection and Pygame lifecycle can leak state; tiers separate fast feedback from long smoke | [Step 12](step12_engineering_report.md) |
| Step 13: operational UI | Present published knowledge by default, label omniscience, and test rendering as an observer | [Step 13](step13_engineering_report.md) |

Historical report counts/timings remain historical. The Step 13 report includes its final menu-alignment addendum: a one-line actual-text-rectangle centering fix and three additional size regressions. Current collection is 336 tests; that does not retroactively change the earlier 333-test full run.

Step 14 documents the approved implementation and curates actual captures. Step 15 research comparisons remain a recommendation requiring separate approval.
