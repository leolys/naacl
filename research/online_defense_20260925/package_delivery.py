"""Create a self-contained artifact/code/data bundle, excluding credentials and environments."""
from datetime import datetime, timezone, timedelta
import importlib.metadata
from pathlib import Path
import re
import shutil
import zipfile
from deps import HERE, PROJECT, wire


def main():
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    for source,stem in [(HERE/'REPORT.md','EXPERIMENT_RESULTS'),
                        (HERE/'refine-logs/EXPERIMENT_TRACKER_20260926_002000.md','EXPERIMENT_TRACKER')]:
        versioned=HERE/'refine-logs'/(stem+'_'+stamp+'.md')
        shutil.copy2(source,versioned)
        shutil.copy2(versioned,HERE/'refine-logs'/(stem+'.md'))
    packages={name:importlib.metadata.version(name) for name in (
        'requests','Flask','playwright','Pillow','beautifulsoup4','Jinja2','Werkzeug',
        'itsdangerous','click','MarkupSafe','urllib3','certifi','charset-normalizer','greenlet','pyee','typing_extensions')}
    wire.dump(HERE/'observed_packages.json',{'observed_environment_only':True,'packages':packages,
        'note':'No packages installed. This is observed local provenance, not a separately tested portable lockfile.'})
    files=[]
    for path in HERE.rglob('*'):
        if path.is_file() and not any(x in path.parts for x in ('__pycache__','.pytest_cache','.venv')):
            if path.name not in ('FILE_MANIFEST.json','PACKAGE_CHECK.json') and path.suffix.lower()!='.zip':files.append(path)
    # Restore the relative import layout for the new code using actually observed
    # inherited source dependencies, without packaging unrelated historical runs.
    for runtime in [HERE/'live_v2_schema_debug/runtime.json',HERE/'batch_prepared_v2/runtime.json']:
        for name in wire.read(runtime)['sources']:
            path=Path(name)
            if path.is_file() and path.is_relative_to(PROJECT):files.append(path)
    # The HTML rebuild helper is packaged read-only, never edited in-place.
    helper=PROJECT/'.agents/skills/render-html/scripts'
    files += [helper/'render_html.py',helper/'templates/academic.html',helper/'templates/dashboard.html']
    files += [PROJECT/'aris_repo/tools/evidence_check.py']
    for skill in ('experiment-bridge','result-to-claim','render-html'):
        trace=PROJECT/'.aris/traces'/skill/'2026-09-26_online_defense'
        files += [p for p in trace.rglob('*') if p.is_file()]
    files=list(dict.fromkeys(files))
    files.sort(key=lambda p:str(p.relative_to(PROJECT)))
    bad=[]
    records=[]
    credential=re.compile(rb'\bsk-[A-Za-z0-9_-]{18,}')
    for path in files:
        body=path.read_bytes()
        if path.suffix.lower() in ('.json','.jsonl','.py','.md','.txt','.html','.xml') and credential.search(body):
            bad.append(str(path.relative_to(PROJECT)))
        records.append({'file':str(path.relative_to(PROJECT)).replace('\\','/'),
                        'bytes':len(body),'sha256':wire.digest(path)})
    if bad:
        raise ValueError('Credential-like data found; bundle not written. Inspect filenames only: '+repr(bad))
    manifest=HERE/'FILE_MANIFEST.json'
    wire.dump(manifest,{'generated_after_run':True,'not_retroactive_historical_attestation':True,
        'recorded_at':datetime.now(timezone.utc).isoformat(),'files':records,
        'credential_like_string_matches':0})
    files.append(manifest)
    archive=HERE.parent/'ONLINE_DEFENSE_DEVELOPER_BUNDLE_20260926.zip'
    if archive.exists():raise ValueError('Refuse to overwrite delivery archive')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for path in files:output.write(path,path.relative_to(PROJECT).as_posix())
    with zipfile.ZipFile(archive) as check:
        failed=check.testzip()
        assert failed is None
        assert len(check.namelist())==len(set(check.namelist()))==len(files)
    wire.dump(HERE/'PACKAGE_CHECK.json',{'archive':str(archive),'files':len(files),
        'bytes':archive.stat().st_size,'sha256':wire.digest(archive),'zip_crc_check':'pass',
        'credential_like_string_matches':0,'model_calls':0,
        'scope':'Offline developer artifact/code bundle, not full-benchmark execution or scientific success.'})
    print('Bundle:',len(files),'files,',archive.stat().st_size,'bytes; CRC pass; secret scan zero.')


if __name__=='__main__':main()
