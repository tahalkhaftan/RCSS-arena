"""Bounded, authenticated, best-effort live telemetry. Never blocks RCSS."""
import collections,hashlib,hmac,json,os,re,threading,time,urllib.request
from urllib.parse import urlparse


def issue_token(ident,expiry=None):
    expiry=int(expiry or time.time()+86400)
    message=f'{int(ident)}:{expiry}'
    signature=hmac.new(os.environ['ARENA_PASSWORD'].encode(),message.encode(),hashlib.sha256).hexdigest()
    return str(expiry)+'.'+signature


def valid_token(ident,token):
    try:
        expiry=int(token.split('.')[0])
        return time.time()<expiry<=time.time()+86401 and hmac.compare_digest(issue_token(ident,expiry),token)
    except (ValueError,KeyError,IndexError):return False


def connection_info(ident):
    base=os.environ.get('ARENA_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL')
    if not base:return None
    parsed=urlparse(base)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:return None
    return {'url':base.rstrip('/')+'/api/live/'+str(int(ident)), 'token':issue_token(ident)}


class Relay:
    def __init__(self):self.condition=threading.Condition();self.events={};self.counter=0
    def publish(self,ident,payload):
        if not isinstance(payload,dict):raise ValueError('Invalid payload')
        frames=payload.get('frames')
        if not isinstance(frames,list) or not 1<=len(frames)<=12:raise ValueError('Invalid frame batch')
        for f in frames:
            if not isinstance(f,dict):raise ValueError('Invalid frame')
            if not all(type(f.get(k)) is int and 1<=f[k]<=100 for k in ('round','game')):raise ValueError('Invalid game')
            if not isinstance(f.get('frame'),dict) or not isinstance(f['frame'].get('players'),list) or len(f['frame']['players'])>22:raise ValueError('Invalid frame')
        with self.condition:
            self.counter+=1;now=time.monotonic()
            for key in list(self.events):
                if now-self.events[key][2]>600:del self.events[key]
            if ident not in self.events and len(self.events)>=16:self.events.pop(next(iter(self.events)))
            self.events[ident]=(self.counter,payload,now);self.condition.notify_all()
    def wait(self,ident,sequence,timeout=10):
        with self.condition:
            self.condition.wait_for(lambda:ident in self.events and self.events[ident][0]!=sequence and time.monotonic()-self.events[ident][2]<15,timeout)
            entry=self.events.get(ident)
            if entry and time.monotonic()-entry[2]<15 and entry[0]!=sequence:return entry[:2]
            return sequence,None


RELAY=Relay()
VIEWERS=threading.BoundedSemaphore(32)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class LivePublisher:
    def __init__(self,connection,allow_local=False):
        self.connection=connection;self.queue=collections.deque(maxlen=12);self.lock=threading.Lock();self.stop=threading.Event();self.thread=None
        u=urlparse(connection.get('url',''))
        if (u.scheme!='https' and not (allow_local and u.hostname=='127.0.0.1')) or not re.fullmatch(r'/api/live/\d+',u.path) or u.username or u.password:raise ValueError('Invalid live destination')
        self.opener=urllib.request.build_opener(NoRedirect())
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def submit(self,round_number,game,frame):
        with self.lock:self.queue.append({'round':round_number,'game':game,'frame':frame,'captured_at':time.time()})
    def run(self):
        while not self.stop.wait(.2):
            with self.lock:
                batch=[f for f in self.queue if time.time()-f['captured_at']<1.5];self.queue.clear()
            if not batch:continue
            try:
                req=urllib.request.Request(self.connection['url'],data=json.dumps({'frames':batch},allow_nan=False,separators=(',',':')).encode(),headers={'Authorization':'Bearer '+self.connection['token'],'Content-Type':'application/json'},method='POST')
                with self.opener.open(req,timeout=2) as response:response.read(1024)
            except Exception:
                # Drop obsolete frames and retry later. Results/logs remain authoritative.
                self.stop.wait(1)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=.1)
