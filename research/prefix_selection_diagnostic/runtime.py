"""Read-only reuse of the reference run's actual implementation, not today's tree."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.path_compat import resolve_path


def load_runtime(source_run: Path):
    snapshot = resolve_path(source_run).resolve() / "evaluator/runtime_source_snapshot"
    package = snapshot / "research/decision_evidence_audit"
    name = "prefix_diagnostic_legacy"
    if name in sys.modules:
        if Path(sys.modules[name].__file__).parent != package:
            raise RuntimeError("cannot mix reference runtime versions in one process")
    else:
        spec = importlib.util.spec_from_file_location(
            name, package / "__init__.py", submodule_search_locations=[str(package)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    # The legacy model boundary imports the already archived client by this name.
    sys.path.insert(0, str(snapshot))
    return SimpleNamespace(snapshot=snapshot, **{
        key: importlib.import_module(f"{name}.{key}")
        for key in ("core", "runner", "policies", "models", "safe_shell")})
