"""Cold-process headless/import checks and lightweight source/workflow checks."""
import argparse
import importlib.abc
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def headless():
    class NoUI(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *args):
            if fullname == 'main' or fullname == 'ui' or fullname.startswith('ui.'):
                raise AssertionError('Headless engine imported presentation: '+fullname)
    guard = NoUI()
    sys.meta_path.insert(0, guard)
    try:
        import pygame
        import config
        from core.simulation import make_simulation
        from core.replay import ReplayPlayer, load
        from benchmarks.step9 import inspect
        def forbidden(*args, **kwargs):
            raise AssertionError('Headless engine requested graphical/input service')
        pygame.init = pygame.display.init = pygame.display.set_mode = forbidden
        pygame.font.init = pygame.mixer.init = pygame.Surface = pygame.time.Clock = forbidden
        pygame.event.get = pygame.key.get_pressed = pygame.mouse.get_pos = forbidden
        with tempfile.TemporaryDirectory(prefix='adss-sanity-') as tmp:
            config.METRICS_LOG_DIR = config.REPLAY_EXPORT_DIR = tmp
            mission = make_simulation(2026)[2]
            for _ in range(6):mission.update()
            assert mission.frame == 6 and mission.outcome == 'running'
            assert inspect(mission) == inspect(mission)
            ReplayPlayer(load(mission.export_replay()))
            assert not pygame.get_init() and not pygame.display.get_init()
            assert not pygame.font.get_init() and pygame.display.get_surface() is None
            assert 'main' not in sys.modules and not any(k == 'ui' or k.startswith('ui.') for k in sys.modules)
        print('PASS: core import, construct, advance, inspect, replay; no graphical initialization or UI imports')
    finally:
        sys.meta_path.remove(guard)


def static():
    import re
    import yaml
    files = [*ROOT.glob('*.py')]
    for directory in ('core','ui','tests','validation','benchmarks'):
        files.extend((ROOT/directory).glob('*.py'))
    for path in files:
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
        assert workflow['permissions'] == {'contents':'read'}, path
        assert 'pull_request_target' not in workflow['on'], path
        for job in workflow['jobs'].values():
            assert int(job['timeout-minutes']) > 0
            for step in job['steps']:
                if 'uses' in step:
                    assert re.fullmatch(r'actions/[\w-]+@[0-9a-f]{40}',step['uses']), step
                assert 'C:/Users/' not in str(step) and 'C:\\Users\\' not in str(step)
    print(f'PASS: {len(files)} Python sources compiled in memory; local workflow structure checks')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static', action='store_true')
    args = parser.parse_args()
    if args.static:static()
    else:headless()
