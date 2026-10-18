"""Fixed tick time, owned random streams and the experiment configuration boundary.

Factory construction and Mission.update activate a snapshot without mutating the
config module. Standalone low-level calls retain legacy live-config semantics;
use experiment.activate() when driving components outside Mission.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import random
from types import MappingProxyType
import config as defaults

TICK_HZ = 60
SCHEMA = 1
RNG_VERSION = 'adss-streams-v1'
_active = ContextVar('adss_experiment', default=None)
_presentation = {
    'WINDOW_TITLE', 'SCREEN_WIDTH', 'SCREEN_HEIGHT', 'TARGET_FPS',
    'MAP_OFFSET_X', 'MAP_OFFSET_Y', 'MAP_PIXEL_W', 'MAP_PIXEL_H',
    'BASE_RADIUS_PX', 'DRONE_RADIUS', 'METRICS_LOG_DIR', 'REPLAY_EXPORT_DIR',
    'RANDOM_SEED',
}


def _setting_names():
    return sorted(k for k in vars(defaults) if k.isupper() and
                  not k.startswith(('C_', 'FONT_')) and k not in _presentation)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class ExperimentConfig:
    """Canonical JSON is the immutable source; settings returns a frozen view."""
    canonical_json: str

    def __post_init__(self):
        value = json.loads(self.canonical_json)
        if (value.get('schema') != SCHEMA or value.get('tick_hz') != TICK_HZ or
                set(value.get('settings', {})) != set(_setting_names())):
            raise ValueError('Unsupported or incomplete experiment configuration')
        object.__setattr__(self, 'canonical_json', _canonical(value))
        object.__setattr__(self, 'settings', _freeze(value['settings']))

    @classmethod
    def capture(cls):
        return cls(_canonical(dict(schema=SCHEMA, tick_hz=TICK_HZ,
                                   settings={k:getattr(defaults,k) for k in _setting_names()})))

    @classmethod
    def from_json(cls, text):
        return cls(text)


class Experiment:
    def __init__(self, seed=None, config=None):
        self.seed = random.SystemRandom().randrange(2**63) if seed is None else seed
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise TypeError('Experiment seed must be an integer')
        self.config = config if config is not None else ExperimentConfig.capture()
        self._streams = {}
        identity = dict(seed=self.seed, rng=RNG_VERSION,
                        configuration=json.loads(self.config.canonical_json))
        self.canonical_json = _canonical(identity)
        self.identity = hashlib.sha256(self.canonical_json.encode()).hexdigest()

    def stream(self, domain, agent_id=None):
        """Stable named PRNGs; separation is not a statistical independence proof."""
        key = (domain, agent_id)
        if key not in self._streams:
            # Retain seeded world geometry. Other domains use labeled SHA-256.
            material = _canonical([RNG_VERSION, self.seed, domain, agent_id]).encode()
            seed = self.seed if key == ('world', None) else int.from_bytes(hashlib.sha256(material).digest(), 'big')
            self._streams[key] = random.Random(seed)
        return self._streams[key]

    @contextmanager
    def activate(self):
        token = _active.set(self)
        try:
            yield self
        finally:
            _active.reset(token)


class _Settings:
    def __getattr__(self, name):
        experiment = _active.get()
        if experiment is not None and name in experiment.config.settings:
            return experiment.config.settings[name]
        return getattr(defaults, name)


settings = _Settings()


def in_experiment(method):
    @wraps(method)
    def bound(self, *args, **kwargs):
        with self.experiment.activate():
            return method(self, *args, **kwargs)
    return bound


@dataclass
class SimulationClock:
    tick: int = 0

    @property
    def seconds(self):
        return self.tick / TICK_HZ
