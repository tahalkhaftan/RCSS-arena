"""Ubuntu outbound worker: local matches/builds/storage, remote UI, no inbound ports."""
import argparse,base64,collections,concurrent.futures,fcntl,gzip,http.client,io,json,os,shutil,socket,tempfile,threading,time,uuid,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse
from live import NoRedirect

class WorkerClient:
    def __init__(self,site,token):
        u=urlparse(site)
        if (u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost'))) or u.username or u.password or u.query or u.fragment:raise ValueError('Use your HTTPS Arena address')
        self.site=site.rstrip('/');self.token=token;self.opener=urllib.request.build_opener(NoRedirect())
    def request(self,path,data=None,ctype='application/json',extra=None):
        headers={'Authorization':'Bearer '+self.token}
        if data is not None:headers['Content-Type']=ctype
        headers.update(extra or {})
        return self.opener.open(urllib.request.Request(self.site+'/api/personal/worker/'+path,data=data,headers=headers),timeout=20)
    def json(self,path,data):
        with self.request(path,json.dumps(data,separators=(',',':')).encode()) as f:return json.load(f)
    def serve_call(self,task,port,authorization):
        ident=task['id'];started=False
        try:
            with tempfile.TemporaryFile() as body:
                offset=0
                while offset<task['length']:
                    with self.request(ident+'/request?offset='+str(offset)) as f:chunk=f.read()
                    if not chunk:raise ValueError('Incomplete request from site')
                    body.write(chunk);offset+=len(chunk)
                body.seek(0);conn=http.client.HTTPConnection('127.0.0.1',port,timeout=180)
                try:
                    conn.putrequest(task['method'],task['path']);conn.putheader('Authorization',authorization)
                    conn.putheader('Content-Length',str(task['length']));conn.putheader('Content-Type',task['content_type']);conn.endheaders()
                    while True:
                        chunk=body.read(1024*1024)
                        if not chunk:break
                        conn.send(chunk)
                    response=conn.getresponse()
                    self.json(ident+'/response',{'status':response.status,'headers':dict(response.getheaders())});started=True;offset=0
                    while True:
                        chunk=response.read(1024*1024)
                        if not chunk:break
                        with self.request(ident+'/chunk',chunk,'application/octet-stream',{'X-Offset':str(offset)}) as f:f.read()
                        offset+=len(chunk)
                finally:conn.close()
        except Exception:
            if not started:
                try:
                    blob=b'{"error":"Ubuntu worker request failed; inspect the local terminal"}'
                    self.json(ident+'/response',{'status':502,'headers':{'Content-Type':'application/json','Content-Length':str(len(blob))}})
                    with self.request(ident+'/chunk',blob,'application/octet-stream',{'X-Offset':'0'}) as f:f.read()
                except Exception:pass
            print('A site request could not be completed; local matches continue.',flush=True)
        finally:
            try:self.json(ident+'/end',{})
            except Exception:pass

class PersonalLive:
    def __init__(self,client,ident):
        from native_tunnel import NativeTunnel
        self.native=NativeTunnel(lambda body:client.json('native/'+str(ident),body))
        self.client=client;self.ident=ident;self.queue=collections.deque(maxlen=12);self.lock=threading.Lock();self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def submit(self,r,g,frame):
        with self.lock:self.queue.append({'round':r,'game':g,'frame':frame,'captured_at':time.time()})
    def run(self):
        while not self.stop.wait(.15):
            with self.lock:batch=list(self.queue);self.queue.clear()
            if batch:
                try:
                    while len(json.dumps({'id':self.ident,'frames':batch}).encode())>65536 and len(batch)>1:batch.pop(0)
                    self.client.json('live',{'id':self.ident,'frames':batch})
                except Exception:pass
    def close(self):self.stop.set();self.native.close()


def local_handler(data_dir):
    import app,re
    from email.parser import BytesParser
    from email.policy import default
    from presets import catalog,resolve_teams
    from build_store import build_signature,pack_compiled
    from team_build import build_team
    from replay import encode_replay
    builds=data_dir/'builds';builds.mkdir(exist_ok=True);build_lock=threading.Lock()
    for p in builds.glob('*/state.json'):
        state=json.loads(p.read_text())
        if state.get('status') in ('queued','building'):
            state.update(status='failed',error='Worker restarted during build; rebuild this source');p.write_text(json.dumps(state))
    cancels=[]
    class LocalHandler(app.Handler):
        build_cancels=cancels
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/api/teams':
                if self.auth():self.send(200,[{k:t[k] for k in ('id','name','directory','command','archive')} for t in catalog()])
                return
            m=re.fullmatch(r'/api/builds/([a-f0-9]{32})(/log)?',path)
            if m:
                if not self.auth():return
                root=builds/m[1]
                if not (root/'state.json').exists():return self.send(404,{'error':'Local build not found'})
                if m[2]:
                    p=root/'build.log'
                    return self.send(200,p.read_bytes() if p.exists() else b'','text/plain; charset=utf-8')
                return self.send(200,json.loads((root/'state.json').read_text()))
            raw_match=re.fullmatch(r'/api/tests/([a-f0-9]{32})/rcg/(\d+)/(\d+)',path)
            if raw_match:
                if not self.auth():return
                ident,r,g=raw_match.groups();r,g=int(r),int(g);job=app.JOBS.get(ident)
                if not job or not 1<=r<=500 or not 1<=g<=500:return self.send(404,{'error':'Local game not found'})
                from native_assets import local_rcg
                try:p=local_rcg(job,r,g)
                except LookupError as exc:return self.send(409,{'error':str(exc)})
                self.send_response(200);self.send_header('Content-Type','application/x-rcg')
                if p.suffix!='.gz':self.send_header('Content-Length',str(p.stat().st_size))
                self.end_headers()
                with (gzip.open(p,'rb') if p.suffix=='.gz' else p.open('rb')) as stream:shutil.copyfileobj(stream,self.wfile)
                return
            m=re.fullmatch(r'/api/tests/([a-f0-9]{32})/replay/(\d+)/(\d+)',path)
            if m:
                if not self.auth():return
                job=app.JOBS.get(m[1]);r,g=map(int,m.groups()[1:])
                if not job or not 1<=r<=500 or not 1<=g<=500:return self.send(404,{'error':'Local replay not found'})
                p=job['root']/'logs'/f'round-{r:03d}-game-{g:03d}'/'replay.json.gz'
                if not p.exists():return self.send(409,{'error':'Replay is not ready'})
                blob=p.read_bytes();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Encoding','gzip');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob);return
            return super().do_GET()
        def do_POST(self):
            path=urlparse(self.path).path
            if path not in ('/api/tests','/api/builds'):return super().do_POST()
            if not self.auth():return
            try:
                length=int(self.headers.get('Content-Length','0'));ctype=self.headers.get('Content-Type','')
                if length<=0 or not ctype.startswith('multipart/form-data'):raise ValueError('Expected multipart upload')
                raw=self.rfile.read(length)
                msg=BytesParser(policy=default).parsebytes(('Content-Type: '+ctype+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                fields={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in msg.iter_parts()}
                config=json.loads(fields['config'])
                if path=='/api/builds':
                    team=config['team'];app.validate({'rounds':1,'games_per_round':1,'synch_mode':True,'left':team,'right':dict(team)})
                    if team.get('input_mode')!='source':raise ValueError('Source build required')
                    ident=uuid.uuid4().hex;root=builds/ident;root.mkdir()
                    app.extract(fields['source_file'],root/'team');signature=build_signature(team)
                    state={'id':ident,'status':'queued','stage':'Queued on Ubuntu','signature':signature}
                    def save():
                        tmp=root/'state.tmp';tmp.write_text(json.dumps(state));tmp.replace(root/'state.json')
                    cancel=threading.Event();cancels.append(cancel)
                    def build():
                        try:
                            def stage(value):state.update(status='building',stage=value);save()
                            with build_lock:result=build_team(team,root/'team',root/'build.log',cancel,stage)
                            (root/'compiled.zip').write_bytes(pack_compiled(team,root/'team'))
                            state.update(status='completed',stage='Build completed on Ubuntu')
                        except Exception as e:state.update(status='failed',error=str(e))
                        finally:save()
                    save();threading.Thread(target=build,daemon=True).start();return self.send(202,{'id':ident})
                app.validate(config)
                for side in ('left','right'):
                    t=config[side]
                    if t.get('input_mode')=='source':
                        ident=str(t.get('build_id',''))
                        if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Build this source on the selected Ubuntu worker first')
                        root=builds/ident;s=json.loads((root/'state.json').read_text())
                        if s['status']!='completed' or s['signature']!=build_signature(t):raise ValueError('Local source build is not ready or settings changed')
                        fields[side+'_file']=(root/'compiled.zip').read_bytes();config[side]=dict(t,input_mode='binary',directory='bin',preset_id='')
                prepared=resolve_teams(config,fields);fields.update({side+'_file':blob for side,blob in prepared.items()})
                fields['config']=json.dumps(config).encode();boundary=uuid.uuid4().hex
                blob=b''.join(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+k+'"\r\n\r\n').encode()+v+b'\r\n' for k,v in fields.items())+('--'+boundary+'--\r\n').encode()
                self.rfile=io.BytesIO(blob);self.headers.replace_header('Content-Length',str(len(blob)));self.headers.replace_header('Content-Type','multipart/form-data; boundary='+boundary)
                return super().do_POST()
            except Exception as e:return self.send(400,{'error':str(e)})
    return LocalHandler


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site');parser.add_argument('--token');parser.add_argument('--data-dir',default=str(Path.home()/'RCSS-arena-data'));parser.add_argument('--server')
    args=parser.parse_args();data=Path(args.data_dir).expanduser().resolve();data.mkdir(parents=True,exist_ok=True)
    lock=(data/'worker.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:parser.error('A worker already uses this data directory')
    settings_path=data/'worker-settings.json'
    saved=json.loads(settings_path.read_text()) if settings_path.exists() else {}
    settings={'site':args.site or saved.get('site'),'token':args.token or saved.get('token'),'machine_id':saved.get('machine_id',uuid.uuid4().hex)}
    if not settings['site'] or not settings['token']:parser.error('First run needs --site and --token from the Arena site')
    client=WorkerClient(settings['site'],settings['token']);settings_path.touch(mode=0o600);settings_path.chmod(0o600);settings_path.write_text(json.dumps(settings))
    install=Path(__file__).resolve().parent/'server-install'
    server=args.server or (str(install/'bin/rcssserver') if (install/'bin/rcssserver').exists() else shutil.which('rcssserver'))
    if not server or not Path(server).is_file():parser.error('RCSSServer not found; run bash scripts/setup_personal_worker.sh')
    os.environ.update(DATA_DIR=str(data/'matches'),RCSSSERVER=server,ARENA_USER='local-worker',ARENA_PASSWORD=uuid.uuid4().hex)
    os.environ['LD_LIBRARY_PATH']=str(install/'lib')+':'+os.environ.get('LD_LIBRARY_PATH','')
    import app
    from runner import run_job
    app.recover()
    def run_personal(job,write):
        live=PersonalLive(client,job['state']['id']);job['live']=live;job['state']['execution']='personal';job['state']['storage_directory']=str(job['root'])
        try:run_job(job,write)
        finally:live.close()
    app.run_job=run_personal
    local=ThreadingHTTPServer(('127.0.0.1',0),local_handler(data));threading.Thread(target=local.serve_forever,daemon=True).start()
    auth='Basic '+base64.b64encode(('local-worker:'+os.environ['ARENA_PASSWORD']).encode()).decode()
    info={'machine_id':settings['machine_id'],'name':socket.gethostname(),'data_dir':str(data)}
    print('Local files: '+str(data)+'\nMonitor: 127.0.0.1:6000\nConnecting to Arena…',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        try:
            while True:
                try:
                    client.json('heartbeat',info);task=client.json('poll',{'machine_id':settings['machine_id']})
                    if task:pool.submit(client.serve_call,task,local.server_port,auth)
                except Exception:
                    print('Site connection unavailable; retrying. Local matches and files remain on Ubuntu.',flush=True);time.sleep(5)
        except KeyboardInterrupt:
            print('Stopping worker and local matches…',flush=True)
            for event in local.RequestHandlerClass.build_cancels:event.set()
            for j in app.JOBS.values():j['cancel'].set()
            for j in app.JOBS.values():
                if j.get('thread'):j['thread'].join(timeout=8)
        finally:local.shutdown();local.server_close()
if __name__=='__main__':main()
