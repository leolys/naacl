"""Reuse archived clients and set-completion interfaces without editing them.

Adapted copy of research/online_defense_20260925/deps.py for
online_p01_20260928. The only change: core is loaded from THIS experiment's
reconstructed core.py (the original explanation_completion_20260925/core.py
was omitted from the export and is rebuilt test-anchored in this directory).
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
RESEARCH = HERE.parent
SNAPSHOT = PROJECT / '.aris/task_flows_20260924/snapshot'
for directory in (RESEARCH / 'competing_rules_20260923', RESEARCH / 'obc140_20260923',
                  RESEARCH / 'obc140_20260923/terra140_native_zh_20260924',
                  RESEARCH / 'obc140_runtime_aligned_20260924', SNAPSHOT):
    sys.path.insert(0, str(directory))
import panel_core as wire
import public_inputs
from budget import BudgetedPanelAPI, EstimatedBudget


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


core = module('online_completion_core', HERE / 'core.py')
completion = module('online_completion_prompts', RESEARCH / 'explanation_completion_20260925/prompts.py')
# Legacy packages use generic module names; restore this experiment's precedence.
sys.path.insert(0, str(HERE))


class Budget(EstimatedBudget):
    def transition(self, action):
        if self.value.get('blocked_reason'):
            raise wire.ServiceStop(self.value['blocked_reason'])
        if self.value['browser_operations'] >= self.config['max_browser_operations']:
            self.stop('browser_operation_budget_exhausted')
        self.value['browser_operations'] += 1
        self.value.setdefault('browser_events', []).append(action)
        self.save()
