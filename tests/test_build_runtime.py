import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('runtime_policy',Path(__file__).resolve().parents[1]/'packaging'/'runtime_policy.py')
policy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class BuildRuntimeTests(unittest.TestCase):
    def test_known_old_and_unreviewed_runtimes_are_not_releasable(self):
        for version in ((3,13,7),(3,13,17),(3,12,10),(3,14,9),(3,15,1),(3,16,0),(3,14,10,'candidate')):
            with self.subTest(version=version):
                self.assertFalse(policy.supported_runtime(version))

    def test_security_baselines_and_later_patches_are_releasable(self):
        for version in ((3,12,16),(3,13,18),(3,14,10),(3,14,11),(3,15,2,'final')):
            with self.subTest(version=version):
                self.assertTrue(policy.supported_runtime(version))
