"""Measured, explicit pytest selection rules; never auto-retier from runtime."""
import json
from pathlib import Path

TIERS = {'fast', 'standard', 'heavy'}
REGISTRY = Path(__file__).with_name('test_contracts.json')


def contracts():
    return json.loads(REGISTRY.read_text(encoding='utf-8'))


def classify(nodeid, explicit=()):
    marked = TIERS.intersection(explicit)
    rule = contracts()['families'].get(nodeid.split('[')[0])
    if rule is None:
        if len(marked) != 1:
            raise ValueError(f'New test needs one explicit tier marker: {nodeid}')
        return dict(tier=next(iter(marked)), graphical='graphical' in explicit,
                    deterministic='deterministic' in explicit, contract='reliability',
                    baseline_max_seconds=None, long_simulation=False, filesystem=True,
                    rationale='explicit new-test tier; review measured duration')
    if marked and marked != {rule['tier']}:
        raise ValueError(f'Conflicting tier markers: {nodeid}')
    return dict(rule)


def audit_nodes(nodeids):
    missing = set(contracts()['baseline_nodeids']) - set(nodeids)
    if missing:
        raise ValueError('Approved regression tests missing from collection: '+', '.join(sorted(missing)))
