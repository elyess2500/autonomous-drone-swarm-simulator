"""Test-only cleanup for process state and temporary output configuration."""
from contextlib import contextmanager
import copy
import os
from pathlib import Path
import random


@contextmanager
def isolated_process_state(output):
    import config
    import numpy as np
    import pygame
    from core.experiment import _active
    from core.utils import _font_cache

    values = {k: copy.deepcopy(v) for k, v in vars(config).items() if k.isupper()}
    py_state, np_state = random.getstate(), np.random.get_state()
    environment, directory = dict(os.environ), Path.cwd()
    token = _active.set(None)
    # Make the previous full-suite collection defaults explicit, per test.
    config.QUICK_DEMO_MODE = False
    config.FAILURE_PROB_PER_FRAME = 0.0
    config.AUTONOMOUS_OFFLINE_MODE = True
    config.METRICS_LOG_DIR = str(Path(output)/'csv')
    config.REPLAY_EXPORT_DIR = str(Path(output)/'replay')
    try:
        yield
    finally:
        _font_cache.clear()
        pygame.quit()
        _active.reset(token)
        for key in list(vars(config)):
            if key.isupper() and key not in values:
                delattr(config, key)
        for key, value in values.items():
            setattr(config, key, value)
        random.setstate(py_state)
        np.random.set_state(np_state)
        os.chdir(directory)
        # pytest owns this value and updates it between test phases.
        current_test = os.environ.get('PYTEST_CURRENT_TEST')
        os.environ.clear()
        os.environ.update(environment)
        if current_test is not None:
            os.environ['PYTEST_CURRENT_TEST'] = current_test
