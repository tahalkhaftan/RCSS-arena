"""Private single-user RCSS portal. Python standard library only."""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import signal
import stat
import threading
import time
import uuid
import zipfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from runner import run_job

DATA=Path(os.environ.get('DATA_DIR','./data')).resolve(); DATA.mkdir(parents=True,exist_ok=True)
JOBS={}; LOCK=threading.RLock(); UPLOAD_LIMIT=int(os.environ.get('MAX_UPLOAD_MB','256'))*1024**2

def write(job):
    with LOCK:
        p=job['root']/'results.json'; temp=p.with_suffix('.tmp'); temp.write_text(json.dumps(job['state'],ensure_ascii=False,indent=2),encoding='utf8'); temp.replace(p)

def recover():
    for p in DATA.glob('*/results.json'):
        try: state=json.loads(p.read_text());
        except (ValueError,OSError): continue
        if state.get('status') in ('queued','running'):
            state.update(status='failed',error='Service restarted: this test was interrupted. Start a new test.')
        job={'root':p.parent,'state':state,'cancel':threading.Event()}; JOBS[p.parent.name]=job; write(job)

def extract(blob,dest):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        infos=z.infolist()
        if len(infos)>20000 or sum(i.file_size for i in infos)>1024**3: raise ValueError('ZIP extracted size exceeds 1 GiB or too many files')
        for i in infos:
            name=i.filename
            if '\\' in name or name.startswith('/') or '..' in Path(name).parts or '\x00' in name: raise ValueError('Unsafe ZIP path')
            mode=i.external_attr>>16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)): raise ValueError('ZIP symlinks/special files are not supported')
            target=(dest/name).resolve()
            if not target.is_relative_to(dest.resolve()): raise ValueError('Unsafe ZIP path')
            if i.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as src,open(target,'wb') as out: shutil.copyfileobj(src,out)
            # ZIP uploads often lose exec bits; grant owner execution for ELF/scripts.
            with target.open('rb') as f: head=f.read(4)
            target.chmod(0o700 if head.startswith((b'\x7fELF',b'#!')) or target.suffix=='.sh' else 0o600)

def validate(c):
    for key in ('rounds','games_per_round'):
        if type(c.get(key)) is not int or not 1<=c[key]<=100: raise ValueError('Invalid match counts')
    if c['rounds']*c['games_per_round']>1000: raise ValueError('Maximum 1000 matches')
    if type(c.get('synch_mode')) is not bool: raise ValueError('synch_mode must be boolean')
    for side in ('left','right'):
        t=c.get(side,{})
        for key in ('name','directory','command'):
            if not isinstance(t.get(key),str) or not t[key].strip() or len(t[key])>500: raise ValueError('Missing/invalid team '+key)
        p=Path(t['directory'])
        if p.is_absolute() or '..' in p.parts or '\\' in str(p): raise ValueError('Team directory must be relative')
    return c

class Handler(BaseHTTPRequestHandler):
    server_version='RCSSArena/1.0'
    def log_message(self,*args): pass  # Do not log Authorization or uploaded data.
    def send(self,code,data=None,ctype='application/json'):
        body=json.dumps(data,ensure_ascii=False).encode() if ctype=='application/json' else data
        self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(body)
    def auth(self):
        user=os.environ.get('ARENA_USER'); password=os.environ.get('ARENA_PASSWORD')
        if not user or not password: self.send(503,{'error':'Configure ARENA_USER and ARENA_PASSWORD'}); return False
        expected='Basic '+base64.b64encode((user+':'+password).encode()).decode()
        if not hmac.compare_digest(self.headers.get('Authorization','').encode(),expected.encode()):
            self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="RCSS Arena", charset="UTF-8"'); self.send_header('Content-Length','0'); self.end_headers(); return False
        return True
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/healthz': self.send(200,{'ok':True}); return
        if not self.auth(): return
        if path in ('/','/index.html'):
            self.send(200,(Path(__file__).parent/'static/index.html').read_bytes(),'text/html; charset=utf-8'); return
        if path=='/api/tests':
            with LOCK: self.send(200,[{'id':k,'status':v['state']['status'],'total':v['state']['total'],'started_at':v['state']['started_at']} for k,v in JOBS.items()]); return
        m=re.fullmatch(r'/api/tests/([a-f0-9]{32})(/logs.zip)?',path)
        if not m or m[1] not in JOBS: self.send(404,{'error':'Not found'}); return
        job=JOBS[m[1]]
        if not m[2]:
            with LOCK: self.send(200,job['state'])
        else:
            p=job['root']/'logs.zip'
            if not p.exists(): self.send(409,{'error':'Archive is not ready'}); return
            self.send_response(200); self.send_header('Content-Type','application/zip'); self.send_header('Content-Length',str(p.stat().st_size)); self.send_header('Content-Disposition','attachment; filename="rcss-logs.zip"'); self.end_headers()
            with p.open('rb') as f: shutil.copyfileobj(f,self.wfile)
    def do_POST(self):
        if not self.auth(): return
        origin=self.headers.get('Origin')
        # No cross-site uploads/control. Serve UI and API from the same origin.
        if origin and urlparse(origin).netloc!=self.headers.get('Host'): self.send(403,{'error':'Cross-origin request rejected'}); return
        path=urlparse(self.path).path
        m=re.fullmatch(r'/api/tests/([a-f0-9]{32})/cancel',path)
        if m:
            if m[1] not in JOBS: self.send(404,{'error':'Not found'}); return
            JOBS[m[1]]['cancel'].set(); self.send(202,{'status':'cancellation_requested'}); return
        if path!='/api/tests': self.send(404,{'error':'Not found'}); return
        root=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=UPLOAD_LIMIT: self.send(413,{'error':'Upload exceeds limit'}); return
            ctype=self.headers.get('Content-Type','')
            if not ctype.startswith('multipart/form-data'): raise ValueError('Expected multipart upload')
            payload=self.rfile.read(length)
            msg=BytesParser(policy=default).parsebytes(('Content-Type: '+ctype+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+payload)
            fields={p.get_param('name',header='content-disposition'):p.get_payload(decode=True) for p in msg.iter_parts()}
            config=validate(json.loads(fields['config']))
            if any(not fields.get(side+'_file') for side in ('left','right')): raise ValueError('Both ZIP files required')
            with LOCK:
                if any(j['state']['status'] in ('queued','running') or not j['state'].get('archive_ready',False) and j.get('thread') and j['thread'].is_alive() for j in JOBS.values()):
                    self.send(409,{'error':'Another test is active'}); return
                if shutil.disk_usage(DATA).free<3*1024**3: self.send(507,{'error':'At least 3 GiB free disk required'}); return
                ident=uuid.uuid4().hex; root=DATA/ident; root.mkdir()
                for side in ('left','right'):
                    dest=root/'teams'/side; extract(fields[side+'_file'],dest)
                    if not (dest/config[side]['directory']).is_dir(): raise ValueError('Team folder not found: '+side)
                state={'id':ident,'demo':False,'status':'queued','server_version':'19.0.0','config':config,'total':config['rounds']*config['games_per_round'],'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'matches':[],'archive_ready':False}
                job={'state':state,'root':root,'cancel':threading.Event()}; JOBS[ident]=job; write(job)
                t=threading.Thread(target=run_job,args=(job,write),daemon=True); job['thread']=t;t.start()
            self.send(202,{'id':ident})
        except (ValueError,KeyError,zipfile.BadZipFile,UnicodeError) as exc:
            if root: shutil.rmtree(root,ignore_errors=True)
            self.send(400,{'error':str(exc)})
        except Exception:
            if root and root.name not in JOBS: shutil.rmtree(root,ignore_errors=True)
            self.send(500,{'error':'Internal error; check service logs'})

if __name__=='__main__':
    recover(); server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8000'))),Handler)
    def stop(*_):
        for j in JOBS.values(): j['cancel'].set()
        def close():
            for j in JOBS.values():
                if j.get('thread'): j['thread'].join(timeout=8)
            server.shutdown()
        threading.Thread(target=close,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    server.serve_forever()
