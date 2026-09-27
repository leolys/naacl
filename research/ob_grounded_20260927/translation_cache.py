"""Reuse prior exact-string Chinese translations offline; no API and no new facts."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'obc140_runtime_aligned_20260924/translations'

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def main():
    output = HERE / 'ZH_EXACT_CACHE.json'
    if output.exists():
        raise FileExistsError(output)
    entries = {}
    cache = read(OLD / 'reused_exact_strings.json')
    for row in cache['items'].values():
        entries[row['en']] = {'zh': row['zh'], 'source': row['source']}
    for src in sorted((OLD / 'inbox').glob('chunk_*.json')):
        dst = OLD / 'outbox' / src.name
        if not dst.exists():
            continue
        translated = read(dst)
        for row in read(src)['items']:
            if row['id'] in translated.get('items', {}):
                entries[row['text']] = {'zh': translated['items'][row['id']], 'source': str(dst)}
    output.write_text(json.dumps({'scope': 'display only; exact string reuse; never sent to models', 'items': entries},
                                 ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'entries': len(entries), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))

if __name__ == '__main__':
    main()
