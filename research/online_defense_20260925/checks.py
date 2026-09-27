"""Offline original-route audit and clearly scripted browser controls (no model)."""
import argparse
import json
from pathlib import Path
from deps import HERE, wire, public_inputs, Budget
from original_env import catalog, make_original, OriginalBrowser
from runner import config_and_cases


def audit_all(output):
    results=[]
    apps={}
    for case in catalog():
        group=case['domain']+'_'+case['arm']
        if group not in apps:
            apps[group]=make_original(case,output/'private'/group).test_client()
        client=apps[group]
        prefix='/task/'+case['task_id']
        row={'case':case,'model_calls':0,'http_gets':0}
        try:
            pages={}
            for name,suffix in [('home',''),('dashboard','/dashboard'),('form','/form')]:
                response=client.get(prefix+suffix)
                row['http_gets']+=1
                if response.status_code!=200: raise ValueError('original_page_http_'+str(response.status_code))
                pages[name]=response.get_data(as_text=True)
            public,bindings=public_inputs.extract(pages,case['alias'])
            row['bindings_checked']=public_inputs.verify_bindings(public,bindings,pages)
            response=client.get(prefix+'/chart')
            row['http_gets']+=1
            if response.status_code!=200 or not response.content_type.startswith('image/'):
                raise ValueError('original_chart_missing')
            row.update(status='supported_original_routes',option_count=len(public['option_labels']),chart_bytes=len(response.data))
            path=output/'public_catalog'/group/(case['task_id']+'.json')
            wire.dump(path,{'task':public,'bindings':bindings})
        except Exception as exc:
            row.update(status='unsupported',error=type(exc).__name__+':'+str(exc))
        results.append(row)
    wire.dump(output/'asset_audit.json',{'cases':results,'count':len(results),'supported':sum(r['status']=='supported_original_routes' for r in results),
        'model_calls':0,'browser_operations':0,'offline_http_gets':sum(r['http_gets'] for r in results),
        'scope':'GET route/projection readiness only, not model or all-task POST validation'})
    return results


def browser_controls(output):
    config,cases=config_and_cases()
    budget=Budget(HERE/'live_budget.json',config)
    results=[]
    # Select by public DOM position, not by gold. This is a mechanical interface control.
    for case in [cases[0],cases[2],cases[4]]:
        folder=output/case['task_id']
        row={'case':case,'evidence_mode':'scripted_browser_control','model_calls':0}
        with OriginalBrowser(case,folder,budget,config['browser_executable']) as browser:
            for _ in range(3):
                context,_=browser.snapshot()
                if context['state']['page']=='form': break
                links=context['state']['links']
                candidates=[s for s in links if ('dashboard' in s.lower() if context['state']['page']=='home' else 'form' in s.lower())]
                if len(candidates)!=1: raise ValueError('control_cannot_identify_ordinary_navigation')
                assert browser.execute({'kind':'open_link','label':candidates[0]})['ok']
            context,_=browser.snapshot()
            assert browser.public and browser.chart
            assert context['state']['current_selection']==''
            option=context['state']['options'][0]
            receipt=browser.execute({'kind':'select','option':option})
            assert receipt['observed_selection_after']==option
            context,_=browser.snapshot()
            assert any(s['label']==option and s['selected'] for s in context['state']['option_states'])
            for field in context['state']['fields']:
                if not field['required'] or field['readonly'] or field['value']:continue
                action={'kind':'select_field','field':field['field'],'option':field['options'][0]} if field['type']=='select' else (
                    {'kind':'check','field':field['field'],'value':True} if field['type']=='checkbox' else
                    {'kind':'fill','field':field['field'],'value':'Scripted interface control'})
                assert browser.execute(action)['ok']
            posted=browser.execute({'kind':'submit'})
            assert posted['submitted']
            context,_=browser.snapshot()
            assert context['state']['page']=='confirmation'
            assert 'evaluation_hidden_from_agent' not in json.dumps(context)
            row.update(status='passed_original_submit',history=browser.history)
        # Hidden server scores are not inspected by the scripted action chooser.
        results.append(row)
    wire.dump(output/'browser_controls.json',{'cases':results,'budget_browser_operations':budget.value['browser_operations'],
        'model_calls':0,'ability_evidence':False})
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',choices=['assets','browser'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    rows=audit_all(args.output) if args.kind=='assets' else browser_controls(args.output)
    print(json.dumps({'count':len(rows),'kind':args.kind,'status':'completed'},ensure_ascii=False))
