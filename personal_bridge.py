"""Outbound Ubuntu worker bridge. Payloads are temporary streams, never GitHub assets."""
import collections,hashlib,hmac,json,os,re,tempfile,threading,time,uuid
from urllib.parse import urlparse,parse_qs
CHUNK=1024*1024
ALLOWED=re.compile(r'/api/(?:teams|tests(?:/[a-f0-9]{32}(?:/cancel|/logs\.zip|/build-log/(?:left|right)|/replay/\d+/\d+)?)?|builds(?:/[a-f0-9]{32}(?:/log)?)?)$')


def worker_token():
    return hmac.new(os.environ['ARENA_PASSWORD'].encode(),b'rcss-personal-worker-v1',hashlib.sha256).hexdigest()


class Call:
    def __init__(self,method,path,ctype,length):
        self.id=uuid.uuid4().hex;self.method=method;self.path=path;self.ctype=ctype;self.length=length
        self.request=tempfile.TemporaryFile();self.response=tempfile.TemporaryFile()
        self.condition=threading.Condition();self.headers=None;self.size=0;self.done=False;self.closed=False
    def close(self):
        with self.condition:
            self.closed=True;self.condition.notify_all();self.request.close();self.response.close()


class Bridge:
    def __init__(self):
        self.condition=threading.Condition();self.calls={};self.queue=collections.deque();self.worker=None;self.seen=0
    def online(self):return self.worker is not None and time.monotonic()-self.seen<30
    def heartbeat(self,info):
        if not isinstance(info,dict) or not re.fullmatch('[a-f0-9]{32}',str(info.get('machine_id',''))):raise ValueError('Invalid worker identity')
        with self.condition:
            if self.online() and self.worker['machine_id']!=info['machine_id']:raise ValueError('Another Ubuntu worker is connected')
            self.worker={k:str(info.get(k,''))[:500] for k in ('machine_id','name','data_dir')};self.seen=time.monotonic()
    def status(self):
        with self.condition:return dict(online=self.online(),worker=self.worker if self.online() else None)
    def claim(self,machine_id):
        with self.condition:
            if not self.online() or self.worker['machine_id']!=machine_id:raise ValueError('Register this worker first')
            self.seen=time.monotonic();self.condition.wait_for(lambda:bool(self.queue),10)
            while self.queue:
                c=self.calls.get(self.queue.popleft())
                if c and not c.closed:return {'id':c.id,'method':c.method,'path':c.path,'content_type':c.ctype,'length':c.length}
            return None
    def call(self,ident):
        with self.condition:
            c=self.calls.get(ident)
            if not c or c.closed:raise ValueError('Request expired')
            return c
    def enqueue(self,c):
        with self.condition:
            if not self.online():raise ConnectionError('Ubuntu Worker متصل نیست؛ برنامهٔ Worker را روی Ubuntu اجرا کن.')
            if len(self.calls)>=12:raise ConnectionError('Personal worker is busy; retry shortly')
            self.calls[c.id]=c;self.queue.append(c.id);self.condition.notify_all()

BRIDGE=Bridge()


def json_body(handler,maximum=65536):
    size=int(handler.headers.get('Content-Length','0'))
    if not 0<size<=maximum:raise ValueError('Invalid request size')
    return json.loads(handler.rfile.read(size))


def handle_worker(handler):
    """True means this path was handled, including authentication rejection."""
    url=urlparse(handler.path);path=url.path
    if not path.startswith('/api/personal/worker/'):return False
    auth=handler.headers.get('Authorization','')
    if not auth.startswith('Bearer ') or not hmac.compare_digest(auth[7:],worker_token()):
        handler.send(403,{'error':'Invalid worker token'});return True
    try:
        if path.endswith('/heartbeat') and handler.command=='POST':
            BRIDGE.heartbeat(json_body(handler));handler.send(200,{'ok':True});return True
        if path.endswith('/poll') and handler.command=='POST':
            info=json_body(handler);handler.send(200,BRIDGE.claim(info.get('machine_id')));return True
        if path.endswith('/live') and handler.command=='POST':
            from live import RELAY
            info=json_body(handler);ident=str(info.get('id',''))
            if not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Invalid test')
            RELAY.publish('personal:'+ident,{'frames':info['frames']});handler.send(200,{'ok':True});return True
        m=re.fullmatch(r'/api/personal/worker/([a-f0-9]{32})/(request|response|chunk|end)',path)
        if not m:handler.send(404,{'error':'Not found'});return True
        c=BRIDGE.call(m[1]);kind=m[2]
        if kind=='request' and handler.command=='GET':
            offset=int(parse_qs(url.query).get('offset',['0'])[0])
            if offset<0 or offset>c.length:raise ValueError('Invalid offset')
            with c.condition:c.request.seek(offset);blob=c.request.read(CHUNK)
            handler.send(200,blob,'application/octet-stream')
        elif kind=='response' and handler.command=='POST':
            info=json_body(handler)
            if type(info.get('status')) is not int or not 100<=info['status']<=599:raise ValueError('Invalid response')
            headers={k:str(v) for k,v in info.get('headers',{}).items() if k.lower() in ('content-type','content-length','content-encoding','content-disposition')}
            if any('\n' in v or '\r' in v for v in headers.values()):raise ValueError('Invalid header')
            with c.condition:c.headers=(info['status'],headers);c.condition.notify_all()
            handler.send(200,{'ok':True})
        elif kind=='chunk' and handler.command=='POST':
            length=int(handler.headers.get('Content-Length','0'));offset=int(handler.headers.get('X-Offset','-1'))
            if not 0<length<=CHUNK:raise ValueError('Invalid chunk')
            blob=handler.rfile.read(length)
            with c.condition:
                if c.closed or offset!=c.size or len(blob)!=length:raise ValueError('Invalid stream offset')
                c.response.seek(c.size);c.response.write(blob);c.size+=length;c.condition.notify_all()
            handler.send(200,{'ok':True})
        elif kind=='end' and handler.command=='POST':
            with c.condition:c.done=True;c.condition.notify_all()
            handler.send(200,{'ok':True})
        else:handler.send(405,{'error':'Method not allowed'})
    except (ValueError,KeyError,TypeError,OSError) as e:handler.send(400,{'error':str(e)})
    return True


def proxy(handler,path):
    if not ALLOWED.fullmatch(path):return handler.send(404,{'error':'Not found'})
    if not BRIDGE.online():return handler.send(503,{'error':'Ubuntu Worker متصل نیست؛ برنامهٔ Worker را روی Ubuntu اجرا کن.'})
    try:
        length=int(handler.headers.get('Content-Length','0'))
        if length<0:raise ValueError('Invalid request length')
    except ValueError:return handler.send(400,{'error':'Invalid request length'})
    c=Call(handler.command,path,handler.headers.get('Content-Type',''),length)
    started=False
    try:
        remaining=c.length;handler.connection.settimeout(120)
        while remaining:
            blob=handler.rfile.read(min(CHUNK,remaining))
            if not blob:raise ValueError('Incomplete upload')
            c.request.write(blob);remaining-=len(blob)
        c.request.flush();BRIDGE.enqueue(c)
        with c.condition:
            if not c.condition.wait_for(lambda:c.headers is not None or c.closed,180) or c.closed:raise ConnectionError('Personal worker did not respond; local tests may still be running')
            status,headers=c.headers
        handler.send_response(status)
        for k,v in headers.items():handler.send_header(k,v)
        handler.send_header('Cache-Control','no-store');handler.end_headers();started=True
        offset=0
        while True:
            with c.condition:
                if not c.condition.wait_for(lambda:c.size>offset or c.done or c.closed,120):raise ConnectionError('Personal download stalled')
                if c.closed:break
                c.response.seek(offset);blob=c.response.read(min(CHUNK,c.size-offset))
                if not blob and c.done:break
            if blob:handler.wfile.write(blob);handler.wfile.flush();offset+=len(blob)
    except (OSError,ValueError) as e:
        if not started:handler.send(503,{'error':str(e)})
        else:handler.close_connection=True
    finally:
        with BRIDGE.condition:BRIDGE.calls.pop(c.id,None)
        c.close()
