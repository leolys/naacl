"""Local offline freeze; never call a model or send labels to its runner."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from evaluate import HERE, digest, evaluate, read, save_new


def inspect_audit(version, audit_path, result):
    audit = read(audit_path)
    keys = set(result['comparisons']['plain']['rows'])
    if (audit.get('version') != version or audit.get('complete') is not True
            or set(audit.get('units', {})) != keys):
        raise ValueError('Need completed audit of all 24 fixed development units')
    if audit.get('bound_result_files') != result['source_hashes']:
        raise ValueError('Audit not bound to these exact results')
    improvements = {key for comp in result['comparisons'].values()
                    for key, row in comp['rows'].items() if row['net_target'] > 0}
    issues = []
    if audit.get('task_specific_prompt_rules') is not False:
        issues.append('Prompt generality not verified')
    for key, record in audit['units'].items():
        if not isinstance(record.get('note'), str) or len(record['note'].strip()) < 20:
            raise ValueError('Substantive audit note required for ' + key)
        if not record.get('evidence_files'):
            raise ValueError('Evidence references required for ' + key)
        if key in improvements and record.get('improved_choice_visible_support') is not True:
            issues.append('New target agreement not visibly justified: ' + key)
        for relative, expected in record['evidence_files'].items():
            resolved = (HERE / relative).resolve()
            if HERE.resolve() not in resolved.parents or digest(resolved) != expected:
                raise ValueError('Audit evidence missing or changed')
    return issues


def make_freeze(version, audit_path):
    if (HERE / 'FREEZE.json').exists():
        raise ValueError('Already frozen; do not select another version')
    result = evaluate(version, 'dev')
    if not result['dev_numeric_gate']:
        raise ValueError('Predeclared numeric development gate not met')
    issues = inspect_audit(version, audit_path, result)
    if issues:
        raise ValueError('; '.join(issues))
    # A previous passing version must not be bypassed by looking for a higher score.
    earlier_dispositions = {}
    for number in range(4, int(version[1:])):
        earlier = HERE / 'runs' / ('v%d_dev' % number) / 'summary.json'
        if earlier.exists() and read(earlier)['status'] == 'finished':
            earlier_result = evaluate('v%d' % number, 'dev')
            record = {'result_files': earlier_result['source_hashes'],
                      'numeric_gate': earlier_result['dev_numeric_gate']}
            if earlier_result['dev_numeric_gate']:
                earlier_audit = HERE / 'audit' / ('v%d_dev.json' % number)
                earlier_issues = inspect_audit('v%d' % number, earlier_audit, earlier_result)
                if not earlier_issues:
                    raise ValueError('Earlier full pass must be frozen; do not cherry-pick')
                record.update(audit_path=str(earlier_audit.relative_to(HERE)),
                              audit_sha256=digest(earlier_audit), semantic_failure=earlier_issues)
            earlier_dispositions['v%d' % number] = record
    source = read(HERE / 'runs' / (version + '_dev') / 'source_hashes.json')
    if any(digest(HERE / name) != expected for name, expected in source.items()):
        raise ValueError('Source changed after development')
    return {'created': datetime.now(timezone.utc).isoformat(), 'version': version,
            'source_hashes': source, 'dev_numeric_gate': True,
            'dev_conditions': result['dev_conditions'],
            'comparison_metrics': {key: {metric: value[metric] for metric in
                ('net_target', 'positive_net_families', 'common_parsed_including_null')}
                for key, value in result['comparisons'].items()},
            'bound_result_files': result['source_hashes'],
            'qualitative_audit_path': str(Path(audit_path).resolve().relative_to(HERE)),
            'qualitative_audit_sha256': digest(audit_path),
            'earlier_version_dispositions': earlier_dispositions,
            'freeze_tool_sha256': digest(HERE / 'freeze.py'),
            'evaluator_sha256': digest(HERE / 'evaluate.py'),
            'no_new_application_results_used': True,
            'business_submissions': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True, choices=['v4', 'v5', 'v6', 'v7'])
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    save_new(HERE / 'FREEZE.json', make_freeze(args.version, args.audit))
    print('Frozen ' + args.version + '; no further development on this panel.')
