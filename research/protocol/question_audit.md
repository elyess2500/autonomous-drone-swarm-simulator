# Step 15 candidate-question audit

The reference is the frozen approved Step 14 code. No intervention support is added to production.

- Communication range is already captured by ExperimentConfig and used by graph reachability and allocation/risk/relay spacing. Therefore the study estimates a total range-configuration effect, not transport alone.
- Swarm size is factory-owned and included in identity. Map construction precedes swarm creation; pilot hashes verify equal worlds across paired conditions. Added agents use agent-specific streams; equal seed does not imply identical task/failure trajectories across sizes.
- An energy-policy comparison has no clean existing control knob. Disabling reserve/admission would confound policy safety and task selection. Deferred instead of introducing an inferior straw-man control.
- Density/collision pressure could vary terrain or counts, but adds confounding and compute. Wait/backoff observations are secondary swarm-size outcomes, with collision protection intact.
- The existing mission_efficiency composite is retained only in full raw snapshots, not used as a research endpoint.
- Physical connectivity counts all deployed drones, so failed/stranded radios affect the denominator. This is explicitly defined rather than filtered post hoc.
- Historical 2026/2027/2031 traces validate engineering; research uses eight new fixed seeds. Pilot seeds are excluded.
- The early 900-tick horizon measures initial exploration/coordination, not steady state, eventual success or stranding elimination.
- CSV output timing is measured transparently inside the unchanged logger call; inclusive update is retained. Other observation/file work stays outside update timing.
- Per-tick ledger observation detects retention gaps and fails instead of silently losing publication timing events.
