"""Reuse the frozen local-only transport; no older prompt is sent online."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
SOURCE = HERE.parent / 'conditional_expansion_20260926/run_live_001'
TRANSPORT = HERE.parent / 'alternative_conclusion_20260926'
DEPENDENCIES = [TRANSPORT / n for n in ('runner.py', 'prompts.py', 'schemas.py')]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_dependencies():
    frozen = read(SOURCE / 'source_hashes.json')
    for p in DEPENDENCIES:
        if sha(p) != frozen[p.relative_to(PROJECT).as_posix()]:
            raise ValueError('Frozen transport changed')


check_dependencies()
spec = importlib.util.spec_from_file_location('ob_only_transport', TRANSPORT / 'runner.py')
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
