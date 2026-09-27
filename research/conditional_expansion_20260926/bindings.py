"""Read-only frozen dependencies for transport and unchanged verifier."""
import importlib.util
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
PREVIOUS = HERE.parent / 'candidate_registration_20260926'
SOURCE_RUN = PREVIOUS / 'run_live_001'
OLD = HERE.parent / 'proposal_completion_20260926'
TRANSPORT = HERE.parent / 'alternative_conclusion_20260926'
DEPENDENCIES = [OLD / name for name in ('records.py', 'lean_prompts.py')] + [
    TRANSPORT / name for name in ('runner.py', 'prompts.py', 'schemas.py')]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_dependencies():
    frozen = read(SOURCE_RUN / 'source_hashes.json')
    for path in DEPENDENCIES:
        if sha(path) != frozen[path.relative_to(PROJECT).as_posix()]:
            raise ValueError('Frozen dependency changed: ' + str(path))


check_dependencies()
records = load('conditional_frozen_records', OLD / 'records.py')
downstream = load('conditional_frozen_verifier', OLD / 'lean_prompts.py')
transport = load('conditional_frozen_transport', TRANSPORT / 'runner.py')
