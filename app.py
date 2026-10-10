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
from runner import run_job,results_only

DATA=Path(os.environ.get('DATA_DIR','./data')).resolve(); DATA.mkdir(parents=True,exist_ok=True)
JOBS={}; LOCK=threading.RLock()

def write(job):
    with LOCK:
        p=job['root']/'results.json'; temp=p.with_suffix('.tmp'); temp.write_text(json.dumps(results_only(job['state']),ensure_ascii=False,indent=2),encoding='utf8'); temp.replace(p)

def recover():
    for p in DATA.glob('*/results.json'):
        try: state=json.loads(p.read_text());
        except (ValueError,OSError): continue
        if state.get('status') in ('queued','running'):
            state.update(status='failed',error='Service restarted: this test was interrupted. Start a new test.')
        job={'root':p.parent,'state':state,'cancel':threading.Event()}; JOBS[p.parent.name]=job; write(job)

def extract(blob,dest):
    dest=dest.resolve()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        infos=z.infolist()
        if len(infos)>20000: raise ValueError('ZIP has too many files')
        entries=[]; links={}; seen=set()
        for i in infos:
            name=i.filename
            if '\\' in name or name.startswith('/') or '..' in Path(name).parts or '\x00' in name: raise ValueError('Unsafe ZIP path')
            # The upper attribute bits describe Unix modes only for Unix ZIPs.
            mode=(i.external_attr>>16) if i.create_system==3 else 0
            target=dest/name
            if target==dest or target in seen: raise ValueError('Duplicate/empty ZIP path: '+name)
            seen.add(target)
            if not target.resolve().is_relative_to(dest): raise ValueError('Unsafe ZIP path')
            if stat.S_ISLNK(mode):
                if i.file_size>4096: raise ValueError('ZIP symlink target too long: '+name)
                link=z.read(i).decode('utf-8')
                if not link or '\x00' in link or '\\' in link or Path(link).is_absolute():
                    raise ValueError('Unsafe ZIP symlink: '+name)
                resolved=(target.parent/link).resolve()
                if not resolved.is_relative_to(dest): raise ValueError('ZIP symlink escapes team folder: '+name)
                links[target]=link
            elif stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise ValueError('ZIP special file is not supported: '+name)
            else: entries.append((i,target,mode))
        # Never write archive entries through a symlink from that archive.
        for target in seen:
            if any(parent in links for parent in target.parents):
                raise ValueError('ZIP path is inside a symlink: '+str(target.relative_to(dest)))
        for i,target,mode in entries:
            if i.is_dir() or stat.S_ISDIR(mode): target.mkdir(parents=True,exist_ok=True); continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(i) as src,open(target,'wb') as out: shutil.copyfileobj(src,out)
            # ZIP uploads often lose exec bits; grant owner execution for ELF/scripts.
            with target.open('rb') as f: head=f.read(4)
            target.chmod(0o700 if mode&0o111 or head.startswith((b'\x7fELF',b'#!')) or target.suffix=='.sh' else 0o600)
        # Resolve library link chains after all regular files have been extracted.
        pending=dict(links)
        while pending:
            progress=False
            for target,link in list(pending.items()):
                resolved=(target.parent/link).resolve()
                if not resolved.is_relative_to(dest): raise ValueError('ZIP symlink escapes team folder: '+str(target.relative_to(dest)))
                if resolved.exists():
                    target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists() or target.is_symlink(): raise ValueError('ZIP symlink conflicts with existing file: '+str(target.relative_to(dest)))
                    target.symlink_to(link); del pending[target]; progress=True
            if not progress: raise ValueError('ZIP symlink target missing or cyclic: '+str(next(iter(pending)).relative_to(dest)))
        # Another link can change the meaning of '..' in a previously made link.
        for target in links:
            resolved=target.resolve()
            if not resolved.is_relative_to(dest) or not resolved.exists():
                raise ValueError('Unsafe/missing ZIP symlink target: '+str(target.relative_to(dest)))

def validate(c):
    for key in ('rounds','games_per_round'):
        if type(c.get(key)) is not int or not 1<=c[key]<=500: raise ValueError('Invalid match counts')
    if c['rounds']*c['games_per_round']>500: raise ValueError('Maximum 500 matches')
    if type(c.get('synch_mode')) is not bool: raise ValueError('synch_mode must be boolean')
    if type(c.get('offline_logging',False)) is not bool: raise ValueError('offline_logging must be boolean')
    for side in ('left','right'):
        t=c.get(side,{})
        mode=t.get('input_mode','binary')
        if mode not in ('binary','source'):raise ValueError('Invalid team input mode')
        t['input_mode']=mode
        if mode=='source':
            if t.get('base') not in ('school','university'):raise ValueError('Choose school or university base')
            source=t.get('source_directory','')
            if not isinstance(source,str) or len(source)>500:raise ValueError('Invalid source directory')
            p=Path(source)
            if p.is_absolute() or '..' in p.parts or '\\' in source:raise ValueError('Source directory must be relative')
            t['directory']=t.get('directory') or '.'
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
        if path=='/healthz': self.send(200,{'ok':True,'version':'2026.10.05.2','commit':os.environ.get('RENDER_GIT_COMMIT','')}); return
        if not self.auth(): return
        if path in ('/','/index.html'):
            self.send(200,(Path(__file__).parent/'static/index.html').read_bytes(),'text/html; charset=utf-8'); return
        if path=='/api/tests':
            with LOCK: self.send(200,[{'id':k,'status':v['state']['status'],'total':v['state']['total'],'started_at':v['state']['started_at']} for k,v in JOBS.items()]); return
        build_match=re.fullmatch(r'/api/tests/([a-f0-9]{32})/build-log/(left|right)',path)
        if build_match:
            job=JOBS.get(build_match[1])
            log=job['root']/'logs'/('build-'+build_match[2]+'.log') if job else None
            if not log or not log.is_file():return self.send(404,{'error':'Build log is not available'})
            self.send(200,log.read_bytes(),'text/plain; charset=utf-8');return
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
            if length<=0: self.send(413,{'error':'Empty upload'}); return
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
                    if config[side].get('input_mode','binary')=='binary' and not (dest/config[side]['directory']).is_dir(): raise ValueError('Team folder not found: '+side)
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
