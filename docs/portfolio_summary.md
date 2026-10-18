# Portfolio summary

Use these as editable descriptions, with evidence and limitations available to reviewers. Do not present collected tests as a newly executed full-suite pass.

## One sentence

Built ADSS, a deterministic Python/Pygame multi-agent drone simulator combining planning, centralized coordination, communication-limited discovery, route-aware energy admission and point-agent collision arbitration.

## Short description (about 50 words)

ADSS explores autonomous search with cooperating simulated drones. It combines A* planning, task ownership, relay connectivity, private discovery buffers and route-aware charge reserves. A headless engine, inspectable UI, detached replay and deterministic accounting make behavior testable. Profiling and exact differential checks support measured optimization without changing the approved simulation policy.

## Extended description (about 150 words)

ADSS is a Python/Pygame autonomous multi-agent simulation project built to make coordination decisions inspectable and reproducible. Drones explore generated terrain using A* routes and centralized Contract-Net-inspired frontier/sector allocation. They manage abstract charge through route-aware task admission and return reserves, coordinate point trajectories through reservations and execution arbitration, and keep discoveries private while disconnected from base.

The engineering work includes fixed simulation ticks, isolated RNG streams, immutable experiment identity, a supported headless factory, versioned detached playback and deterministic event accounting. Reliability gates cover hand-calculated fixtures, persistence failures, golden traces and presentation independence. Profiling identified repeated route-energy geometry; bounded reuse preserved exact three-seed behavior while paired trials showed lower mean and p95/p99 update cost.

The UI exposes mission, task, communication and energy context while labeling ground-truth diagnostics explicitly. ADSS models abstract autonomy rather than physical flight, realistic RF, survivor rescue or checkpoint continuation. Its evidence and limitations are documented alongside the implementation.

## Technical scope

- Python state machines, grid search and shared movement geometry.
- Centralized task lifecycle, relay roles and connectivity-gated knowledge.
- Fixed-time deterministic experiments and presentation-independent state.
- Route-aware energy feasibility and bounded pure-cost memoization.
- Immutable accounting records, sampled persistence and failure diagnostics.
- Incremental architecture separation with source/differential validation.

## Resume bullet alternatives

Choose two or three relevant bullets rather than combining every number.

- **Autonomy:** Built a multi-agent drone simulator integrating A*, centralized task allocation, radio-constrained discovery, route-aware energy reserves and point-agent collision arbitration.
- **Software engineering:** Separated headless simulation from Pygame orchestration while preserving exact tested state, RNG, accounting and replay behavior across presentation conditions.
- **Performance:** Profiled repeated route-energy geometry and introduced bounded pure-result reuse; paired 3,600-tick trials showed 38.8–49.9% lower mean update latency across three seeds with exact authoritative equivalence.
- **Reliability:** Maintained 336 collected regression cases with FAST/STANDARD/HEAVY gates, deterministic goldens and persistence failure injection; last full suite passed 333 cases, followed by 23 passing post-polish UI cases.
- **Observability:** Implemented deterministic event accounting and detached sampled replay, with explicit local/global discovery semantics and a selected-drone mission inspector.

Timing caveat for interview discussion: maxima increased in the performance trials; no real-time guarantee or universal speedup was demonstrated.

## LinkedIn / project description

ADSS — Autonomous Drone Swarm Simulator. A Python/Pygame project exploring how planning, coordination, connectivity and energy constraints interact in autonomous search. I developed a deterministic headless engine, centralized task ownership, point-agent deconfliction, private discovery buffering, route-aware energy admission and an inspectable mission UI. Regression fixtures and multi-seed differential checks protect behavior; profiling guided a pure-computation cache rather than reduced simulation fidelity. The repository includes measured results, reproducible validation commands and explicit model limitations.

[Technical claims and evidence](claims_and_evidence.md) · [Interview guide](interview_guide.md)

## Controlled research component

Designed and executed a preregistered study of communication-range and swarm-size trade-offs: 40 runs across eight paired seeds and five configurations, each lasting 900 simulation ticks. Preserved raw measurements, exact configuration/source identities and reproducible bootstrap uncertainty, with pilot data kept separate.

Within this early-search model, sixteen versus eight drones increased mean published coverage by 3.15 percentage points (98.75% paired-bootstrap interval 2.24–3.91), accompanied by substantially higher update cost. These bounded results complement engineering validation; they do not establish physical-flight performance or eventual mission success. [Research report](research_report.md) · [Protocol](research_protocol.md)
