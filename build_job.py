"""Build an uploaded source team once and publish a reusable binary privately."""
import hashlib,json,os,threading
from pathlib import Path
from app import extract
from github_api import storage_client
from build_store import build_state,pack_compiled
from team_build import build_team

def main():
    gh=storage_client();gh.require_private();ident=int(os.environ['RELEASE_ID'])
    state=build_state(gh,ident);assets=gh.assets(ident)
    root=Path('build-data').resolve();root.mkdir(exist_ok=True);log=root/'build.log'
    def publish():gh.json('/releases/'+str(ident),'PATCH',{'body':json.dumps({'build_state':state},ensure_ascii=False)})
    def stage(value):state.update(status='building',stage=value);publish()
    try:
        state.update(status='building',stage='Extract source ZIP');publish()
        blob=gh.read_asset(assets['source.zip']);state['source_sha256']=hashlib.sha256(blob).hexdigest()
        extract(blob,root/'team');team=dict(state['signature'])
        for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_PASSWORD','ARENA_USER'):os.environ.pop(key,None)
        result=build_team(team,root/'team',log,threading.Event(),stage)
        stage('Package compiled team');compiled=pack_compiled(team,root/'team')
        gh.put(ident,'compiled.zip',compiled,'application/zip')
        state.update(status='completed',stage='Build completed',directory=result['directory'],compiled_sha256=hashlib.sha256(compiled).hexdigest())
    except Exception as error:
        state.update(status='failed',error=str(error))
        if not log.exists():log.write_text(str(error),encoding='utf-8')
    finally:
        if log.exists():
            try:gh.put(ident,'build.log',log.read_bytes(),'text/plain; charset=utf-8');state['log_ready']=True
            except Exception:state['log_ready']=False
        publish()
    if state['status']!='completed':raise SystemExit('Team build failed; full terminal output is in the private build log.')

if __name__=='__main__':main()
