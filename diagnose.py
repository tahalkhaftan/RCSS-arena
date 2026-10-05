"""Reproduce one private uploaded match with a debug server and retain traces privately."""
import json
import os
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path
from app import extract, validate
from github_api import storage_client
from runner import run_job


def main():
    gh=storage_client(); gh.require_private()
    source=int(os.environ['RELEASE_ID']); assets=gh.assets(source)
    config=validate(json.loads(gh.read_asset(assets['config.json'])))
    config.update(rounds=1,games_per_round=1)
    scenario=os.environ.get('DIAGNOSTIC_SCENARIO','uploaded')
    if scenario=='control':
        config['right']=dict(config['left'],name='AITech_control',command='./start.sh -h 127.0.0.1 -t AITech_control')
    root=Path('diagnostic-data-'+scenario).resolve(); root.mkdir(exist_ok=True)
    for side in ('left','right'):
        asset='left.zip' if scenario=='control' else side+'.zip'
        extract(gh.read_asset(assets[asset]),root/'teams'/side)
    wrapper=root/'debug-server.sh'
    wrapper.write_text('#!/bin/sh\nexec gdb -batch -return-child-result -ex "set startup-with-shell off" -ex run -ex "thread apply all bt" --args "$RCSS_DEBUG_SERVER" "$@"\n')
    wrapper.chmod(0o700)
    os.environ['RCSS_DEBUG_SERVER']=os.environ['RCSSSERVER']
    os.environ['RCSSSERVER']=str(wrapper)
    os.environ['MATCH_TIMEOUT_SECONDS']='300'
    for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_USER','ARENA_PASSWORD'): os.environ.pop(key,None)
    state={'config':config,'matches':[],'status':'queued','archive_ready':False,'source_release':source}
    def write(_): (root/'results.json').write_text(json.dumps(state,indent=2))
    run_job({'root':root,'state':state,'cancel':threading.Event()},write)
    release=gh.json('/releases','POST',{'tag_name':'arena-diagnostic-'+uuid.uuid4().hex,'name':'Private crash diagnostic '+str(source),'draft':True})
    gh.put(release['id'],'diagnostic.zip',(root/'logs.zip').read_bytes(),'application/zip')
    gh.put(release['id'],'results.json',(root/'results.json').read_bytes(),'application/json')
    # Only public server function names and diagnostic categories enter Actions logs.
    report={'scenario':scenario,'source':source,'diagnostic_release':release['id'],'status':state['status'],'match_errors':[m.get('error') for m in state['matches']],'server_frames':[],'server_setup_errors':[],'team_loader_error':False,'team_intercept_error':False,'team_segfault':False}
    for p in (root/'logs').rglob('*.log'):
        text=p.read_text(errors='replace')
        if p.name=='server.log':
            for line in text.splitlines():
                if line.startswith('#'):
                    report['server_frames'].append(re.sub(r'\s*\(.*','',line)[:250])
                elif any(word in line.lower() for word in ('error','not found','no such','invalid','undefined','permission','unrecognized')):
                    report['server_setup_errors'].append(line[:500])
        else:
            report['team_loader_error'] |= 'error while loading shared libraries:' in text
            report['team_intercept_error'] |= 'no intercept evaluator' in text
            report['team_segfault'] |= 'Segmentation fault' in text
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__': main()
