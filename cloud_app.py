"""Free Render control plane: no RCSS processes or permanent local uploads."""
import io,json,os,time,uuid,threading,urllib.error
from email.parser import BytesParser
from email.policy import default
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from app import Handler as BaseHandler,validate
from github_api import GitHub,storage_client,is_arena_release
from pathlib import Path
from presets import catalog,resolve_teams
LOCK=threading.Lock();CACHE={}

def state(gh,ident,workflow=None):
    workflow=workflow or gh
    now=time.monotonic()
    if ident in CACHE and now-CACHE[ident][0]<10:return CACHE[ident][1]
    rel=gh.release(ident)
    if not is_arena_release(rel):raise ValueError('Not an Arena test')
    assets=gh.assets(ident)
    try: metadata=json.loads(rel.get('body') or '{}')
    except (ValueError,TypeError): metadata={}
    live=metadata.get('arena_state')
    if isinstance(live,dict) and str(live.get('id'))==str(ident): s=live
    elif 'results.json' in assets:s=json.loads(gh.read_asset(assets['results.json']))
    else:
        config=json.loads(gh.read_asset(assets['config.json']))
        s={'id':str(ident),'status':'queued','total':config['rounds']*config['games_per_round'],'config':config,'matches':[],'started_at':rel['created_at'],'archive_ready':False}
    # If a runner fails before publishing, reflect that failure instead of waiting forever.
    if s['status'] in ('queued','running'):
        runs=workflow.json('/actions/workflows/matches.yml/runs?event=workflow_dispatch&per_page=100')['workflow_runs']
        run=next((r for r in runs if r.get('display_title')=='Arena '+str(ident)),None)
        if run:
            s['workflow_url']=run['html_url']
            if run['status']=='completed':
                s['status']='cancelled' if run['conclusion']=='cancelled' else 'failed'
                s['publication_pending']=False
                s['error']='Workflow finished without a completed report; inspect Actions logs.'
    s['archive_ready']='logs.zip' in assets
    CACHE[ident]=(now,s);return s

class Handler(BaseHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/','/index.html','/healthz'):return super().do_GET()
        if not self.auth():return
        try:
            if path=='/api/teams':
                return self.send(200,[{k:t[k] for k in ('id','name','directory','command','archive')} for t in catalog()])
            workflow=GitHub();gh=storage_client();gh.require_private()
            if path=='/api/tests':
                rels=gh.json('/releases?per_page=100');rows=[]
                for rel in rels:
                    if is_arena_release(rel):
                        rows.append({'id':str(rel['id']),'status':'unknown','started_at':rel['created_at']})
                return self.send(200,rows)
            import re
            m=re.fullmatch(r'/api/tests/(\d+)(/logs.zip)?',path)
            if not m:return self.send(404,{'error':'Not found'})
            ident=m[1]
            if not m[2]:return self.send(200,state(gh,ident,workflow))
            rel=gh.release(ident)
            if not is_arena_release(rel):raise ValueError('Not an Arena test')
            asset=gh.assets(ident).get('logs.zip')
            if not asset:return self.send(409,{'error':'ZIP is not ready'})
            # Stream archive instead of retaining it on Render or in RAM.
            with gh.open('/releases/assets/'+str(asset['id']),binary=True) as response:
                self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Length',str(asset['size']));self.send_header('Content-Disposition','attachment; filename="rcss-logs.zip"');self.end_headers()
                while True:
                    chunk=response.read(65536)
                    if not chunk:break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as e:self.send(502,{'error':'GitHub API: '+str(e.code)})
        except Exception as e:self.send(400,{'error':str(e)})
    def do_POST(self):
        if not self.auth():return
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,{'error':'Cross-origin request rejected'})
        path=urlparse(self.path).path
        try:
            import re
            workflow=GitHub();gh=storage_client();gh.require_private();m=re.fullmatch(r'/api/tests/(\d+)/cancel',path)
            if m:
                rel=gh.release(m[1])
                if not is_arena_release(rel):raise ValueError('Not an Arena test')
                # Graceful runner cancellation. If queued/building, takes effect when runner starts.
                gh.put(m[1],'cancel.json',b'{"cancel":true}','application/json');CACHE.pop(m[1],None)
                return self.send(202,{'status':'cancellation_requested'})
            if path!='/api/tests':return self.send(404,{'error':'Not found'})
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=32*1024**2:return self.send(413,{'error':'Maximum 32 MB for both teams combined in this free version'})
            ctype=self.headers.get('Content-Type','')
            if not ctype.startswith('multipart/form-data'):raise ValueError('Expected multipart upload')
            payload=self.rfile.read(length)
            msg=BytesParser(policy=default).parsebytes(('Content-Type: '+ctype+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+payload)
            fields={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in msg.iter_parts()}
            config=json.loads(fields['config'])
            teams=resolve_teams(config,fields)
            config=validate(config)
            if config['rounds']*config['games_per_round']>50:raise ValueError('Free version: maximum 50 matches per request')
            # Single Render instance; avoid concurrent requests while creating release.
            with LOCK:
                runs=workflow.json('/actions/workflows/matches.yml/runs?per_page=100')['workflow_runs']
                if any(r['status'] in ('queued','in_progress','waiting','pending','requested') for r in runs):return self.send(409,{'error':'A test is already active'})
                tag='arena-'+uuid.uuid4().hex
                rel=gh.json('/releases','POST',{'tag_name':tag,'name':tag,'draft':True})
                ident=rel['id']
                try:
                    for side in ('left','right'):gh.put(ident,side+'.zip',teams[side])
                    gh.put(ident,'config.json',json.dumps(config).encode(),'application/json')
                    workflow.json('/actions/workflows/matches.yml/dispatches','POST',{'ref':os.environ.get('GITHUB_REF','main'),'inputs':{'release_id':str(ident)}})
                except Exception:
                    gh.json('/releases/'+str(ident),'DELETE');raise
            self.send(202,{'id':str(ident)})
        except urllib.error.HTTPError as e:self.send(502,{'error':'GitHub API: '+str(e.code)+'; check token permissions and workflow on default branch'})
        except Exception as e:self.send(400,{'error':str(e)})

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
