"""Run on GitHub-hosted Ubuntu only; publish per-match reports and final ZIP."""
import json,os,threading,time
from pathlib import Path
from github_api import storage_client
from app import extract,validate
from runner import run_job

class RemoteCancel:
    def __init__(self,gh,ident):self.gh=gh;self.ident=ident;self.next=0;self.value=False
    def is_set(self):
        if time.monotonic()>self.next:
            self.next=time.monotonic()+30
            try:self.value='cancel.json' in self.gh.assets(self.ident)
            except Exception:pass
        return self.value

def main():
    gh=storage_client();gh.require_private();ident=int(os.environ['RELEASE_ID']);rel=gh.release(ident)
    if not rel['tag_name'].startswith('arena-'):raise ValueError('Invalid release')
    assets=gh.assets(ident);config=validate(json.loads(gh.read_asset(assets['config.json'])))
    if config['rounds']*config['games_per_round']>50:raise ValueError('Maximum 50 matches')
    root=Path('job-data').resolve();root.mkdir(exist_ok=True)
    state={'id':str(ident),'status':'queued','demo':False,'server_version':'19.0.0','config':config,'matches':[],'total':config['rounds']*config['games_per_round'],'started_at':rel['created_at'],'archive_ready':False}
    def write(job):
        content=json.dumps(state,ensure_ascii=False,indent=2).encode();(root/'results.json').write_bytes(content)
        gh.put(ident,'results.json',content,'application/json')
    try:
        for side in ('left','right'):
            dest=root/'teams'/side;extract(gh.read_asset(assets[side+'.zip']),dest)
            if not (dest/config[side]['directory']).is_dir():raise ValueError('Folder missing: '+side)
        job={'state':state,'root':root,'cancel':RemoteCancel(gh,ident)}
        # Prevent site secrets/token being inherited by player processes.
        for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_PASSWORD','ARENA_USER'):os.environ.pop(key,None)
        run_job(job,write)
        # bytes uploaded only after archive was closed.
        gh.put(ident,'logs.zip',(root/'logs.zip').read_bytes(),'application/zip');state['archive_ready']=True;write(job)
    except Exception as e:
        state.update(status='failed',error=str(e));write({'state':state})
        raise SystemExit('Match job failed; details are available inside the authenticated Arena portal.')
if __name__=='__main__':main()
