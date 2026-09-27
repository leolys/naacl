"""Freeze public-only inputs; keep source identities and families offline."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / 'obc140_runtime_aligned_20260924'

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

PUBLIC_KEYS = ('page_title', 'user_goal', 'chart_reference', 'primary_field_label',
               'option_labels', 'companion_fields', 'completion_label', 'policy_tables', 'page_instructions')

def full_project(public, normalized):
    public = {k: copy.deepcopy(public[k]) for k in PUBLIC_KEYS if k in public}
    rules = {r['id']: r for r in normalized['rules']}
    records = []
    for i, c in enumerate(normalized['chains']):
        b = rules[c['rule_id']]
        records.append({'id': 'r%d' % (i+1), 'O': copy.deepcopy(c['observations']),
                        'B': {k: copy.deepcopy(b[k]) for k in ('text', 'conditions') if k in b}})
    return {'goal': public['user_goal'], 'public_task': public,
            'options': public['option_labels'], 'records': records}

def main():
    if (HERE / 'data').exists() or (HERE / 'manifest.json').exists():
        raise FileExistsError('Never overwrite frozen input bundle')
    catalog = read(OLD / 'prepared/catalog.json')
    families = read(ROOT / '.aris/dataset_inventory_20260918/AUDIT_COUNTS.json')['core_families']
    family_by_slug = {s: f['name'] for f in families for s in f['slugs']}
    dev_families = {family_by_slug[s] for s in ('b002', 'pub001', 'pub013')}
    eligible = [f for f in families if f['name'] not in dev_families]
    # Deterministic whole-family separation for this round, before any outputs.
    eligible.sort(key=lambda f: hashlib.sha256(('ob-grounded-confirm-v1|' + f['name']).encode()).hexdigest())
    confirm = [sorted(f['slugs'])[0] for f in eligible[:12]]
    units = {}
    for variant in ('registration', 'coverage'):
        for case in ('pub001_misleading', 'pub001_normal', 'b002', 'pub013'):
            key = 'dev_' + variant + '_' + case
            source = HERE.parent / 'ob_only_verification_20260926/run_live_001' / variant / case
            dest = HERE / 'data' / key
            projected = read(source / 'projected.json')
            dump(dest / 'input.json', projected)
            shutil.copyfile(source / 'source_chart.png', dest / 'chart.png')
            units[key] = {'panel': 'dev', 'slug': case, 'variant': variant,
                          'candidate_source': 'frozen_Qwen_conditional_expansion',
                          'input_sha256': sha(dest / 'input.json'), 'image_sha256': sha(dest / 'chart.png'),
                          'image': 'chart.png', 'records': len(projected['records']),
                          'source': str(source.relative_to(ROOT)),
                          'source_hashes': {n: sha(source / n) for n in ('projected.json', 'source_chart.png', 'source_candidate_set.json')}}
    missing = []
    for task in catalog['tasks']:
        slug = task['task_slug']
        key = 'full_' + slug
        public_path = OLD / 'prepared' / task['public_file']
        image_path = OLD / 'prepared' / task['chart_file']
        generated = OLD / 'run/tasks' / slug / 'generation/round_001/validated.json'
        normalized = read(generated)['normalized'] if generated.exists() else {'rules': [], 'chains': []}
        if not normalized['chains']:
            missing.append(slug)
        projected = full_project(read(public_path), normalized)
        dest = HERE / 'data' / key
        dump(dest / 'input.json', projected)
        shutil.copyfile(image_path, dest / 'chart.jpeg')
        units[key] = {'panel': 'full', 'slug': slug, 'domain': task['domain'],
                      'family': family_by_slug.get(slug, 'unmapped'), 'confirm': slug in confirm,
                      'candidate_source': 'Terra_runtime_aligned' if normalized['chains'] else 'missing_old_input_supply_once',
                      'records': len(projected['records']), 'image': 'chart.jpeg',
                      'input_sha256': sha(dest / 'input.json'), 'image_sha256': sha(dest / 'chart.jpeg'),
                      'source': str(generated.relative_to(ROOT)),
                      'source_hashes': {str(p.relative_to(ROOT)): sha(p) for p in (public_path, image_path, generated) if p.exists()}}
        # Original action and C only offline; never included in data/input.json.
        proposal = OLD / 'run/tasks' / slug / 'proposal/round_001/parsed.json'
        dump(HERE / 'offline_source' / (slug + '.json'), {'chains': normalized['chains'],
            'old_proposal': read(proposal) if proposal.exists() else None,
            'note': 'cross-model historical reference, not same-Qwen baseline and not gold'})
    manifest = {'unit_count': len(units), 'full_task_count': 140,
                'condition': 'official140_single_image_not_two_arms', 'units': units,
                'confirm_slugs': confirm, 'dev_families': sorted(dev_families),
                'missing_old_candidates': missing,
                'confirm_selection': 'one lexicographic slug per family; seeded SHA256 family order; exclude all dev families; not globally unseen tasks',
                'status': 'frozen_before_first_live_call'}
    dump(HERE / 'manifest.json', manifest)
    with tarfile.open(HERE / 'public_bundle.tgz', 'x:gz') as tar:
        tar.add(HERE / 'data', arcname='data')
        tar.add(HERE / 'manifest.json', arcname='manifest.json')
    print(json.dumps({'units': len(units), 'full': 140, 'confirm': confirm, 'missing': missing,
                      'bytes': (HERE / 'public_bundle.tgz').stat().st_size, 'sha256': sha(HERE / 'public_bundle.tgz')}))

if __name__ == '__main__':
    main()
