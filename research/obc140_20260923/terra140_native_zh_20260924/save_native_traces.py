"""Windows UTF-8 fallback for unavailable shell trace dependencies/encoding."""
from datetime import datetime, timezone
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]


def save(purpose, prompt, response, number):
    folder = WORKSPACE / '.aris/traces/experiment-bridge/2026-09-24_terra140_utf8'
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    base = {'executor': 'codex', 'executor_model': 'gpt-5',
            'executor_model_source': 'caller-declared', 'executor_family': 'openai',
            'reviewer_model_source': 'requested', 'reviewer_family': 'openai',
            'family_relation': 'same', 'independence_verified': False,
            'review_independence': 'same-family', 'acceptance_status': 'provisional'}
    def dump(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not (folder / 'run.meta.json').exists():
        dump(folder / 'run.meta.json', {**base, 'skill': 'experiment-bridge',
             'started_at': timestamp, 'reviewer_backend': 'codex', 'project_dir': str(WORKSPACE),
             'fallback_reason': 'Resolved .aris/tools/save_trace.sh: first nested bash resolved WSL access denial; nonlogin shell missed tr/cat; login helper later failed on Windows GBK/nonASCII environment. Native UTF-8 file reader preserves original request/response exactly.',
             'failed_shell_artifacts_retained': '.aris/traces/experiment-bridge/2026-09-24_run01'})
    prefix = '%03d-%s' % (number, purpose)
    if (folder / (prefix + '.response.md')).exists():
        raise FileExistsError('trace already exists; never overwrite')
    dump(folder / (prefix + '.request.json'), {**base, 'call_number': number,
        'purpose': purpose, 'timestamp': timestamp, 'tool': 'collaboration.' + ('spawn_agent' if number == 1 else 'followup_task'),
        'backend': 'codex', 'model': 'gpt-5.6-sol', 'config': {'model_reasoning_effort': 'xhigh'},
        'prompt': (HERE / prompt).read_text(encoding='utf-8')})
    responses = response if isinstance(response, (list, tuple)) else [response]
    text = '\n\n'.join((HERE / filename).read_text(encoding='utf-8') for filename in responses)
    (folder / (prefix + '.response.md')).write_text(text, encoding='utf-8')
    dump(folder / (prefix + '.meta.json'), {**base, 'call_number': number, 'purpose': purpose,
        'timestamp': timestamp, 'thread_id': '/root/terra140_code_gate', 'model': 'gpt-5.6-sol',
        'model_family': 'openai', 'status': 'ok', 'effort': 'xhigh',
        'requested_reviewer_model': 'gpt-5.6-sol', 'reported_reviewer_model': None,
        'note': 'Review completed before trace serialization; not a second review or API call.'})
    events = WORKSPACE / '.aris/meta/events.jsonl'
    events.parent.mkdir(parents=True, exist_ok=True)
    with events.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({**base, 'event': 'review_trace', 'skill': 'experiment-bridge',
            'purpose': purpose, 'thread_id': '/root/terra140_code_gate', 'trace_path': str(folder),
            'backend': 'codex', 'status': 'ok'}, ensure_ascii=False) + '\n')
    print(str(folder / (prefix + '.response.md')))


if __name__ == '__main__':
    save('code-gate', 'code_gate_request.txt', 'PREDEPLOY_REVIEW.md', 1)
    save('b002-semantic', 'semantic_b002_request.txt', 'semantic_review_b002.md', 2)
