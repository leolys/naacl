"""Run fixed development or frozen application panel with isolated public messages."""
import argparse
import copy
import importlib.util
import os
from pathlib import Path
import shutil
from engine import Client, GlobalLock, Stop, dump, read, sha, stamp, preflight

HERE = Path(__file__).resolve().parent
VERSIONS = ('plain', 'v4', 'v5', 'v6', 'v7')
COMMON = ('run.py', 'engine.py', 'schema.py', 'config.json', 'manifest.json', 'PLAN.md',
          'legacy/engine.py', 'legacy/schema.py')


def public_context(projected):
    if set(projected) != {'goal', 'public_task', 'options', 'records'}:
        raise Stop('unexpected input projection')
    return copy.deepcopy({key: projected[key] for key in ('goal', 'public_task', 'options')})


def contexts(projected, notes=None, checks=None):
    value = public_context(projected)
    if notes is not None:
        value['records'] = copy.deepcopy(projected['records'])
        value['independent_visual_notes'] = copy.deepcopy(notes)
    if checks is not None:
        if notes is None:
            raise Stop('checks without notes')
        value['ob_checks'] = copy.deepcopy(checks['reviews'])
    return value


def source_hashes(version):
    return {name: sha(HERE / name) for name in COMMON + ('prompts_' + version + '.py',)}


def bounded_config(config):
    if (config['max_attempts'] > 1000 or config['max_dev_versions'] > 4 or
            config['concurrency'] != 1 or config['paid_api_allowed']):
        raise Stop('authorization_bounds_changed')
    expected = {'model': 'Qwen3.8-27B', 'temperature': 0.7, 'top_p': 0.8,
                'top_k': 20, 'seed': 12345, 'enable_thinking': False}
    if any(config[k] != v for k, v in expected.items()):
        raise Stop('fixed decoding changed')
    if config['deadline_utc'] != '2026-09-27T10:30:00+00:00':
        raise Stop('deadline changed')


def run(panel, version):
    if version not in VERSIONS or panel not in ('dev', 'application'):
        raise Stop('unregistered configuration')
    config = read(HERE / 'config.json')
    bounded_config(config)
    hashes = source_hashes(version)
    if panel == 'application':
        freeze = read(HERE / 'FREEZE.json')
        if version != 'plain' and (freeze['version'] != version or freeze['source_hashes'] != hashes):
            raise Stop('application needs exact frozen candidate')
        if version == 'plain':
            if read(HERE / 'runs/plain_dev/source_hashes.json') != hashes:
                raise Stop('baseline changed after development')
    elif version != 'plain' and (HERE / 'FREEZE.json').exists():
        raise Stop('no more development after freeze')
    spec = importlib.util.spec_from_file_location('selected_prompts', HERE / ('prompts_' + version + '.py'))
    prompts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prompts)
    manifest = read(HERE / 'manifest.json')
    units = {key: unit for key, unit in manifest['units'].items() if unit['panel'] == panel}
    output = HERE / 'runs' / (version + '_' + panel)
    if output.exists():
        if read(output / 'source_hashes.json') != hashes:
            raise Stop('run source changed')
    else:
        output.mkdir(parents=True)
        dump(output / 'source_hashes.json', hashes)
        for name in hashes:
            target = output / 'runtime_source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / name, target)
    summary = read(output / 'summary.json') if (output / 'summary.json').exists() else {
        'version': version, 'panel': panel, 'status': 'prepared', 'started': stamp(), 'units': {},
        'business_submissions': 0, 'paid_api_calls': 0}
    if summary['status'] == 'finished':
        print('already finished; no new requests', flush=True)
        return
    api = Client(config, HERE)
    api.guard()
    preflight(api, output)
    summary['status'] = 'running'
    dump(output / 'summary.json', summary)
    dump(HERE / 'ACTIVE.json', {'pid': os.getpid(), 'run': str(output.relative_to(HERE)), 'started': stamp()})
    try:
        for key, unit in units.items():
            data = HERE / 'data' / key
            if sha(data / 'input.json') != unit['input_sha256'] or sha(data / unit['image']) != unit['image_sha256']:
                raise Stop('input changed')
            dest = output / key
            result = read(dest / 'result.json') if (dest / 'result.json').exists() else {'unit': key, 'status': 'prepared'}
            if result['status'] in ('completed', 'interface_failed'):
                summary['units'][key] = result
                continue
            api.guard()
            projected = read(data / 'input.json')
            image = data / unit['image']
            stage = 'decide' if version == 'plain' else 'read'
            try:
                dump(dest / 'projected.json', public_context(projected) if version == 'plain' else projected)
                notes, checks = None, None
                if version != 'plain':
                    print(version + '/' + panel + ' READ ' + key, flush=True)
                    notes = api.call(dest / 'read', prompts.READ, contexts(projected), image, 'read')
                    stage = 'verify'
                    print('VERIFY ' + key, flush=True)
                    checks = api.call(dest / 'verify', prompts.VERIFY, contexts(projected, notes), image, 'verify')
                stage = 'decide'
                print('DECIDE ' + key, flush=True)
                decision = api.call(dest / 'decide', prompts.DECIDE, contexts(projected, notes, checks), image, 'decide')
                result.update(status='completed', choice=decision)
                print('DONE ' + key + ' attempts=' + str(api.ledger['attempts']), flush=True)
            except Stop:
                result.update(status='stopped', stopped_stage=stage)
                raise
            except Exception as exc:
                result.update(status='interface_failed', failed_stage=stage,
                              error={'type': type(exc).__name__, 'message': str(exc)})
            finally:
                dump(dest / 'result.json', result)
                summary['units'][key] = result
                summary['global_attempts'] = api.ledger['attempts']
                dump(output / 'summary.json', summary)
        summary['status'] = 'finished'
    except Exception as exc:
        summary.update(status='stopped', error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        summary.update(ended=stamp(), global_attempts=api.ledger['attempts'],
                       runtime_preserved=source_hashes(version) == hashes)
        dump(output / 'summary.json', summary)
        dump(HERE / 'ACTIVE.json', {'pid': os.getpid(), 'run': str(output.relative_to(HERE)),
                                  'state': 'ended', 'ended': stamp()})
        print(summary['status'] + ' ' + str(len(summary['units'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', choices=VERSIONS, required=True)
    parser.add_argument('--panel', choices=['dev', 'application'], required=True)
    args = parser.parse_args()
    with GlobalLock():
        run(args.panel, args.version)
