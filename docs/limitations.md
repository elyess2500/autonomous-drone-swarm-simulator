# Model and evidence limitations

These boundaries are part of the project contract, not a list of promised features.

| Area | Implemented abstraction | What is not established |
| --- | --- | --- |
| Coordination | Centralized Contract-Net-inspired allocation, frontier/sector work and relay roles | Fully distributed negotiation, consensus, globally optimal assignment or guaranteed coverage |
| Motion | Grid planning and capped point-center trajectories | Aerodynamics, inertia, finite body clearance, flight control or real hardware integration |
| Deconfliction | Absolute-tick forecasts, execution checks, deterministic waits and bounded backoff | Collision freedom for physical aircraft, deadlock-free corridors or complete MAPF |
| Docking | Shared physical base disk with explicit occupancy exception | Charging-pad scheduling or multi-base logistics |
| Communication | Symmetric range graph, base reachability and abstract instant synchronization | RF attenuation/interference, packets, bandwidth, loss, latency or received-network telemetry |
| Knowledge | Local/pending observations and globally published map/survivors | Decentralized mapping, localization uncertainty or SLAM |
| Energy | Abstract charge per activity/tick; route + return + overhead + reserve estimate | Joules, electrochemistry or guaranteed safety under future weather/traffic/recovery |
| Mission outcome | 98% coverage OR all nonempty survivor zones published | Survivor rescue, proof every drone returns, terminal failure classification or a mission deadline |
| Replay | Versioned self-contained sampled detached playback | Checkpoint restore, deterministic continuation or full event reconstruction |
| Accounting | Bounded event records with lifetime counters/hash and pure queries | An indefinitely retained log or a complete state-restoration stream |
| Determinism | Exact covered-state equality in tested seeds/configurations/presentation conditions | Formal proof over all maps, all Python state, runtime upgrades or cross-platform floating point |
| Performance | Profile-driven pure-calculation reuse with measured workload benefit | Real-time 60 Hz, bounded maximum latency or smooth large-swarm scaling |
| Validation | Local Windows runs, pinned environment, goldens and configured CI | Hosted GitHub success, Linux runtime success, security certification or exhaustive input coverage |
| UI | Published-survivor default, labeled debug mode and observer-tested instrumentation | Real received telemetry, arbitrary-resolution/DPI certification or a full accessibility audit |

## Important interpretation details

- Coverage excludes obstacles but includes no-fly cells in the denominator. It is a published-map metric, not a complete reachable-flight-area metric.
- Sensor discoveries and publication are distinct; multiple local observations can refer to one survivor zone. The rescue metric is unsupported rather than fabricated.
- The `Y` operator action recovers stranded drones. Emergency recovery policies and manual interventions must be recorded when interpreting runs.
- Proximity episodes, rejected proposals, waits and actual point contacts have different meanings. Do not substitute one count for another.
- A ready drone waiting at base is not repeatedly relaunching or completing charge. Actual relaunch is distinct from a state transition.
- Replay records private diagnostics but the normal viewer respects publication boundaries. Low-level legacy rendering helpers are not a substitute for the supported operational view.
- Settings snapshots cover a defined configuration set, not arbitrary monkey patches, source revision, output paths or interpreter state.
- Published timing pairs are observations from one host, without confidence intervals. Some maxima and a median worsened; short scaling probes are not sustained throughput evidence.

See [claims and evidence](claims_and_evidence.md), [validation](validation.md) and [performance](performance.md) before quoting results.
