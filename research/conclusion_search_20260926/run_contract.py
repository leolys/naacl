"""Output-contract development revision, never a repair of prior model outputs."""
from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_additional as additional
search=additional.search
base=search.base

OLD_EXAMPLE='Return {"chains":[],"notes":"coverage and limits"}.\n'
CONTRACT='''Return JSON matching the supplied schema. If you decide to propose a
candidate, write its complete O, B, and C in chains in THIS response. Do not put
the candidate only in notes or promise to provide it later. notes is a short
coverage/limitation note, not a substitute for the candidate record. Do not refer
to previous attempts or feedback that were not supplied in this request.

The nonempty object structure below contains placeholders, NOT observations or
an answer to adopt. Replace them only with your own image-grounded candidate:
{"chains":[{"id":"h1","O":[{"location":"visible location","content":"literal visible observation"}],
"B":{"rule":"conditional bridge","conditions":["adopted reading and scope"]},
"C":{"claim":"concrete task candidate","option_label":"exact hypothesis option"}}],
"notes":"brief coverage and limits"}.
If you do not propose a complete candidate, use {"chains":[],"notes":"specific coverage or limitation"}.
The complete template is not a requirement to support the hypothesis. Empty is
still allowed. Do not fabricate evidence or change the task to fill the template.
'''


def contract_system(system,stage):
    if stage!='hypothesis':
        return system
    if system.count(OLD_EXAMPLE)!=1:
        raise ValueError('Refuse to alter an unrecognized hypothesis prompt')
    return system.replace(OLD_EXAMPLE,CONTRACT,1)


class ContractAPI(base.LocalAPI):
    def call(self,folder,system,context,image,schema,stage):
        return super().call(folder,contract_system(system,stage),context,image,schema,stage)


class ContractChartAPI(additional.FullChartAPI):
    def chart_image(self,context,folder):
        image=super().chart_image(context,folder)
        arm=Path(folder).parents[1].name
        reference=HERE/'run_chart_001'/arm/'public_chart_observation/chart.png'
        if base.digest(image)!=base.digest(reference):
            raise ValueError('Contract revision must keep the exact V5 full-chart input bytes')
        return image

    def call(self,folder,system,context,image,schema,stage):
        return super().call(folder,contract_system(system,stage),context,image,schema,stage)


def static_contract_case(case,parent,output,api):
    out=output/case
    out.mkdir()
    old=parent/case
    context=search.read(old/'public_context.json')
    initial=search.read(old/'shared_initial/accepted.json')
    image=old/'chart.png'
    manifest=search.read(old/'source_manifest.json')
    if base.digest(old/'public_context.json')!=manifest['context_sha256'] or base.digest(image)!=manifest['png_sha256']:
        raise ValueError('Static revision must use exactly the prior public inputs')
    base.dump(out/'public_context.json',context)
    base.dump(out/'shared_initial.json',initial)
    shutil.copyfile(image,out/'chart.png')
    base.dump(out/'reuse_provenance.json',{'source':str(old),'initial_sha256':base.digest(old/'shared_initial/accepted.json'),
              'image_sha256':base.digest(image),'context_sha256':base.digest(old/'public_context.json')})
    item={'case':case,'mode':'static_public_task_transfer','initial':initial,'branches':{},'submitted':False,'business_actions':0}
    branch={'status':'started','stages':{},'submitted':False,'actor_status':'not_run_static_diagnostic'}
    item['branches']['contract_hypotheses']=branch
    folder=out/'contract_hypotheses'
    folder.mkdir()
    try:
        hypotheses=search.hypothesis_candidates(api,folder,context,image)
        branch['stages']['hypotheses']=hypotheses
        chains=copy.deepcopy(initial['chains'])+hypotheses['new_chains']
        verification=additional.transfer_verify(api,folder/'verification',
            {k:copy.deepcopy(context[k]) for k in ('goal','state','history','options')}|{'chains':chains},image)
        branch['stages']['verification']=verification
        branch['new_action_labels']=sorted({c['C']['option_label'] for c in hypotheses['new_chains'] if c['C']['option_label'] is not None}
                                          -{c['C']['option_label'] for c in initial['chains']})
        branch['status']='completed_static_only'
        item['status']='completed_panel'
    except base.LimitStop:
        branch['status']='stopped_by_global_limit_or_transport'
        raise
    except Exception as exc:
        branch.update(status='failed_no_quality_retry',error={'type':type(exc).__name__,'message':str(exc)})
        item['status']='failed_no_quality_retry'
    finally:
        base.dump(folder/'result.json',branch)
        base.dump(out/'result.json',item)
    return item


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--parent-run',required=True,type=Path)
    parser.add_argument('--prior-run',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    parent=args.parent_run.resolve()
    if parent!=(HERE/'run_transfer_001').resolve() or search.read(parent/'summary.json')['status']!='finished':
        raise ValueError('Complete the frozen transfer panel before this revision')
    inherited=search.read(parent/'ledger.json')
    if inherited.get('blocked_reason'):
        raise ValueError('Cannot reset a blocked cumulative ledger')
    parent_sources=search.read(parent/'source_hashes.json')
    for path,sha in parent_sources.items():
        if base.digest(path)!=sha:
            raise ValueError('Preserve parent sources: '+path)
    config=search.read(HERE/'config.json')
    parent_config=search.read(parent/'config.json')
    for key in ('model','endpoint','temperature','top_p','top_k','seed','enable_thinking','max_request_attempts','max_browser_operations'):
        if config[key]!=parent_config[key]:
            raise ValueError('This revision may not alter '+key)
    additional.assert_checkpoint_source(args.prior_run,HERE/'run_live_001',config['arms'])
    if args.output.exists():
        raise FileExistsError('Do not overwrite a contract revision')
    with (HERE/'LIVE_CONTRACT_LOCK.json').open('x',encoding='utf-8') as stream:
        json.dump({'output':str(args.output),'parent':str(parent),'scope':'same_100_300_total'},stream)
    args.output.mkdir()
    config['strategies']=['symmetric_hypotheses']
    config['phase']='output_contract_revision'
    config['method_image']='original_full_public_chart'
    base.dump(args.output/'config.json',config)
    ledger=base.Ledger(args.output,config)
    ledger.data=copy.deepcopy(inherited)
    ledger.data['parent_ledger']=str(parent/'ledger.json')
    ledger.save()
    starts=(ledger.data['request_attempts'],ledger.data['browser_operations'])
    source_files=list(HERE.glob('*.py'))+[HERE/'CONTRACT_ADDENDUM.md',HERE/'config.json']+[Path(p) for p in parent_sources]
    snapshots={}
    for source in dict.fromkeys(source_files):
        target=args.output/'runtime_source'/source.relative_to(args.project)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        snapshots[str(source)]=base.digest(source)
    base.dump(args.output/'source_hashes.json',snapshots)
    os.environ.pop('WEB_AGENT_EXTRA_SYSTEM_PROMPT',None)
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(args.project))
    api=ContractChartAPI(config,ledger)
    if api.http.get('http://127.0.0.1:8058/health',timeout=10,allow_redirects=False).status_code!=200:
        raise ValueError('Existing model service is unavailable')
    original=importlib.import_module('web_agent_benchmark.evaluation.run_public39')
    actor=base.Actor(original,api,search.read(search.BASE_DIR/'browser_action_schema.json'))
    static_api=ContractAPI(config,ledger)
    summary={'status':'running','phase':'output_contract_revision','parent_run':str(parent),
             'results':[],'transfer_results':[],'new_natural_prefixes':0}
    try:
        control=HERE/'run_chart_001/nonchart_control'
        control_out=args.output/'nonchart_control'
        control_out.mkdir()
        context=search.read(control/'public_context.json')
        shutil.copyfile(control/'page.png',control_out/'page.png')
        base.dump(control_out/'public_context.json',context)
        summary['nonchart_control']=search.hypothesis_candidates(static_api,control_out,context,control/'page.png')
        base.dump(control_out/'reuse_provenance.json',{'source':str(control),'image_sha256':base.digest(control/'page.png'),
                  'context_sha256':base.digest(control/'public_context.json'),'new_browser_actions':0})
        for arm in config['arms']:
            summary['results'].append(search.run_arm(arm,args.prior_run,args.output,args.project,config,ledger,api,original,actor))
            base.dump(args.output/'summary.json',summary)
        for case in ('b002','pub013'):
            print('START contract static '+case,flush=True)
            summary['transfer_results'].append(static_contract_case(case,parent,args.output,static_api))
            base.dump(args.output/'summary.json',summary)
        summary['status']='finished'
    except Exception as exc:
        summary.update(status='stopped',error={'type':type(exc).__name__,'message':str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'],browser_operations=ledger.data['browser_operations'],
                       phase_request_attempts=ledger.data['request_attempts']-starts[0],
                       phase_browser_operations=ledger.data['browser_operations']-starts[1],
                       source_preserved={p:base.digest(p)==sha for p,sha in snapshots.items()})
        base.dump(args.output/'summary.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k not in ('results','transfer_results','nonchart_control')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
