# Interview guide

These are concise starting points, not a script or claims about real flight deployment.

**What problem does ADSS solve?**

It provides an inspectable environment for exploring how multiple autonomous agents divide search work while routes, connectivity, energy and shared space constrain them.

**Why build it?**

To integrate algorithms with stateful systems engineering. A plausible animation is easy to confuse with correct coordination; reproducible fixtures and explicit contracts make the difference reviewable.

**What was the hardest bug?**

A useful example is the discovery boundary: using delayed LOST_COMM state as a delivery gate leaked observations during the disconnection grace period. The fix separates immediate radio reachability from delayed behavior and synchronizes after post-motion connectivity refresh. First-tick, repeated partition and duplicate-upload regressions protect it.

**How does coordination work? Is it decentralized?**

A central swarm object runs Contract-Net-inspired bids for frontiers with sector fallback and relay assignments. Individual drones own state/motion, but assignment authority is centralized. I would not describe it as a distributed consensus or fully distributed Contract Net implementation.

**How do you avoid collisions?**

Forecast absolute-tick occupancy and arbitrate actual proposed point trajectories deterministically. Unsafe moves wait; bounded sidestep/backoff can retain tasks. Shared docking is explicit. Narrow corridors can still block, and finite drone bodies are outside the model.

**How does communication work?**

An ideal symmetric range graph and BFS determine base reachability through eligible peers. Disconnected observations stay local from the first tick; restored connectivity merges them deterministically. There are no packet, bandwidth or RF propagation dynamics.

**How does energy planning work?**

Price the executable route to the next work waypoint, expected work and route home using the same abstract drain function as execution, then add uncertainty and reserve. Current wind/weather are included conservatively; future traffic or weather is not guaranteed predictable.

**How did you make it deterministic?**

Fixed simulation ticks, owned named RNG streams, canonical experiment snapshots and deterministic decision ordering. Tests vary rendering, FPS settings, UI state and presentation randomness. The claim is exact tested equivalence, not formal cross-platform determinism.

**What did you optimize?**

Profiling showed known-route energy geometry repeatedly recomputed despite route-cache hits. I cached the pure calculation with full geometry keys and conservative context validation, leaving decisions and their events untouched.

**What tradeoffs did that introduce?**

Bounded cache memory and validity-check overhead; cold routes still cost time. Mean/p95/p99 improved in paired trials, but maxima rose and one median worsened. I kept those unfavorable numbers visible.

**How did you validate correctness?**

Hand-calculated unit fixtures, Dijkstra planner references, state/ownership invariants, failure injection and exact per-tick differential checks. Three 3,600-tick seeds preserved state/event/RNG/persistence behavior for the optimization; a separate 10,800-tick smoke protects longer recovery behavior.

**What makes this more than a visual demo?**

The engine runs without graphical initialization. Queryable accounting, versioned playback, explicit outcome semantics, portable deterministic goldens and measured optimization provide evidence independent of the UI.

**What are its limitations?**

Central coordination, point agents, idealized radio, abstract energy, no physical flight or survivor rescue, no checkpoint continuation and no real-time guarantee. Hosted CI/Linux runtime and exact cross-platform reproducibility remain unverified.

**What would you improve next?**

After separate approval, define a small controlled experiment protocol with fixed configurations, explicit hypotheses, repeated seeds and supported metrics. Avoid presenting a new algorithm as better without comparable evidence.

**How would you move toward real drones?**

Treat it as a separate safety/robotics project: vehicle dynamics, localization uncertainty, finite-body clearance, delayed/lossy telemetry, hardware interfaces and hardware-in-the-loop testing would all need explicit contracts. This simulator is not directly deployable flight software.

Use [claims and evidence](claims_and_evidence.md) to substantiate answers. [Portfolio wording](portfolio_summary.md) supplies shorter descriptions.
