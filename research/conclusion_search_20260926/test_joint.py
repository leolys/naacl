import copy
import re
import unittest
import run_joint as joint


class JointTests(unittest.TestCase):
    def test_no_old_arguments_or_current_choice(self):
        context = {'goal': 'original goal', 'options': ['A', 'B'], 'history': ['A'], 'pending_proposal': 'submit',
                   'state': {'text': 'public rule', 'selected_text': 'A', 'url': 'local'}}
        initial = {'chains': [{'O': ['old'], 'B': 'old', 'C': {'option_label': 'A', 'claim': 'old reason'}}]*2}
        before = copy.deepcopy(context)
        out = joint.joint_context(context, initial)
        self.assertEqual(out, {'goal':'original goal', 'options':['A','B'], 'state':{'text':'public rule'}, 'existing_conclusions':['A']})
        self.assertEqual(context, before)

    def test_no_task_specific_prompt(self):
        for token in ('Maine', 'Texas', 'Firefox', 'Illinois', 'yellow', 'red', 'legend', 'highest risk'):
            self.assertIsNone(re.search(r'\b' + re.escape(token) + r'\b', joint.JOINT))
        self.assertIn('empty list', joint.JOINT)
        self.assertIn('not selection of a winning', joint.JOINT)


if __name__ == '__main__':
    unittest.main()
