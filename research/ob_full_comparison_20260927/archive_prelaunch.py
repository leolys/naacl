"""Preserve pre-inference infrastructure revision; never overwrite run evidence."""
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
NAMES = ('dispatch.py', 'watchdog.py', 'RUNTIME_SEAL.json', 'ONLINE_BUNDLE.zip')


def main():
    assert ROOT.name == 'ob_full_comparison_20260927'
    target = ROOT / 'prelaunch_v1'
    target.mkdir(exist_ok=False)
    for name in NAMES:
        source = ROOT / name
        source.resolve().relative_to(ROOT)
        destination = target / name
        if name.endswith('.py') and os.name == 'nt':
            with source.open('rb') as src, destination.open('xb') as out:
                shutil.copyfileobj(src, out)
        else:
            source.rename(destination)
    # Remote extraction must not overwrite old code; remove from root only via a
    # recoverable move after making the byte-identical local archive above.
    print('Prelaunch v1 artifacts preserved; no model results exist in this revision.')


if __name__ == '__main__':
    main()
