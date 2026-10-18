"""Explicit test isolation, measured tiers and reproducible inventory/order."""
import json
from pathlib import Path
import random
import pytest
from validation.isolation import isolated_process_state
from validation.selection import classify, audit_nodes


def pytest_addoption(parser):
    parser.addoption('--inventory', type=str, help='Write collected test metadata and measured phase durations')
    parser.addoption('--audit-inventory', action='store_true', help='Require all 302 approved node IDs in full collection')
    parser.addoption('--test-order', choices=('normal','reverse','shuffle'), default='normal')
    parser.addoption('--order-seed', type=int, default=2026)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    inventory = {}
    for item in items:
        try:
            rule = classify(item.nodeid, {m.name for m in item.iter_markers()})
        except ValueError as exc:
            raise pytest.UsageError(str(exc)) from exc
        if not item.get_closest_marker(rule['tier']):
            item.add_marker(getattr(pytest.mark,rule['tier']))
        for mark in ('graphical','deterministic'):
            if rule[mark] and not item.get_closest_marker(mark):
                item.add_marker(getattr(pytest.mark,mark))
        inventory[item.nodeid] = dict(nodeid=item.nodeid,file=str(item.path.relative_to(config.rootpath)),
            markers=sorted({m.name for m in item.iter_markers()}),**rule,phase_seconds={},outcomes={})
    if config.getoption('--audit-inventory'):
        try:audit_nodes(inventory)
        except ValueError as exc:raise pytest.UsageError(str(exc)) from exc
    config._adss_inventory = inventory
    order = config.getoption('--test-order')
    if order == 'reverse':items.reverse()
    elif order == 'shuffle':random.Random(config.getoption('--order-seed')).shuffle(items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    record = item.config._adss_inventory[item.nodeid]
    record['phase_seconds'][report.when] = report.duration
    record['outcomes'][report.when] = report.outcome


def pytest_sessionfinish(session, exitstatus):
    target = session.config.getoption('--inventory')
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True,exist_ok=True)
        records = list(getattr(session.config,'_adss_inventory',{}).values())
        for record in records:
            record['measured_seconds'] = sum(record['phase_seconds'].values()) if record['phase_seconds'] else None
        path.write_text(json.dumps(dict(schema=1,exit_status=int(exitstatus),tests=records),indent=2)+'\n',encoding='utf-8')


@pytest.fixture(autouse=True)
def process_state(tmp_path):
    with isolated_process_state(tmp_path):
        yield
