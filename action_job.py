"""Run on GitHub-hosted Ubuntu only; publish per-match reports and final ZIP."""
import json,os,threading,time
from pathlib import Path
from github_api import storage_client,is_arena_release
from app import extract,validate
from runner import run_job,results_only
from replay import asset_name
from live import LivePublisher

class RemoteCancel:
    def __init__(self,gh,ident):self.gh=gh;self.ident=ident;self.next=0;self.value=False;self.lock=threading.Lock();self.polling=False
    def is_set(self):
        with self.lock:
            if not self.polling and time.monotonic()>self.next:
                self.next=time.monotonic()+30;self.polling=True
                threading.Thread(target=self.poll,daemon=True).start()
            return self.value
    def poll(self):
        try:
            value='cancel.json' in self.gh.assets(self.ident)
            with self.lock:self.value=self.value or value
        except Exception:pass
        finally:
            with self.lock:self.polling=False

def main():
    gh=storage_client();gh.require_private();ident=int(os.environ['RELEASE_ID']);rel=gh.release(ident)
    if not is_arena_release(rel):raise ValueError('Invalid release')
    assets=gh.assets(ident);config=validate(json.loads(gh.read_asset(assets['config.json'])))
    if config['rounds']*config['games_per_round']>500:raise ValueError('Maximum 500 matches')
    root=Path('job-data').resolve();root.mkdir(exist_ok=True)
    state={'id':str(ident),'status':'queued','demo':False,'server_version':'19.0.0','config':config,'matches':[],'total':config['rounds']*config['games_per_round'],'started_at':rel['created_at'],'archive_ready':False,'publication_pending':True}
    publisher=None
    if 'live.json' in assets:
        try:publisher=LivePublisher(json.loads(gh.read_asset(assets['live.json'])))
        except Exception:print('Direct live feed unavailable; periodic reports remain enabled.',flush=True)
    published_replays=set();published_build_logs=set()
    def write(job):
        for side,build in state.get('builds',{}).items():
            if side in published_build_logs or build.get('status') not in ('failed','completed','cancelled'):continue
            path=root/'logs'/('build-'+side+'.log')
            if path.is_file():
                try:
                    gh.put(ident,'build-'+side+'.log',path.read_bytes(),'text/plain; charset=utf-8')
                    published_build_logs.add(side);build['log_ready']=True
                except Exception:pass
        # Publish each finished game's replay before proceeding to the next game.
        for match in state['matches']:
            key=(match['round'],match['game'])
            if key in published_replays or not match.get('replay_available'):continue
            path=root/'logs'/f'round-{key[0]:03d}-game-{key[1]:03d}'/'replay.json.gz'
            try:
                gh.put(ident,asset_name(*key),path.read_bytes(),'application/gzip')
                published_replays.add(key);match['replay_ready']=True
            except Exception:
                print('Replay publication delayed; match results are retained.',flush=True)

        content=json.dumps(results_only(state),ensure_ascii=False,indent=2).encode();(root/'results.json').write_bytes(content)
        # Release metadata gives atomic live updates without deleting/re-uploading an asset.
        try:
            gh.json('/releases/'+str(ident),'PATCH',{'body':json.dumps({'arena_state':state},ensure_ascii=False)})
        except Exception:
            if not state.get('publication_pending'): raise
            print('Live report update delayed; the final report will be retried.',flush=True)
    try:
        for side in ('left','right'):
            dest=root/'teams'/side;extract(gh.read_asset(assets[side+'.zip']),dest)
            if config[side].get('input_mode','binary')=='binary' and not (dest/config[side]['directory']).is_dir():raise ValueError('Folder missing: '+side)
        job={'state':state,'root':root,'cancel':RemoteCancel(gh,ident),'live':publisher}
        # Prevent site secrets/token being inherited by player processes.
        for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_PASSWORD','ARENA_USER'):os.environ.pop(key,None)
        run_job(job,write)
        # bytes uploaded only after archive was closed.
        gh.put(ident,'logs.zip',(root/'logs.zip').read_bytes(),'application/zip')
        state.update(archive_ready=True,publication_pending=False)
        gh.put(ident,'results.json',json.dumps(results_only(state),ensure_ascii=False,indent=2).encode(),'application/json')
        write(job)
    except Exception as e:
        state.update(status='failed',error=str(e),publication_pending=False);write({'state':state})
        raise SystemExit('Match job failed; details are available inside the authenticated Arena portal.')
    finally:
        if publisher:publisher.close()
    if state['status']=='failed': raise SystemExit('Matches failed; the private Arena report contains the specific errors and logs.')
if __name__=='__main__':main()
