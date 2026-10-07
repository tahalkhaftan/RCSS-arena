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
from replay import asset_name,encode_replay
import tempfile,zipfile
from live import connection_info,valid_token,RELAY,VIEWERS
import re
LOCK=threading.Lock();CACHE={}
REPLAY_LOCK=threading.Lock();REPLAY_CACHE={}

def replay_data(gh,ident,round_number,game_number):
    key=(getattr(gh,'repo','storage'),str(ident),round_number,game_number)
    # Keep at most two compressed replays in the small Render instance.
    with REPLAY_LOCK:
        cached=REPLAY_CACHE.get(key)
        if cached and time.monotonic()-cached[0]<300:return cached[1]
        rel=gh.release(ident)
        if not is_arena_release(rel):raise ValueError('Not an Arena test')
        assets=gh.assets(ident);asset=assets.get(asset_name(round_number,game_number))
        if asset:
            if asset.get('size',0)>16*1024**2:raise ValueError('Replay asset is too large')
            blob=gh.read_asset(asset)
        else:
            archive=assets.get('logs.zip')
            if not archive:raise LookupError('بازپخش هنوز آماده نیست؛ پس از پایان بازی دوباره دریافت کن.')
            if archive.get('size',0)>64*1024**2:raise ValueError('برای این آرشیو قدیمی و بزرگ، ZIP لاگ‌ها را دانلود کن.')
            prefix=f'logs/round-{round_number:03d}-game-{game_number:03d}/'
            with tempfile.TemporaryFile() as temp:
                with gh.open('/releases/assets/'+str(archive['id']),binary=True) as response:
                    total=0
                    while True:
                        chunk=response.read(65536)
                        if not chunk:break
                        total+=len(chunk)
                        if total>64*1024**2:raise ValueError('Archive is too large')
                        temp.write(chunk)
                temp.seek(0)
                with zipfile.ZipFile(temp) as z:
                    replay=prefix+'replay.json.gz'
                    path=replay if replay in z.namelist() else prefix+'match.rcg'
                    if path not in z.namelist():raise LookupError('این بازی هنوز لاگ قابل نمایش ندارد.')
                    limit=16*1024**2 if path==replay else 128*1024**2
                    if z.getinfo(path).file_size>limit:raise ValueError('Replay log is too large')
                    with z.open(path) as stream:
                        blob=stream.read() if path==replay else encode_replay(io.TextIOWrapper(stream,encoding='utf-8'))
        if len(blob)>16*1024**2:raise ValueError('Replay is too large')
        if len(REPLAY_CACHE)>=2:REPLAY_CACHE.pop(next(iter(REPLAY_CACHE)))
        REPLAY_CACHE[key]=(time.monotonic(),blob)
        return blob


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
            live_match=re.fullmatch(r'/api/tests/(\d+)/live',path)
            if live_match:return self.stream_live(live_match[1])
            if path=='/api/teams':
                return self.send(200,[{k:t[k] for k in ('id','name','directory','command','archive')} for t in catalog()])
            workflow=GitHub();gh=storage_client();gh.require_private()
            if path=='/api/tests':
                rels=gh.json('/releases?per_page=100');rows=[]
                for rel in rels:
                    if is_arena_release(rel):
                        rows.append({'id':str(rel['id']),'status':'unknown','started_at':rel['created_at']})
                return self.send(200,rows)
            replay_match=re.fullmatch(r'/api/tests/(\d+)/replay/(\d+)/(\d+)',path)
            if replay_match:
                ident,r,g=map(int,replay_match.groups())
                if not 1<=r<=100 or not 1<=g<=100:raise ValueError('Invalid round/game')
                try:blob=replay_data(gh,ident,r,g)
                except LookupError as exc:return self.send(409,{'error':str(exc)})
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Encoding','gzip')
                self.send_header('Content-Length',str(len(blob)))
                self.send_header('Cache-Control','no-store')
                self.end_headers();self.wfile.write(blob);return
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
    def stream_live(self,ident):
        if not VIEWERS.acquire(blocking=False):return self.send(503,{'error':'Too many live viewers'})
        try:
            self.connection.settimeout(15)
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Cache-Control','no-cache, no-transform')
            self.send_header('X-Accel-Buffering','no')
            self.end_headers();self.wfile.write(b'retry: 1000\n\n');self.wfile.flush()
            sequence=0;deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                sequence,payload=RELAY.wait(ident,sequence)
                message=('data: '+json.dumps(payload,separators=(',',':'))+'\n\n').encode() if payload else b': keepalive\n\n'
                self.wfile.write(message);self.wfile.flush()
        except (OSError,TimeoutError):pass
        finally:VIEWERS.release();self.close_connection=True

    def do_POST(self):
        path=urlparse(self.path).path
        live_match=re.fullmatch(r'/api/live/(\d+)',path)
        if live_match:
            ident=live_match[1];header=self.headers.get('Authorization','')
            if not header.startswith('Bearer ') or not valid_token(ident,header[7:]):return self.send(403,{'error':'Invalid live token'})
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=65536:return self.send(413,{'error':'Live batch too large'})
                self.connection.settimeout(5)
                RELAY.publish(ident,json.loads(self.rfile.read(length)))
                return self.send(200,{'ok':True})
            except (ValueError,TypeError,KeyError,OSError):return self.send(400,{'error':'Invalid live batch'})
        if not self.auth():return
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,{'error':'Cross-origin request rejected'})
        path=urlparse(self.path).path
        try:
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
                    connection=connection_info(ident)
                    if connection:gh.put(ident,'live.json',json.dumps(connection).encode(),'application/json')
                    workflow.json('/actions/workflows/matches.yml/dispatches','POST',{'ref':os.environ.get('GITHUB_REF','main'),'inputs':{'release_id':str(ident)}})
                except Exception:
                    gh.json('/releases/'+str(ident),'DELETE');raise
            self.send(202,{'id':str(ident)})
        except urllib.error.HTTPError as e:self.send(502,{'error':'GitHub API: '+str(e.code)+'; check token permissions and workflow on default branch'})
        except Exception as e:self.send(400,{'error':str(e)})

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8000'))),Handler).serve_forever()
