"""Small runner reliability checks; research observations are not regression fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from experiments import run_step15 as run

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.manifest, _ = run.checked_manifest(run.ROOT/'research/manifests/pilot.json')
        self.manifest = copy.deepcopy(self.manifest)
        self.manifest['ticks'] = 60
        self.manifest['runs'] = [dict(seed=99001, condition='reference')]
        self.item = self.manifest['runs'][0]

    def test_observer_repeat_resume_and_corruption(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT/'research') as tmp:
            root = Path(tmp)
            a,_ = run.run_one(self.manifest,run.digest(self.manifest),self.item,root/'a')
            b,_ = run.run_one(self.manifest,run.digest(self.manifest),self.item,root/'b',measure_csv=False)
            for field in ('metrics','accounting','observations','series','final_group_hashes','world_hash','energy_diagnostics'):
                self.assertEqual(a[field],b[field],field)
            p=root/'a/reference_seed99001.json';before=p.read_bytes()
            c,resumed=run.run_one(self.manifest,run.digest(self.manifest),self.item,root/'a')
            self.assertTrue(resumed);self.assertEqual(before,p.read_bytes());self.assertEqual(a,c)
            p.write_bytes(before+b' ')
            with self.assertRaisesRegex(ValueError,'checksum'):
                run.run_one(self.manifest,run.digest(self.manifest),self.item,root/'a')

    def test_failure_is_preserved_and_reentry_blocked(self):
        with tempfile.TemporaryDirectory(dir=run.ROOT/'research') as tmp:
            root=Path(tmp)
            with patch.object(run,'make_simulation',side_effect=RuntimeError('injected failure')):
                with self.assertRaises(RuntimeError):
                    run.run_one(self.manifest,run.digest(self.manifest),self.item,root)
            failures=list(root.rglob('failure_*.json'))
            self.assertEqual(len(failures),1)
            self.assertEqual(json.loads(failures[0].read_text())['status'],'failed')
            with self.assertRaisesRegex(ValueError,'Incomplete prior attempt'):
                run.run_one(self.manifest,run.digest(self.manifest),self.item,root)

    def test_config_changes_only_intended_factor(self):
        c=self.manifest['conditions'];base=c['reference']['settings']
        expected={'range_90':{'DRONE_COMM_RANGE'},'range_360':{'DRONE_COMM_RANGE'},
                  'swarm_4':{'NUM_DRONES'},'swarm_16':{'NUM_DRONES'}}
        for condition,names in expected.items():
            self.assertEqual({k for k,v in base.items() if c[condition]['settings'][k]!=v},names)

if __name__=='__main__':
    unittest.main()
