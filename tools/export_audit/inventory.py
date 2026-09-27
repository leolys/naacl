"""Read-only allowlist inventory for the user-approved core handoff.

Only metadata is emitted. No credentials are opened, no symlinks are followed,
and source files are never changed. The same script runs locally and via SSH.
"""
import argparse
import json
import os
from pathlib import Path
import re

LOCAL_RESEARCH = [
    'competing_rules_20260923', 'obc140_20260923',
    'obc140_runtime_aligned_20260924', 'counterquestion_b001_20260925',
    'counterquestion_general_20260925', 'explanation_completion_20260925',
    'explanation_completion_v2_20260926', 'explanation_completion_v3_20260926',
    'alternative_conclusion_20260926', 'conclusion_search_20260926',
    'candidate_registration_20260926', 'proposal_completion_20260926',
    'conditional_expansion_20260926', 'ob_only_verification_20260926',
    'ob_grounded_20260927', 'ob_refinement_20260927',
    'ob_full_comparison_20260927', 'online_defense_20260925',
]
REMOTE_ROOTS = [
    'web_agent_benchmark/benchmark_v2_open/assets/official140',
    'web_agent_benchmark/benchmark_v2_open/assets/clean140',
    'web_agent_benchmark/benchmark_v2_open/splits/official140',
    'web_agent_benchmark/benchmark_v2_open/splits/clean140',
    'web_agent_benchmark/evaluation',
    'web_agent_benchmark/business_shell',
    'web_agent_benchmark/environment_energy_shell',
    'web_agent_benchmark/health_shell',
    'web_agent_benchmark/public_benchmark',
    'web_agent_benchmark/public_shell',
    'web_agent_benchmark/public_affairs_shell',
    'web_agent_benchmark/benchmark_v2',
    'web_agent_benchmark/official_benchmark_v1',
    'web_agent_benchmark/clean_benchmark_v1',
    'web_agent_benchmark/selection',
    'web_agent_benchmark/task_generation',
    'web_agent_benchmark/tasks',
    'web_agent_benchmark/environment_energy_tasks',
    'web_agent_benchmark/health_tasks',
    'web_agent_benchmark/public_affairs_tasks',
    'adversarial_pipeline', 'tests',
    'research/decision_evidence_audit',
    'research/prospective_simple_check_pilot',
    'research/prefix_selection_diagnostic',
    'research/multi_model_simple_check',
    'research/postpilot_attribution_diagnostic',
]
REMOTE_FILES = [
    'research/path_compat.py', 'research/test_path_compat.py',
    'web_agent_benchmark/benchmark_v2_open/LICENSE.md',
    'web_agent_benchmark/benchmark_v2_open/ATTRIBUTION.md',
    'web_agent_benchmark/review_annotations.json',
    'web_agent_benchmark/selected_cases_supplemental_fixed_misleaders/review_annotations.json',
    'web_agent_benchmark/selected_cases_final_suitable/review_annotations.json',
    'web_agent_benchmark/selected_cases_workflow_ready/review_annotations.json',
    'web_agent_benchmark/action_workflow_field_requirements.md',
    'docs/web_agent_benchmark_agent_prompt.md',
    'docs/intranet_model_api_usage.md',
    'docs/multimodal_litellm_api.md',
    'Codex_MisVis_Direction1_Research_Brief.md',
    'Codex_Prospective_Simple_Check_API_Pilot.md',
    'Codex_Stage2_5_Review_and_Live_Check.md',
    'benchmark_construction_chapter.md',
]
BLOCK_DIRS = {
    '.git', '.agents', '.aris', '.codex', '.venv', 'venv', 'node_modules',
    '__pycache__', '.pytest_cache', 'cache', 'uv_cache', 'browsers',
    'browser_libs', 'browser_debs', 'debs', 'cuda_compat', 'backups',
    'resources', 'cleanup', 'dispatch', 'service_logs', 'service_snapshot',
    'real_world40', 'real_world40_v2_final', 'progress_001',
    'profiled_runs',
}
BLOCK_NAMES = {
    'apikey.txt', 'password.txt', 'auth.json', 'hosts.yml', 'credentials.json',
    '.env', 'id_rsa', 'id_ed25519', 'id_lys', 'resource_manager.py',
    'cleanup.py', 'watchdog.py', 'dispatch.py', 'test_full.py',
    'premise_controller.py', 'final_resource_check.py',
    'FINAL_RESOURCE_CHECK.json', 'AUTOMATION_CLOSE_RECEIPT.json',
    'storage_state.json', 'cookies.json', 'cookie.txt', 'cookies.txt',
}
BLOCK_SUFFIXES = {'.zip', '.tar', '.gz', '.7z', '.exe', '.dll', '.so',
                  '.safetensors', '.pt', '.pth', '.bin', '.pyc', '.key',
                  '.pem', '.aux', '.bbl', '.blg', '.fdb_latexmk', '.fls',
                  '.out', '.lock', '.tmp'}
TEXT_SUFFIXES = {'.py', '.md', '.json', '.jsonl', '.yaml', '.yml', '.toml',
                 '.txt', '.html', '.js', '.css', '.csv', '.tsv', '.tex',
                 '.bib', '.sty', '.bst', '.sh', '.ps1', '.ini', '.cfg', '.xml', '.log'}
ALLOWED_SUFFIXES = TEXT_SUFFIXES | {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.pdf'}


def excluded(parts, is_dir=False):
    for part in parts:
        low = part.lower()
        if part in BLOCK_DIRS or part in BLOCK_NAMES:
            return True
        if low.startswith(('.env', 'core.', 'real_world', 'travel_', 'guard_')):
            return True
        if any(x in low for x in ('gpu_guard', 'gpu_occup', 'rebuttal', 'openreview')):
            return True
        if low.startswith('heartbeat_') or low in ('gpu_preflight.json', 'resource_preflight.json'):
            return True
        if 'backup' in low:
            return True
        if re.match(r'^(?:full_|confirm_|v\d+_)?partial\d+$', low):
            return True
        if low.startswith('review_') and low not in {
            'review_final_002', 'review_full_002', 'review_002', 'review_001',
            'review_v3', 'review_confirm_007', 'review_v1_dev_003',
            'review_v2_dev_001', 'review_v3_dev_001'}:
            # Repeated rendered intermediate UIs are not independent evidence.
            if '.' not in low:
                return True
    if not is_dir:
        name = parts[-1]
        suffix = Path(name).suffix.lower()
        if suffix in BLOCK_SUFFIXES:
            return True
        if suffix not in ALLOWED_SUFFIXES and name not in ('LICENSE', 'NOTICE', 'Dockerfile', 'Makefile', '.gitignore'):
            return True
    return False


def inventory(root, side):
    roots = ['research/' + n for n in LOCAL_RESEARCH] if side == 'local' else REMOTE_ROOTS
    files = []
    skipped = []
    missing = []
    candidates = set()
    for name in roots:
        start = root / name
        if not start.exists():
            missing.append(name)
            continue
        for current, dirs, names in os.walk(start, followlinks=False):
            directory = Path(current)
            dirs[:] = [d for d in sorted(dirs)
                       if not (directory / d).is_symlink()
                       and not excluded((directory / d).relative_to(root).parts, True)]
            for filename in names:
                candidates.add(directory / filename)
    if side == 'remote':
        candidates.update(root / p for p in REMOTE_FILES)
        paper = root / 'paper_0707'
        if paper.exists():
            for current, dirs, names in os.walk(paper, followlinks=False):
                dirs[:] = [d for d in dirs if d in ('figures', 'prompts', 'scripts')]
                for n in names:
                    if Path(n).suffix.lower() in {'.tex', '.bib', '.sty', '.bst', '.png', '.pdf', '.py', '.txt'} and 'old' not in n.lower() and '_v1' not in n:
                        candidates.add(Path(current) / n)
    for p in sorted(candidates):
        rel = p.relative_to(root).as_posix()
        if not p.exists():
            missing.append(rel)
        elif p.is_symlink():
            skipped.append({'path': rel, 'reason': 'symlink_requires_explicit_dependency_resolution'})
        elif excluded(p.relative_to(root).parts):
            skipped.append({'path': rel, 'reason': 'scope_or_nonportable_exclusion'})
        else:
            s = p.stat()
            files.append({'path': rel, 'bytes': s.st_size})
    return {'side': side, 'root': str(root), 'files': files,
            'skipped_files': skipped, 'missing': missing,
            'file_count': len(files), 'bytes': sum(f['bytes'] for f in files)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--side', choices=('local', 'remote'), required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = inventory(a.root, a.side)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with a.output.open('x', encoding='utf-8') as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
        print(json.dumps({k: result[k] for k in ('side', 'file_count', 'bytes', 'missing')}))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
