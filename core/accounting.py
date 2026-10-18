"""Version 1 deterministic accounting, not an event-sourced simulation.

One ledger per swarm, including construction at tick zero. Retain the last 4096
records; lifetime counts and a chained SHA-256 digest survive record eviction.
Events describe successful mutations, so idempotence belongs at the mutation
site (two real actions in one tick remain two events). No object references.
"""
from collections import Counter, deque
from dataclasses import dataclass, asdict
import hashlib
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class Event:
    version: int
    tick: int
    sequence: int
    kind: str
    actor: int | None
    subject: str | None
    reason: str
    payload_json: str


class Accounting:
    def __init__(self, limit=4096):
        self.tick = 0
        self.sequence = 0
        self._counts = Counter()
        self._records = deque(maxlen=limit)
        self._digest = bytes(32)

    def emit(self, kind, actor=None, subject=None, reason='', **payload):
        encoded = canonical(payload)
        event = Event(1, self.tick, self.sequence, kind, actor,
                      None if subject is None else str(subject), reason, encoded)
        self.sequence += 1
        self._counts[kind] += 1
        self._records.append(event)
        self._digest = hashlib.sha256(self._digest + canonical(asdict(event)).encode()).digest()

    def count(self, kind):
        return self._counts[kind]

    @property
    def records(self):
        return tuple(self._records)

    def snapshot(self):
        return dict(version=1, tick=self.tick, total_events=self.sequence,
                    retained_events=len(self._records), retention_limit=self._records.maxlen,
                    counts=dict(sorted(self._counts.items())), event_hash=self._digest.hex())


EVENT_METRICS = dict(task_awards='task_awarded', task_completions='task_completed',
            task_cancellations='task_cancelled', path_searches='path_search',
            partitions='partition', reconnects='reconnect', lost_comm_entries='lost_comm_entry',
            discovery_uploads='discovery_upload', collision_rejections='collision_rejected',
            collision_waits='collision_wait', backoff_attempts='backoff_attempt',
            backoffs='backoff_initiated', exhausted_backoffs='backoff_exhausted',
            field_contacts='field_contact', charging_starts='charging_started',
            charging_completions='charging_completed', relaunches='relaunch',
            hardware_failures='hardware_failure', stranded_transitions='stranded')
