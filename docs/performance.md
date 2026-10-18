# Performance: measurements and boundaries

The fixed tick is 1/60 simulation second. It is not a real-time deadline guarantee. Engine update, profiling and rendering measurements have different boundaries and must not be combined.

## Why route-energy geometry was optimized

The [Step 11 report](step11_engineering_report.md) records frozen Step 10 profiles for seeds 2026/2027/2031. In one sampled seed-2026 window, total profiled time was about 91.5 s; energy estimation was about 67 s and route-energy geometry about 55 s (nested cumulative values overlap). Of 190,104 route lookups, 189,302 already hit the route cache. Recomputing known-route energy geometry, rather than route generation alone, was the measured target.

A per-drone 1,024-entry FIFO cache reuses the pure route-energy calculation. Complete geometry/activity/weather keys and conservative terrain/config/helper context checks protect validity. Custom map geometry bypasses it. It preserves assessment cadence, feasibility checks, accounting and events; it does not cache policy decisions.

## Clean simulation update trials

Fresh sequential 3,600-update baseline/candidate runs; eight drones, same seed/configuration and timing boundaries. Normal in-update persistence is included; rendering, profiling and state inspection are excluded.

| Seed | Version | Mean ms | p50 ms | p95 ms | p99 ms | Max ms |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 | Step 10 | 40.659 | 21.577 | 91.843 | 139.510 | 601.061 |
| 2026 | Step 11 | 20.363 | 17.216 | 37.636 | 92.109 | 823.526 |
| 2027 | Step 10 | 105.045 | 107.613 | 227.072 | 327.168 | 707.580 |
| 2027 | Step 11 | 54.840 | 50.017 | 122.347 | 259.550 | 1425.107 |
| 2031 | Step 10 | 33.091 | 10.434 | 84.434 | 119.191 | 595.397 |
| 2031 | Step 11 | 20.260 | 12.336 | 41.963 | 73.630 | 827.810 |

Observed means fell 49.9%, 47.8% and 38.8%; p95/p99 fell for all three seeds. **All maxima rose**, and seed 2031's median rose. Candidate 2026 repeat mean was 23.003 ms, illustrating timing variation despite exact behavioral equality. One paired trial per seed does not establish confidence intervals or attribute every wall-time difference to the cache.

The per-tick differential, detailed checkpoints, final state, energy diagnostics, accounting/event hashes, RNG, replay and CSV matched Step 10. Assessments remained 246,605 / 711,189 / 182,857 and counted searches remained 5,331 / 6,455 / 3,400. No fidelity reduction supplied the speed benefit.

## Bounded scaling

Seed 2026, 180 ticks, sequential pairs; startup work is substantial.

| Drones | Before mean ms | After mean ms | Before p95 ms | After p95 ms |
| --- | --- | --- | --- | --- |
| 8 | 36.174 | 34.768 | 39.370 | 37.114 |
| 16 | 147.097 | 118.689 | 303.869 | 133.588 |
| 32 | 1448.587 | 524.116 | 2030.936 | 814.933 |

At 32 drones, maximum latency increased from 25.301 s to 29.386 s. At 16 drones p99 increased. Sector allocation and route searches dominated the sampled post-cache large-swarm profile. Reservation geometry, frontier construction and allocation remain meaningful default-workload costs. This is not sustained large-swarm scalability evidence.

## Rendering measured separately

[Step 13 rendering evidence](step13_engineering_report.md) uses the same real tick-3,600 state, five warm-ups and 30 draws per mode. Draw timing excludes simulation updates, image saving and display flip.

| Mode | Step 12 mean / p95 ms | Step 13 mean / p95 ms |
| --- | --- | --- |
| Normal | 8.146 / 9.102 | 6.939 / 7.334 |
| Overlays off | 6.801 / 7.628 | 6.931 / 7.325 |
| Major overlays | 27.748 / 32.610 | 7.870 / 8.299 |
| Dense zoom | 24.900 / 31.325 | 9.142 / 11.865 |

UI composition changed, including default diagnostic suppression and a new inspector. These are representative composition costs, not identical visual work or proof of engine optimization. Overlays-off mean was slightly higher. No new timing campaign was run for documentation.

## Reproduce responsibly

Use the commands in [validation](validation.md) for clean, profile and bounded scaling modes. Run jobs sequentially with no concurrent test/profile workload, retain seed/config/source/runtime details and compare the same timer boundaries. Profiler time is not clean latency. Follow the golden/differential gate before accepting an optimization. No performance threshold is a correctness substitute.
