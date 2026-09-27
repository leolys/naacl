"""New, bounded local-service diagnostic. Prior runs are read-only inputs."""
from __future__ import annotations

import argparse
import copy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import search_strategies as strategies

BASE_DIR = HERE.parent / 'alternative_conclusion_20260926'
spec = importlib.util.spec_from_file_location('frozen_base_runtime', BASE_DIR / 'runner.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

FRESH_QUESTION_PREFIX = '''Explore concrete task conclusions this complete image might support,
without being supplied earlier candidate records. This is a search for plausible
readings, not a verdict on a previous answer and not a request to force disagreement.
Treat the current selection as a previous action, not evidence for a conclusion.
Ask up to two search questions. Each names a concrete possible task conclusion
and a locatable visual cue motivating examination of that reading. Ask whether
it can form a complete conditional O-B-C candidate. Different conclusions need
not be opposites. Do not choose a single winner in advance or require a reading
to be verified before it can be explored. Do not invent marks or task policies.
Zero questions is allowed when no image-grounded candidate can be articulated;
explain what was inspected. Return {"questions":[{"id":"q1","question":"..."}],
"summary":"coverage and limits"}.
'''

HYPOTHESIS_PREFIX = '''The supplied public option is a SEARCH HYPOTHESIS, not an answer
to defend or a command to act. Every available option is explored with this same
instruction, including the current one. Re-observe the complete image and ask:
could a reading motivated by specific visible cues yield this task conclusion?
If so, form at most ONE complete O-B-C candidate under that reading. O must state
localized literal visible facts, B the conditional decoding/comparison bridge,
and C the concrete task conclusion linked to the hypothesis option. A conditional
reading can be explored before its applicability is verified. Do not assume the
hypothesis is correct as a premise, invent values, redefine the user's objective,
or fabricate O to make the conclusion hold. This is not criticism of a prior chain.
If no such complete candidate can be articulated, return chains=[] and describe
what was inspected in notes. An empty result is fully acceptable; do not fill a quota.
Do not compare to an earlier candidate set or choose a final winner. Use a chain
ID such as h1. Return {"chains":[],"notes":"coverage and limits"}.
'''


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def normalized_state(state):
    result = copy.deepcopy(state)
    parsed = urlparse(result['url'])
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.query or parsed.fragment:
        raise ValueError('Only ephemeral local state.url may be normalized')
    result['url'] = 'http://127.0.0.1:EPHEMERAL' + parsed.path
    return result


def public_input(checkpoint, state, history):
    return base.public_context(state, history, checkpoint['pending'])


def call(api, out, stage, context, image, system=None):
    raw = api.call(out, system if system is not None else base.PROMPTS[stage],
                   context, image, base.SCHEMAS[stage], stage)
    base.dump(out / 'raw.json', {'content': raw})
    parsed = json.loads(raw)
    base.validate(stage, parsed, context)
    base.dump(out / 'accepted.json', parsed)
    return parsed


def question_request(name, context, initial):
    full = {**copy.deepcopy(context), 'initial_chains': copy.deepcopy(initial['chains'])}
    if name in ('action_conclusion_only', 'option_search'):
        key = 'V1' if name == 'action_conclusion_only' else 'V2'
        request = strategies.make_strategy_request(key, base.PROMPTS['questions_new'], full)
        return request['system'], request['context']
    if name == 'fresh_search':
        # No prior candidate content or comparison result. Current selection remains visible.
        common = importlib.import_module('prompts').COMMON
        return FRESH_QUESTION_PREFIX + common, copy.deepcopy(context)
    raise ValueError('Unknown strategy')


def hypothesis_candidates(api, out, context, image):
    """Explore every public option symmetrically. Never filter on gold or verdicts."""
    labels = context['options']
    if not labels or len(labels) > 3 or len(set(labels)) != len(labels):
        raise ValueError('This bounded panel supports one to three distinct public options')
    schema = copy.deepcopy(base.SCHEMAS['initial'])
    schema['properties']['chains']['maxItems'] = 1
    common = importlib.import_module('prompts').COMMON
    result = {'hypotheses': [], 'new_chains': []}
    for index, label in enumerate(labels):
        query = {**copy.deepcopy(context), 'hypothesis_option': label,
                 'search_question': 'Could selecting this public option follow from another image-grounded reading?'}
        folder = out / ('hypothesis_%02d' % index)
        raw = api.call(folder, HYPOTHESIS_PREFIX + common, query, image, schema, 'hypothesis')
        base.dump(folder / 'raw.json', {'content': raw})
        parsed = json.loads(raw)
        base.validate('initial', parsed, context)
        if len(parsed['chains']) > 1 or any(c['C']['option_label'] != label for c in parsed['chains']):
            raise ValueError('Hypothesis response violates the supplied one-candidate interface')
        base.dump(folder / 'accepted.json', parsed)
        renamed = copy.deepcopy(parsed['chains'])
        for chain in renamed:
            chain['id'] = 'hypothesis_%02d_%s' % (index, chain['id'])
        result['hypotheses'].append({'option_label':label,'search_question':query['search_question'],
                                    'response':parsed,'renamed_chain_ids':[c['id'] for c in renamed]})
        result['new_chains'].extend(renamed)
    base.dump(out / 'hypotheses_combined.json',result)
    return result


def branch(api, pw, original, actor, base_url, out, config, ledger, checkpoint, initial, image_ref, submission_path, name):
    env = base.BrowserSession(pw, base_url, out, ledger, original, config)
    item = {'strategy': name, 'status': 'started', 'stages': {}, 'continuation': []}
    offset = base.row_count(submission_path)
    try:
        for event in checkpoint['history']:
            receipt = env.execute(event['action'], 'checkpoint_replay')
            if not receipt['executed'] or receipt['submitted']:
                raise ValueError('Checkpoint replay failed or unexpectedly submitted')
        state, image = env.snapshot()
        match = {'state_equal_except_ephemeral_url_port': normalized_state(state) == normalized_state(checkpoint['state']),
                 'history_equal': env.history == checkpoint['history'],
                 'image_equal': base.digest(image) == base.digest(image_ref)}
        base.dump(out / 'replay_check.json', match)
        item['replay_check'] = match
        if not all(match.values()):
            raise ValueError('Reconstructed checkpoint is not identical')
        context = public_input(checkpoint, state, env.history)
        if name == 'symmetric_hypotheses':
            hypotheses = hypothesis_candidates(api, out, context, image)
            item['stages']['hypotheses'] = hypotheses
            # No claim that a question model or the old supplement stage ran here.
            new_chains = hypotheses['new_chains']
        else:
            system, qcontext = question_request(name, context, initial)
            questions = call(api, out / 'questions', 'questions_new', qcontext, image, system)
            item['stages']['questions'] = questions
            supplement_context = {**copy.deepcopy(context), 'initial_chains': copy.deepcopy(initial['chains']),
                                  'questions': questions['questions']}
            if questions['questions']:
                supplement = call(api, out / 'supplement', 'supplement', supplement_context, image)
            else:
                supplement = {'new_chains': [], 'question_responses': []}
                base.dump(out / 'supplement_skipped.json', {'reason': 'zero_questions', 'result': supplement})
            item['stages']['supplement'] = supplement
            new_chains = supplement['new_chains']
        chains = copy.deepcopy(initial['chains']) + new_chains
        if len(chains) > base.SCHEMAS['verify']['properties']['checks']['maxItems']:
            raise ValueError('Verification capacity exceeded; do not silently drop candidates')
        item['new_action_labels'] = sorted({c['C']['option_label'] for c in new_chains if c['C']['option_label'] is not None}
                                        - {c['C']['option_label'] for c in initial['chains']})
        verify_context = {k:copy.deepcopy(context[k]) for k in ('goal','state','history','options')}
        verify_context['chains'] = chains
        verification = call(api, out / 'verification', 'verify', verify_context, image)
        item['stages']['verification'] = verification
        report = {'chains': chains, 'verification': verification}
        base.dump(out / 'candidate_review.json', report)
        # No semantic/gold-based routing: every completed verification reaches ordinary actor.
        for index in range(config['continuation_max_calls']):
            action, state, image = actor.next(env, out / ('actor_%02d' % index), report)
            event = {'action': action, 'selection_before': base.selected(state), 'image': str(image)}
            item['continuation'].append(event)
            if action['action'] == 'finish':
                event['receipt'] = {'executed': False, 'submitted': False, 'reason': 'actor_finished'}
                break
            event['receipt'] = env.execute(action, 'continuation_actor')
            base.dump(out / 'result.json', item)
            if event['receipt']['submitted']:
                env.snapshot()
                break
        item.update(base.score(submission_path, offset))
        item['status'] = 'completed' if item['submitted'] else 'actor_finished_or_call_limit'
    except base.LimitStop:
        raise
    except Exception as exc:
        item.update(status='failed_no_quality_retry', error={'type':type(exc).__name__,'message':str(exc)},
                    **base.score(submission_path, offset))
    finally:
        base.dump(out / 'result.json', item)
        env.close()
    return item


def run_arm(arm, prior, output, project, config, ledger, api, original, actor):
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    out = output / arm
    out.mkdir()
    checkpoint = read(prior / arm / 'checkpoint.json')
    initial = read(prior / arm / 'shared_initial/accepted.json')
    image_ref = prior / arm / 'prefix' / Path(checkpoint['image']).name
    # Archive exactly what was reused; no old manifest/result is edited.
    base.dump(out / 'source_checkpoint.json', checkpoint)
    base.dump(out / 'shared_initial.json', initial)
    shutil.copyfile(image_ref, out / 'source_checkpoint.png')
    base.dump(out / 'reuse_provenance.json', {'source_run':str(prior),
              'checkpoint_sha256':base.digest(prior / arm / 'checkpoint.json'),
              'initial_sha256':base.digest(prior / arm / 'shared_initial/accepted.json'),
              'image_sha256':base.digest(image_ref), 'new_natural_prefix':False})
    submissions = out / 'private/submissions.jsonl'
    submissions.parent.mkdir()
    tasks = project / 'web_agent_benchmark/benchmark_v2_open/splits' / arm / 'public39_tasks.jsonl'
    if base.digest(tasks) != read(prior / arm / 'result.json')['task_file_sha256']:
        raise ValueError('Original task/rule/gold file differs from the recorded prior run')
    app = original.shell.make_app(submissions, tasks, out / 'private/shell_summary.md', False)
    server = make_server('127.0.0.1', 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    item = {'arm':arm,'task':config['task'],'status':'started','branches':{},'task_file_sha256':base.digest(tasks)}
    try:
        with sync_playwright() as pw:
            for name in config['strategies']:
                print('START %s %s' % (arm,name), flush=True)
                result = branch(api,pw,original,actor,'http://127.0.0.1:%d'%server.server_port,
                                out/name,config,ledger,checkpoint,initial,image_ref,submissions,name)
                item['branches'][name] = result
                base.dump(out / 'result.json', item)
                print(json.dumps({'arm':arm,'strategy':name,'status':result['status'],
                                 'questions':len(result.get('stages',{}).get('questions',{}).get('questions',[])),
                                 'new_chains':len(result.get('stages',{}).get('hypotheses',result.get('stages',{}).get('supplement',{})).get('new_chains',[])),
                                 'outcome':result.get('outcome')},ensure_ascii=False), flush=True)
        item['status'] = 'completed_panel'
    finally:
        base.dump(out / 'result.json',item)
        server.shutdown()
        server.server_close()
    return item


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--prior-run',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    config=read(HERE/'config.json')
    os.environ.pop('WEB_AGENT_EXTRA_SYSTEM_PROMPT',None)
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(args.project))
    original=importlib.import_module('web_agent_benchmark.evaluation.run_public39')
    # Depend on the exact reviewed previous runtime, not an unnoticed later edit.
    old_hashes=read(args.prior_run/'source_hashes.json')
    for path, expected in old_hashes.items():
        if base.digest(path) != expected:
            raise ValueError('A prior dependency changed: '+path)
    if args.output.exists():
        raise FileExistsError('Output exists; no replacement rerun')
    with (HERE/'LIVE_SEARCH_LOCK.json').open('x',encoding='utf-8') as stream:
        json.dump({'output':str(args.output),'prior':str(args.prior_run),'scope':'fixed_search_panel'},stream)
    args.output.mkdir(parents=True)
    ledger=base.Ledger(args.output,config)
    ledger.save()
    api=base.LocalAPI(config,ledger)
    # Read-only health probe, not a model inference request.
    health=api.http.get('http://127.0.0.1:8058/health',timeout=10,allow_redirects=False)
    models=api.http.get('http://127.0.0.1:8058/v1/models',timeout=10,allow_redirects=False).json()
    base.dump(args.output/'service_preflight.json',{'health':health.status_code,'models':models})
    if health.status_code != 200 or config['model'] not in [m['id'] for m in models['data']]:
        raise ValueError('Existing service unavailable; no fallback')
    base.dump(args.output/'config.json',config)
    snapshots={}
    sources=list(HERE.glob('*.py'))+[HERE/'config.json',HERE/'PROTOCOL.md']+[Path(p) for p in old_hashes]
    for source in sources:
        target=args.output/'runtime_source'/source.relative_to(args.project)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        snapshots[str(source)]=base.digest(source)
    base.dump(args.output/'source_hashes.json',snapshots)
    actor=base.Actor(original,api,read(BASE_DIR/'browser_action_schema.json'))
    summary={'status':'running','results':[],'new_natural_prefixes':0,'paid_api_requests':0}
    try:
        for arm in config['arms']:
            summary['results'].append(run_arm(arm,args.prior_run,args.output,args.project,config,ledger,api,original,actor))
            base.dump(args.output/'summary.json',summary)
        summary['status']='finished'
    except Exception as exc:
        summary.update(status='stopped',error={'type':type(exc).__name__,'message':str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'],browser_operations=ledger.data['browser_operations'],
                       source_preserved={p:base.digest(p)==sha for p,sha in snapshots.items()})
        base.dump(args.output/'summary.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
