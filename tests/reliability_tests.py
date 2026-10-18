"""Step 12 infrastructure contracts; never alter simulation policy."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('module', ['battery_docking_tests.py', 'gameplay_smoke.py'])
@pytest.mark.fast
def test_legacy_collection_does_not_mutate_configuration(module):
    code = '''
import copy, runpy, sys
import config
config.FAILURE_PROB_PER_FRAME = .123
config.QUICK_DEMO_MODE = True
config.AUTONOMOUS_OFFLINE_MODE = False
before = {k:copy.deepcopy(v) for k,v in vars(config).items() if k.isupper()}
runpy.run_path(sys.argv[1], run_name='collection_probe')
after = {k:v for k,v in vars(config).items() if k.isupper()}
assert before == after, {k:(before[k],after[k]) for k in before if before[k]!=after[k]}
'''
    result = subprocess.run([sys.executable, '-c', code, str(ROOT/'tests'/module)],
                            cwd=ROOT, text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.standard
@pytest.mark.graphical
def test_isolation_restores_process_state_after_exception(tmp_path):
    import config
    import copy
    import os
    import random
    import numpy as np
    import pygame
    from core.experiment import Experiment, _active
    from core.utils import _font_cache
    from validation.isolation import isolated_process_state
    settings = {k:copy.deepcopy(v) for k,v in vars(config).items() if k.isupper()}
    py, numpy = random.getstate(), np.random.get_state()
    cwd = Path.cwd()
    with pytest.raises(RuntimeError, match='isolation probe'):
        with isolated_process_state(tmp_path/'inner'):
            config.DRONE_SPEED = 999
            config.ISOLATION_PROBE = True
            random.random(); np.random.random()
            os.environ['ADSS_ISOLATION_PROBE'] = 'changed'
            os.chdir(tmp_path)
            pygame.font.init()
            _font_cache['probe'] = pygame.font.Font(None, 12)
            _active.set(Experiment(9))
            raise RuntimeError('isolation probe')
    assert {k:v for k,v in vars(config).items() if k.isupper()} == settings
    assert random.getstate() == py
    assert np.array_equal(np.random.get_state()[1], numpy[1])
    assert np.random.get_state()[2:] == numpy[2:]
    assert Path.cwd() == cwd and 'ADSS_ISOLATION_PROBE' not in os.environ
    assert _active.get() is None and not pygame.font.get_init()
    assert not _font_cache


@pytest.mark.fast
def test_golden_bundle_integrity_and_no_automatic_rewrite(tmp_path):
    import shutil
    from validation.differential import GOLDEN, load_bundle
    target = tmp_path/'golden'
    shutil.copytree(GOLDEN,target)
    assert load_bundle(target)['baseline'] == 'approved-step11'
    path = target/'2026.json.gz'
    path.write_bytes(b'truncated')
    with pytest.raises(ValueError,match='Golden integrity mismatch'):
        load_bundle(target)
    assert path.read_bytes() == b'truncated'


@pytest.mark.fast
def test_failure_evidence_identifies_tick_group_and_exact_field(tmp_path):
    from validation.differential import failure_evidence, digest
    expected = {'drone_0':{'px':1.0},'events':[{'tick':7}]}
    actual = {'drone_0':{'px':1.000000000000001},'events':[{'tick':7}]}
    expected_hash = digest({k:digest(v) for k,v in expected.items()})
    path = failure_evidence(2026,7,expected_hash,actual,tmp_path,reference=expected)
    detail = json.loads((path/'failure.json').read_text())
    assert detail['first_divergent_tick'] == 7
    assert detail['first_divergent_group'] == 'drone_0'
    assert detail['first_difference']['path'] == '$.drone_0.px'
    assert detail['reference_matches_golden']
    assert json.loads((path/'actual.json').read_text()) == actual


@pytest.mark.standard
@pytest.mark.deterministic
def test_bounded_golden_and_repeat(tmp_path):
    import os
    import platform
    from validation.differential import run
    # Linux compatibility uses repeat equality; Windows enforces approved golden.
    golden = platform.system() == 'Windows'
    evidence = Path(os.environ.get('ADSS_FAILURE_DIR',str(tmp_path)))
    first = run(2026,60,evidence,golden=golden)
    assert run(2026,60,evidence,golden=golden) == first


@pytest.mark.fast
def test_missing_dependency_produces_actionable_import_failure():
    result = subprocess.run([sys.executable,'-S','-m','validation.sanity'],cwd=ROOT,
                            capture_output=True,text=True,encoding='utf-8')
    assert result.returncode != 0
    assert 'ModuleNotFoundError' in result.stderr and 'pygame' in result.stderr


@pytest.mark.fast
def test_tier_audit_detects_removed_contract_and_unknown_test():
    from validation.selection import audit_nodes, classify, contracts
    nodes = contracts()['baseline_nodeids']
    assert len(nodes) == 302 and len(set(nodes)) == 302
    audit_nodes(nodes)
    with pytest.raises(ValueError,match='Approved regression tests missing'):
        audit_nodes(nodes[1:])
    with pytest.raises(ValueError,match='one explicit tier marker'):
        classify('tests/new_tests.py::test_new')
    with pytest.raises(ValueError,match='Conflicting tier'):
        classify('tests/gameplay_smoke.py::test_gameplay_smoke', {'fast'})
    assert classify('tests/new_tests.py::test_new',{'standard'})['tier'] == 'standard'


@pytest.mark.fast
def test_every_approved_contract_is_classified_once():
    from validation.selection import classify, contracts, TIERS
    rules = [classify(node) for node in contracts()['baseline_nodeids']]
    assert all(rule['tier'] in TIERS for rule in rules)
    assert {r['contract'] for r in rules} >= {'motion','pathfinding','task_lifecycle',
        'reservation','communication','experiment','replay','accounting','headless','energy','performance'}
    assert classify('tests/gameplay_smoke.py::test_gameplay_smoke')['tier'] == 'heavy'
    assert classify('tests/performance_tests.py::test_cost_cache_pure_queries_do_not_mutate_it')['tier'] == 'fast'


@pytest.mark.fast
def test_presentation_gate_rejects_missing_condition_and_changed_state():
    import copy
    from validation.presentation import KEYS, verify
    modes = [('headless',60),('normal',60),('normal',30),('normal',144),
             ('reduced',60),('overlays_off',60),('noisy',60)]
    rows = [dict(mode=mode,fps=fps,**{k:'same' for k in KEYS}) for mode,fps in modes]
    verify({'results':rows})
    with pytest.raises(AssertionError,match='missing a required condition'):
        verify({'results':rows[:-1]})
    changed = copy.deepcopy(rows)
    changed[-1]['rng_hash'] = 'wrong'
    with pytest.raises(AssertionError,match='field=rng_hash'):
        verify({'results':changed})


@pytest.mark.standard
@pytest.mark.deterministic
def test_wrong_golden_tick_fails_and_preserves_reference_evidence(monkeypatch,tmp_path):
    import validation.differential as gate
    original = json.load
    def injected(stream,*args,**kwargs):
        payload = original(stream,*args,**kwargs)
        if 'tick_hashes' in payload:
            payload['tick_hashes'][0] = '0'*64
        return payload
    monkeypatch.setattr(json,'load',injected)
    # This negative test is about failure reporting, not cross-platform equality.
    monkeypatch.setattr(gate,'require_reference_environment',lambda manifest:None)
    with pytest.raises(AssertionError,match='FIRST divergence seed=2026 tick=0'):
        gate.run(2026,0,tmp_path)
    path = next(tmp_path.glob('divergence_*/failure.json'))
    detail = json.loads(path.read_text())
    assert detail['first_divergent_tick'] == 0
    assert not detail['reference_matches_golden']
    assert detail['first_difference'] is None  # Fault is expected hash, not state.
    assert (path.parent/'actual.json').exists() and (path.parent/'expected.json').exists()
