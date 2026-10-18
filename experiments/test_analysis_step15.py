"""Hand-calculated analysis checks, separate from simulation research replicates."""
import unittest
from pathlib import Path
import numpy as np
from research.analysis.analyze import bootstrap_difference, ROOT


class AnalysisTests(unittest.TestCase):
    def test_relative_cli_input_provenance(self):
        from research.analysis.analyze import repository_path
        relative = Path('research/manifests/main.json')
        self.assertEqual(repository_path(relative), relative.as_posix())
        self.assertEqual(repository_path(ROOT / relative), relative.as_posix())

    def test_pairing_preserves_constant_effect(self):
        indices = np.random.Generator(np.random.PCG64(1502026)).integers(0, 4, (20000, 4))
        result = bootstrap_difference([3, 12, 102, -8], [1, 10, 100, -10], indices)
        self.assertEqual(result['mean'], 2)
        self.assertEqual(result['ci95'], [2, 2])
        self.assertEqual(result['ci9875'], [2, 2])
        self.assertEqual(result['differences'], [2, 2, 2, 2])

    def test_zero_effect_and_deterministic_resampling(self):
        def calculate():
            indices = np.random.Generator(np.random.PCG64(1502026)).integers(0, 4, (20000, 4))
            return bootstrap_difference([0, 2, 7, 4], [0, 2, 7, 4], indices)
        a, b = calculate(), calculate()
        self.assertEqual(a, b)
        self.assertEqual(a['ci9875'], [0, 0])
        self.assertEqual(a['sd'], 0)


if __name__ == '__main__':
    unittest.main()
