"""No-clobber extraction, allow already-uploaded byte-identical files only."""
import hashlib
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    with zipfile.ZipFile(HERE / 'ONLINE_BUNDLE.zip') as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError('duplicate archive member')
        for name in names:
            target = (HERE / name).resolve()
            target.relative_to(HERE)
            if 'offline' in Path(name).parts or 'runs' in Path(name).parts:
                raise RuntimeError('nonpublic archive member')
            if target.exists() and target.read_bytes() != archive.read(name):
                raise RuntimeError('would overwrite different existing artifact: ' + name)
        written = 0
        for name in names:
            target = HERE / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as out:
                out.write(archive.read(name))
            written += 1
    print('New files extracted without clobber:', written)


if __name__ == '__main__':
    main()
