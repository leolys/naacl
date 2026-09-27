"""Explicit additional phases with inherited total budget and immutable parents."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_search as search
base=search.base


class FullChartAPI(base.LocalAPI):
    """Only method calls use the complete public chart asset. Actor remains unchanged."""
    def __init__(self,config,ledger):
        super().__init__(config,ledger)
        self.chart_cache={}

    def chart_image(self,context,folder):
        from PIL import Image
        state_url=urlparse(context['state']['url'])
        expected='/task/'+self.config['task']+'/form'
        if (state_url.scheme!='http' or state_url.hostname!='127.0.0.1' or not state_url.port
                or state_url.path!=expected or state_url.query or state_url.fragment):
            raise ValueError('Only the current task public chart endpoint is allowed')
        chart_url='http://'+state_url.netloc+'/task/'+self.config['task']+'/chart'
        observation=Path(folder).parents[1]/'public_chart_observation'
        cache_key=(str(observation.resolve()),chart_url)
        if cache_key in self.chart_cache:
            return self.chart_cache[cache_key]
        observation.mkdir(exist_ok=False)
        self.ledger.event('browser',{'source':'public_chart_asset_get','url':chart_url,'folder':str(observation),
                                     'note':'conservatively counted public observation, not a page-navigation transition'})
        response=self.http.get(chart_url,timeout=30,allow_redirects=False)
        if response.status_code!=200 or not response.headers.get('Content-Type','').startswith('image/'):
            raise ValueError('Public chart asset unavailable')
        original=response.content
        (observation/'original_chart.bin').write_bytes(original)
        with Image.open(io.BytesIO(original)) as chart:
            original_format=chart.format
            decoded=chart.convert('RGB')
            size=decoded.size
            pixel_sha=hashlib.sha256(decoded.tobytes()).hexdigest()
            png=observation/'chart.png'
            decoded.save(png,format='PNG')
        with Image.open(png) as converted:
            if converted.size!=size or hashlib.sha256(converted.convert('RGB').tobytes()).hexdigest()!=pixel_sha:
                raise ValueError('Format conversion altered decoded RGB pixels')
        base.dump(observation/'provenance.json',{'public_url':chart_url,'content_type':response.headers.get('Content-Type'),
                  'original_format':original_format,'original_sha256':hashlib.sha256(original).hexdigest(),
                  'png_sha256':base.digest(png),'rgb_pixels_sha256':pixel_sha,'dimensions':list(size),
                  'local_resize':False,'crop':False,'conversion':'RGB PNG, decoded pixels identical',
                  'scope':'complete public chart asset; no evaluator region selection'})
        self.chart_cache[cache_key]=png
        return png

    def call(self,folder,system,context,image,schema,stage):
        if stage in ('hypothesis','verify'):
            image=self.chart_image(context,folder)
        return super().call(folder,system,context,image,schema,stage)


def transfer_verify(api,out,context,image):
    # All up to 3 initial + 3 new candidates are checked; do not remove inconvenient candidates.
    schema=copy.deepcopy(base.SCHEMAS['verify'])
    schema['properties']['checks']['maxItems']=6
    raw=api.call(out,base.PROMPTS['verify'],context,image,schema,'verify')
    base.dump(out/'raw.json',{'content':raw})
    parsed=json.loads(raw)
    validator=importlib.import_module('schemas')
    validator._validate_shape(parsed,schema,'verify')
    supplied=validator._ids(context['chains'],'id','context.chains')
    checked=validator._ids(parsed['checks'],'chain_id','verify.checks')
    if supplied!=checked:
        raise ValueError('Transfer verification must cover every candidate exactly once')
    base.dump(out/'accepted.json',parsed)
    return parsed


def transfer_case(case,inputs,out,api):
    out.mkdir()
    manifest=search.read(inputs/case/'manifest.json')
    if (base.digest(inputs/case/'public_context.json')!=manifest['context_sha256']
            or base.digest(inputs/case/'chart.png')!=manifest['png_sha256']):
        raise ValueError('Static transfer inputs differ from the audited manifest')
    context=search.read(inputs/case/'public_context.json')
    image=inputs/case/'chart.png'
    shutil.copyfile(image,out/'chart.png')
    base.dump(out/'public_context.json',context)
    base.dump(out/'source_manifest.json',search.read(inputs/case/'manifest.json'))
    item={'case':case,'mode':'static_public_task_transfer','submitted':False,'business_actions':0,'branches':{}}
    try:
        initial=search.call(api,out/'shared_initial','initial',context,image)
        item['initial']=initial
        for name in ('action_conclusion_only','symmetric_hypotheses'):
            folder=out/name
            folder.mkdir()
            branch={'status':'started','stages':{},'submitted':False,'actor_status':'not_run_static_diagnostic'}
            item['branches'][name]=branch
            try:
                if name=='action_conclusion_only':
                    system,qcontext=search.question_request(name,context,initial)
                    questions=search.call(api,folder/'questions','questions_new',qcontext,image,system)
                    branch['stages']['questions']=questions
                    if questions['questions']:
                        supplement=search.call(api,folder/'supplement','supplement',
                            {**copy.deepcopy(context),'initial_chains':copy.deepcopy(initial['chains']),'questions':questions['questions']},image)
                    else:
                        supplement={'new_chains':[],'question_responses':[]}
                        base.dump(folder/'supplement_skipped.json',{'reason':'zero_questions','result':supplement})
                    branch['stages']['supplement']=supplement
                    new=supplement['new_chains']
                else:
                    hypotheses=search.hypothesis_candidates(api,folder,context,image)
                    branch['stages']['hypotheses']=hypotheses
                    new=hypotheses['new_chains']
                chains=copy.deepcopy(initial['chains'])+new
                verification=transfer_verify(api,folder/'verification',
                    {k:copy.deepcopy(context[k]) for k in ('goal','state','history','options')}|{'chains':chains},image)
                branch['stages']['verification']=verification
                branch['new_action_labels']=sorted({c['C']['option_label'] for c in new if c['C']['option_label'] is not None}
                                                  -{c['C']['option_label'] for c in initial['chains']})
                branch['status']='completed_static_only'
            except base.LimitStop:
                branch['status']='stopped_by_global_limit_or_transport'
                raise
            except Exception as exc:
                branch.update(status='failed_no_quality_retry',error={'type':type(exc).__name__,'message':str(exc)})
            finally:
                base.dump(folder/'result.json',branch)
                base.dump(out/'result.json',item)
        item['status']='completed_panel'
    except base.LimitStop:
        item['status']='stopped_by_global_limit_or_transport'
        raise
    except Exception as exc:
        item.update(status='failed_no_quality_retry',error={'type':type(exc).__name__,'message':str(exc)})
    finally:
        base.dump(out/'result.json',item)
    return item


def assert_checkpoint_source(prior,parent,arms):
    for arm in arms:
        expected=search.read(parent/arm/'reuse_provenance.json')
        checkpoint=search.read(prior/arm/'checkpoint.json')
        image=prior/arm/'prefix'/Path(checkpoint['image']).name
        actual={'checkpoint_sha256':base.digest(prior/arm/'checkpoint.json'),
                'initial_sha256':base.digest(prior/arm/'shared_initial/accepted.json'),
                'image_sha256':base.digest(image)}
        if any(actual[key]!=expected[key] for key in actual):
            raise ValueError('Chart phase must reuse the same original checkpoint/initial/image')


def positive_control(output,api,ledger,config):
    """A disclosed non-chart test of the unchanged hypothesis interface, not an outcome gate."""
    from playwright.sync_api import sync_playwright
    folder=output/'nonchart_control'
    folder.mkdir()
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Routing review</title>
<body style="font:28px sans-serif;margin:60px"><h1>Routing review</h1><p>Value: <strong>7</strong></p>
<p>Public rule: if the value is at least 5, choose Route A; otherwise choose Route B.</p>
<label>Route <select><option selected>Select a route</option><option>Route A</option><option>Route B</option></select></label>
</body></html>'''
    (folder/'page.html').write_text(html,encoding='utf-8')
    context={'goal':'Choose the route according to the public rule.',
             'state':{'view_mode':'nonchart_control','text':'Value: 7. Public rule: if the value is at least 5, choose Route A; otherwise choose Route B.',
                      'current_selection':''},'history':[],'options':['Route A','Route B'],'pending_proposal':None}
    base.dump(folder/'public_context.json',context)
    image=folder/'page.png'
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport=config['viewport'])
            page.route('**/*',lambda route:route.abort())
            ledger.event('browser',{'source':'nonchart_control_set_content','folder':str(folder)})
            page.set_content(html,wait_until='load')
            page.screenshot(path=str(image),full_page=True)
        finally:
            browser.close()
    # Bypass only FullChartAPI's image replacement, because this is not a benchmark form.
    control_api=base.LocalAPI(config,ledger)
    result=search.hypothesis_candidates(control_api,folder,context,image)
    base.dump(folder/'result.json',{'status':'completed','result':result,'model_calls_expected':2,
              'scope':'nonchart interface control; does not measure chart explanation quality',
              'predeclared_expectation_offline_only':'A can have a complete chain; B should not require a fabricated chain'})
    return {'status':'completed','candidate_counts':[len(h['response']['chains']) for h in result['hypotheses']]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',required=True,choices=['chart','transfer'])
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--parent-run',required=True,type=Path)
    parser.add_argument('--prior-run',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    parent=args.parent_run.resolve()
    expected_parent=HERE/('run_live_001' if args.phase=='chart' else 'run_chart_001')
    if parent!=expected_parent.resolve() or search.read(parent/'summary.json')['status']!='finished':
        raise ValueError('Additional phase requires its exact completed parent panel')
    if args.phase=='chart':
        assert_checkpoint_source(args.prior_run,parent,search.read(HERE/'config.json')['arms'])
    inherited=search.read(parent/'ledger.json')
    if inherited.get('blocked_reason'):
        raise ValueError('Parent ledger is blocked; no budget reset or fallback')
    parent_sources=search.read(parent/'source_hashes.json')
    for path,sha in parent_sources.items():
        if base.digest(path)!=sha:
            raise ValueError('Parent runtime dependency changed: '+path)
    config=search.read(HERE/'config.json')
    if config['max_request_attempts']!=100 or config['max_browser_operations']!=300:
        raise ValueError('Do not enlarge this authorization ledger')
    for key in ('model','endpoint','temperature','top_p','top_k','seed','enable_thinking','max_request_attempts','max_browser_operations'):
        if config[key]!=search.read(parent/'config.json')[key]:
            raise ValueError('This additional phase cannot change '+key)
    if args.output.exists():
        raise FileExistsError('Preserve existing additional-phase output')
    with (HERE/('LIVE_'+args.phase.upper()+'_LOCK.json')).open('x',encoding='utf-8') as stream:
        json.dump({'output':str(args.output),'parent':str(parent),'scope':'shared_100_300_budget'},stream)
    args.output.mkdir()
    config['strategies']=['symmetric_hypotheses']
    config['phase']=args.phase
    config['method_image']='original_full_public_chart' if args.phase=='chart' else 'static_full_chart'
    ledger=base.Ledger(args.output,config)
    ledger.data=copy.deepcopy(inherited)
    ledger.data['parent_ledger']=str(parent/'ledger.json')
    ledger.save()
    start_requests=ledger.data['request_attempts']
    start_browser=ledger.data['browser_operations']
    api=FullChartAPI(config,ledger) if args.phase=='chart' else base.LocalAPI(config,ledger)
    health=api.http.get('http://127.0.0.1:8058/health',timeout=10,allow_redirects=False)
    if health.status_code!=200:
        raise ValueError('Existing model service unavailable')
    os.environ.pop('WEB_AGENT_EXTRA_SYSTEM_PROMPT',None)
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(args.project))
    source_files=list(HERE.glob('*.py'))+[HERE/'config.json',HERE/'PROTOCOL.md',HERE/'CHART_ADDENDUM.md',HERE/'TRANSFER_PROTOCOL.md']+[Path(p) for p in parent_sources]
    snapshots={}
    for source in dict.fromkeys(source_files):
        target=args.output/'runtime_source'/source.relative_to(args.project)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        snapshots[str(source)]=base.digest(source)
    base.dump(args.output/'source_hashes.json',snapshots)
    base.dump(args.output/'config.json',config)
    summary={'status':'running','phase':args.phase,'results':[],'parent_run':str(parent),'new_natural_prefixes':0}
    try:
        if args.phase=='chart':
            try:
                summary['nonchart_control']=positive_control(args.output,api,ledger,config)
            except base.LimitStop:
                raise
            except Exception as exc:
                summary['nonchart_control']={'status':'failed_no_quality_retry','error':{'type':type(exc).__name__,'message':str(exc)}}
                base.dump(args.output/'nonchart_control/result.json',summary['nonchart_control'])
            original=importlib.import_module('web_agent_benchmark.evaluation.run_public39')
            actor=base.Actor(original,api,search.read(search.BASE_DIR/'browser_action_schema.json'))
            for arm in config['arms']:
                summary['results'].append(search.run_arm(arm,args.prior_run,args.output,args.project,config,ledger,api,original,actor))
                base.dump(args.output/'summary.json',summary)
        else:
            for case in ('b002','pub013'):
                print('START static transfer '+case,flush=True)
                summary['results'].append(transfer_case(case,HERE/'transfer_inputs',args.output/case,api))
                base.dump(args.output/'summary.json',summary)
                print(json.dumps(summary['results'][-1],ensure_ascii=False),flush=True)
        summary['status']='finished'
    except Exception as exc:
        summary.update(status='stopped',error={'type':type(exc).__name__,'message':str(exc)})
        raise
    finally:
        summary.update(request_attempts=ledger.data['request_attempts'],browser_operations=ledger.data['browser_operations'],
                       phase_request_attempts=ledger.data['request_attempts']-start_requests,
                       phase_browser_operations=ledger.data['browser_operations']-start_browser,
                       source_preserved={p:base.digest(p)==sha for p,sha in snapshots.items()})
        base.dump(args.output/'summary.json',summary)
        print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
