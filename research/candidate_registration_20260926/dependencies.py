"""Load unchanged transport and downstream contracts; never their old actor."""
import importlib.util
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'proposal_completion_20260926'
TRANSPORT = HERE.parent / 'alternative_conclusion_20260926'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


DEPENDENCIES = [PREVIOUS / name for name in ('records.py', 'lean_prompts.py')] + [
    TRANSPORT / name for name in ('runner.py', 'prompts.py', 'schemas.py')]


def check_dependencies(project):
    frozen = read(PREVIOUS / 'run_live_001/source_hashes.json')
    for path in DEPENDENCIES:
        key = path.relative_to(project).as_posix()
        if sha(path) != frozen[key]:
            raise ValueError('Frozen dependency changed: ' + key)


check_dependencies(HERE.parent.parent)
records = load('registration_frozen_records', PREVIOUS / 'records.py')
downstream = load('registration_frozen_downstream', PREVIOUS / 'lean_prompts.py')
transport = load('registration_frozen_transport', TRANSPORT / 'runner.py')
