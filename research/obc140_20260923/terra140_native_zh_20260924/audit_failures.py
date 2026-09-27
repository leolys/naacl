"""Offline deterministic explanations for retained structural failures."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'terra_citation_check_20260924'))
import panel_core as core
import citation_adapter


def audit():
    findings = []
    config = core.read(HERE / 'config.json')
    for path in sorted((HERE / 'run/tasks').glob('*/record.json')):
        record = core.read(path)
        for phase in ('proposal','generation','verification'):
            status = record['status'][phase]
            if status not in ('invalid','failed','blocked'):
                continue
            row = {'task': record['task_slug'], 'phase': phase, 'status': status,
                   'stage': record['stages'].get(phase), 'new_model_requests': 0}
            stage_folder = row['stage'].get('folder') if row['stage'] else None
            attempts = sorted((path.parent / stage_folder).glob('attempt_*.json')) if stage_folder else []
            row['attempts'] = [{k: core.read(p).get(k) for k in ('attempt','http_status',
                'finish_reason','error_category','exception_type','retryable')} for p in attempts]
            if row['attempts'] and row['attempts'][-1].get('finish_reason') == 'length':
                row['reason'] = 'output_length_limit'
            elif (row['attempts'] and row['attempts'][-1].get('finish_reason') == 'stop'
                  and row['attempts'][-1].get('exception_type') == 'JSONDecodeError'):
                row['reason'] = 'invalid_json_on_normal_stop'
            if status == 'invalid' and phase + '_invalid_raw' in record:
                try:
                    citation_adapter.validate_stage(phase, record[phase + '_invalid_raw'], record, config)
                    row['deterministic_replay'] = 'unexpected_acceptance_requires_audit'
                except Exception as error:
                    row.update(deterministic_replay='rejected', exception_type=type(error).__name__,
                               reason=str(error))
            findings.append(row)
    core.dump(HERE / 'failure_audit.json', findings)
    print({'retained_failed_stages': len(findings), 'new_requests': 0})


if __name__ == '__main__':
    audit()
