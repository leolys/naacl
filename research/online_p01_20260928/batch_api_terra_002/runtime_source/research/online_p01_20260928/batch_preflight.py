"""All original task-condition POST controls, explicitly not agent results."""
import sys
import json
from pathlib import Path
from bs4 import BeautifulSoup
from deps import HERE, wire
import original_env


def main():
    runtime=HERE/'runtime_snapshot'
    if not runtime.is_dir():raise ValueError('prepare isolated original runtime first')
    sys.path.insert(0,str(runtime))
    original_env.SNAPSHOT=runtime
    output=HERE/'batch_post_controls'
    output.mkdir(exist_ok=False)
    apps={}
    results=[]
    for case in original_env.catalog():
        group=case['domain']+'_'+case['arm']
        if group not in apps: apps[group]=original_env.make_original(case,output/'private'/group).test_client()
        client=apps[group]
        prefix='/task/'+case['task_id']
        row={'case':case,'evidence_mode':'offline_http_scripted_control_not_agent','model_calls':0,'browser_operations':0}
        try:
            client.get(prefix)
            client.get(prefix+'/dashboard')
            response=client.get(prefix+'/form')
            form=BeautifulSoup(response.data,'html.parser').find('form')
            payload={}
            for e in form.select('input,select,textarea'):
                name=e.get('name')
                if not name:continue
                if e.name=='select':
                    option=next((o for o in e.find_all('option') if o.get('value') and not o.has_attr('disabled')),None)
                    if option:payload[name]=option['value']
                elif e.name=='textarea':payload[name]='Scripted interface control' if e.has_attr('required') else ''
                elif e.get('type') in ('checkbox','radio'):
                    if e.has_attr('checked') or e.has_attr('required'):payload[name]=e.get('value','on')
                else:payload[name]=e.get('value','')
            post=client.post(form['action'],data=payload)
            if post.status_code!=302:raise ValueError('POST_not_redirect')
            location=post.headers['Location']
            if not location.endswith('/confirmation'):raise ValueError('not_original_confirmation')
            confirmed=client.get(location)
            if confirmed.status_code!=200:raise ValueError('confirmation_unavailable')
            if b'evaluation_hidden_from_agent' in confirmed.data:raise ValueError('private_evaluation_in_confirmation')
            row.update(status='pass_original_post',confirmation=location)
        except Exception as exc:row.update(status='fail',error=str(exc))
        results.append(row)
    wire.dump(output/'summary.json',{'units':results,'total':len(results),'passed':sum(r['status']=='pass_original_post' for r in results),
        'model_calls':0,'browser_operations':0,'offline_http_operations':len(results)*5,
        'claim':'Original GET/POST/confirmation interface controls only; not accuracy or browser-model robustness.'})
    print(json.dumps({'total':len(results),'passed':sum(r['status']=='pass_original_post' for r in results)}))


if __name__=='__main__':main()
