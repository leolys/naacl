import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('contract_test_runtime',HERE/'run_contract.py')
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class ContractTests(unittest.TestCase):
    def test_only_hypothesis_stage_is_changed(self):
        for stage in ('actor','initial','questions_new','supplement','verify'):
            self.assertEqual(run.contract_system('original system',stage),'original system')

    def test_changes_only_tail_example_and_keeps_empty_branch(self):
        original=run.search.HYPOTHESIS_PREFIX+'UNCHANGED COMMON'
        modified=run.contract_system(original,'hypothesis')
        self.assertEqual(modified.replace(run.CONTRACT,run.OLD_EXAMPLE),original)
        self.assertIn('Empty is\nstill allowed',modified)
        self.assertIn('"O"',modified)
        self.assertIn('"B"',modified)
        self.assertIn('"C"',modified)
        self.assertTrue(modified.endswith('UNCHANGED COMMON'))

    def test_no_task_specific_answers_or_visual_guidance(self):
        for token in ('pub001','pub013','b002','Maine','Texas','Illinois','yellow','dark red','legend'):
            self.assertNotIn(token,run.CONTRACT)

    def test_unrecognized_prompt_is_not_silently_rewritten(self):
        with self.assertRaises(ValueError):
            run.contract_system('different interface','hypothesis')


if __name__=='__main__':
    unittest.main()
