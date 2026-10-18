"""Supported simulation construction without application/UI initialization.

    from core.simulation import make_simulation
    from core.experiment import ExperimentConfig
    world, swarm, mission, resolved_seed = make_simulation(
        2026, experiment_config=ExperimentConfig.capture())
    for _ in range(300):
        mission.update()
    metrics = mission.analytics.sample(mission)  # Pure query; dataclass snapshot.
    accounting = swarm.accounting.snapshot()   # Detached dictionary.
    outcome, final_summary = mission.outcome, mission.summary()

One update is the existing fixed 1/60-second tick. Explicit updates may continue
past completion; mission duration/final summary remain frozen. If a replay player
is attached, Mission.update retains its established detached-playback behavior.

Construction retains existing CSV/replay recording. Output directories remain
runtime config settings. Writers open/close files per operation; no display,
thread, event loop or persistent file handle needs shutdown. Drop the returned
objects after any desired export. Pygame remains an installed/imported dependency
of compatible core drawing helpers, but this API never initializes it.
"""
import config
from core.experiment import Experiment
from core.map import Map
from core.swarm import Swarm
from core.mission import Mission


def make_simulation(seed=None, *, experiment_config=None):
    """Capture a reproducible experiment; UI settings remain runtime mutable."""
    if seed is None:
        seed = config.RANDOM_SEED
    experiment = Experiment(seed, experiment_config)
    with experiment.activate():
        game_map = Map(experiment=experiment)
        swarm = Swarm(game_map, experiment.config.settings['NUM_DRONES'])
        mission = Mission(game_map, swarm)
    return game_map, swarm, mission, experiment.seed
