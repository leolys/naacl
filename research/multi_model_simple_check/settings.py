from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
CONDA = Path('/mnt/data/code_generation/liyisheng/8H100conda')
WEIGHTS = Path('/mnt/data/datasets/open_source_models')
RUN_ROOT = PACKAGE / 'runs' / 'extension_20260916_v1'
SOURCE_MANIFEST = REPO / 'research/prospective_simple_check_pilot/preparation_20260907_v1/TASK_MANIFEST.json'
GPU = '7'
PORT = 18767
NAMES = ('qwen25_7b', 'qwen3_32b', 'internvl3_8b')
CONFIGS = {
    'qwen25_7b': dict(family='qwen25', display='Qwen2.5-VL-7B-Instruct', weights=str(WEIGHTS / 'Qwen2.5-VL-7B-Instruct'), env='qwen3_vl'),
    'qwen3_32b': dict(family='qwen3', display='Qwen3-VL-32B-Instruct', weights=str(WEIGHTS / 'Qwen3-vl-32-instruct'), env='qwen3_vl'),
    'internvl3_8b': dict(family='internvl3', display='InternVL3-8B', weights=str(WEIGHTS / 'InternVL3-8B'), env='internvl'),
}
BROWSER = REPO / 'new_paper_projects/evidence_revision_web_agent/gui_benchmark_native_recovery_v1/.runtime/workarena-0.5.3/browsers/chromium-1117/chrome-linux/chrome'
BROWSER_RUNTIME = PACKAGE / 'runtime' / 'browser_libs'
BROWSER_LIBS = BROWSER_RUNTIME / 'usr/lib/x86_64-linux-gnu'
EVAL_PYTHON = CONDA / 'envs/misleading_webagent_eval/bin/python'
TASKS = ('b010', 'b046', 'health001', 'env035', 'health005', 'pub013', 'b014', 'env005')


def common_env():
    import os
    return {**os.environ, 'CUDA_VISIBLE_DEVICES': GPU, 'OMP_NUM_THREADS': '4',
            'MKL_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'TOKENIZERS_PARALLELISM': 'false', 'WANDB_DISABLED': 'true',
            'PYTHONDONTWRITEBYTECODE': '1',
            'LD_LIBRARY_PATH': str(BROWSER_LIBS) + ':' + os.environ.get('LD_LIBRARY_PATH', '')}
