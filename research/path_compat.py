"""Resolve pre-migration filesystem references without rewriting experiment evidence.

Only filesystem consumers call this function. JSON records, prompts, scores,
checkpoint identities, and archived source files remain unchanged.
"""
from pathlib import Path

PROJECT_ROOT = Path("/mnt/data/lys/CognitiveHijacking_CognitiveDenial")
OLD_STORAGE = "/hipilot/sharestorage"
OLD_PROJECT = OLD_STORAGE + "/lys/CognitiveHijacking_CognitiveDenial"
NEW_STORAGE = Path("/mnt/data")


def resolve_path(value, *, base=None):
    """Map exact legacy prefixes; leave unrelated and relative paths alone.

    Does not require existence, fabricate files, or fall back to another asset.
    A supplied base is used only for relative references.
    """
    path = Path(value)
    text = path.as_posix()
    for old, new in ((OLD_PROJECT, PROJECT_ROOT), (OLD_STORAGE, NEW_STORAGE)):
        if text == old:
            return new
        if text.startswith(old + "/"):
            return new / text[len(old) + 1:]
    if base is not None and not path.is_absolute():
        return resolve_path(base) / path
    return path
