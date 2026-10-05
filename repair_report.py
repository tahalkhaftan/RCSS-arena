"""Reanalyze an existing real match; retain its replay and audit previous results."""
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from analysis import analyze, summary
from github_api import storage_client

gh=storage_client();gh.require_private();ident=int(os.environ['RELEASE_ID'])
assets=gh.assets(ident)
original=gh.read_asset(assets['results.json'])
state=json.loads(original)
blob=gh.read_asset(assets['logs.zip'])
with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(io.BytesIO(blob)) as archive:
    for match in state['matches']:
        prefix=f"logs/round-{match['round']:03d}-game-{match['game']:03d}/"
        # Do not relabel server crashes or incomplete games as completed.
        if match.get('error')!='Invalid record': continue
        server_log=archive.read(prefix+'server.log').decode(errors='replace')
        if 'Game Over. Exiting...' not in server_log: raise ValueError('No normal server exit')
        log=Path(temp)/'match.rcg';log.write_bytes(archive.read(prefix+'match.rcg'))
        parsed=analyze(log)
        if not parsed['natural_end'] or parsed['scores'] is None or min(parsed['max_players'].values())<11:
            raise ValueError('Original match did not finish with complete teams')
        if prefix+'match.rcl' not in archive.namelist(): raise ValueError('Missing RCL')
        match.update(status='completed',left_score=parsed['scores'][0],right_score=parsed['scores'][1],
                     server_team_names=parsed['team_names'],last_cycle=parsed['last_cycle'],possession=parsed['possession'])
        match.pop('error',None)
    state['summary']=summary(state['matches'])
    state['status']='failed' if state['summary']['failed'] else 'completed'
    if state['status']=='completed': state.pop('error',None)
    state.update(archive_ready=True,publication_pending=False,result_reprocessed=True)
    content=json.dumps(state,ensure_ascii=False,indent=2).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as new:
        for info in archive.infolist():
            if info.filename=='results.json': continue
            new.writestr(info,archive.read(info))
        new.writestr('results-before-repair.json',original)
        new.writestr('results.json',content)
gh.put(ident,'logs.zip',out.getvalue(),'application/zip')
gh.put(ident,'results.json',content,'application/json')
gh.json('/releases/'+str(ident),'PATCH',{'body':json.dumps({'arena_state':state},ensure_ascii=False)})
print('Original real replay reanalyzed and results retained privately. No synthetic scores used.')
