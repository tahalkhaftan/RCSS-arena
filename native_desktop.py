"""Actual unmodified SoccerWindow2 in Xvfb/Openbox, transported by noVNC.

One session is shared by the Arena administrator. The VNC and UDP listeners
are loopback-only; all web routes require the site's existing authentication.
"""
import atexit,collections,json,mimetypes,os,re,select,shutil,socket,subprocess,threading,time
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from native_tunnel import MonitorBroker

ROOT=Path(__file__).resolve().parent
class Desktop:
    def __init__(self):
        self.lock=threading.RLock();self.processes=[];self.broker=None;self.app=None;self.last_used=0
        self.root=Path(os.environ.get('ARENA_DESKTOP_DIR','/tmp/arena-desktop'));self.env=None
        atexit.register(self.close)
        threading.Thread(target=self.reap,daemon=True).start()
    def reap(self):
        while True:
            time.sleep(30)
            if self.app and time.monotonic()-self.last_used>1200:self.close()
    def start(self):
        with self.lock:
            self.last_used=time.monotonic()
            if self.app and self.app.poll() is None:return
            self.close()
            for name in ('Xvfb','openbox','x11vnc','websockify','soccerwindow2','xdotool'):
                if not shutil.which(name):raise RuntimeError('Native desktop dependency missing: '+name+'; deploy the new Docker image')
            self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
            (self.root/'files').mkdir(exist_ok=True)
            env=os.environ.copy()
            # Never hand site/GitHub credentials to GUI child processes or their launchers.
            for k in list(env):
                if any(w in k for w in ('TOKEN','PASSWORD','SECRET')):env.pop(k,None)
            env.update(DISPLAY=':91',HOME=str(self.root),QT_X11_NO_MITSHM='1',QT_STYLE_OVERRIDE='Fusion')
            self.env=env
            self.broker=MonitorBroker()
            def launch(argv):
                with (self.root/'desktop.log').open('ab') as log:
                    p=subprocess.Popen(argv,cwd=self.root/'files',env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                self.processes.append(p);return p
            try:
                launch(['Xvfb',':91','-screen','0','1024x720x16','-nolisten','tcp','-ac'])
                self.wait(lambda:Path('/tmp/.X11-unix/X91').exists())
                launch(['openbox','--sm-disable'])
                launch(['x11vnc','-display',':91','-localhost','-rfbport','5901','-forever','-shared','-nopw','-threads','-wait','80','-defer','15','-quiet'])
                self.wait(lambda:self.port_open(5901))
                launch(['websockify','127.0.0.1:6081','127.0.0.1:5901'])
                self.wait(lambda:self.port_open(6081))
                self.app=launch(['soccerwindow2','--geometry','1004x670+0+0','--host','127.0.0.1','--port','16000','--client-version','5','--debug-server-mode','--debug-log-dir',str(self.root/'files')])
                self.wait(lambda:bool(self.windows()))
                self.main_window=self.windows()[0]
                self.xdo('windowsize',self.main_window,1024,680)
                self.xdo('windowactivate',self.main_window)
            except Exception:self.close();raise
    def wait(self,fn):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if fn():return
            time.sleep(.05)
        raise RuntimeError('Native desktop did not become ready; inspect desktop.log')
    @staticmethod
    def port_open(port):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.1):return True
        except OSError:return False
    def xdo(self,*args):return subprocess.run(['xdotool',*map(str,args)],env=self.env,capture_output=True,text=True,timeout=5)
    def windows(self):
        if not self.app:return []
        return self.xdo('search','--onlyvisible','--pid',self.app.pid).stdout.split()
    def exchange(self,target,body):
        with self.lock:
            return self.broker.exchange(target,body) if self.broker else {'active':False,'epoch':0,'packets':[]}
    def connect(self,target):
        self.start();self.broker.bind(target)
        self.xdo('windowactivate',self.main_window)
        self.xdo('key','--clearmodifiers','ctrl+c') # Native Monitor > Connect shortcut (verified upstream).
    def close_tool(self):
        self.start()
        # Openbox's standard close action closes the active child editor/dialog.
        active=self.xdo('getactivewindow').stdout.strip();windows=self.windows()
        if active in windows and active!=self.main_window:self.xdo('key','--clearmodifiers','alt+F4')
    def open_file(self,path):
        self.start();self.xdo('windowactivate',self.main_window);self.xdo('key','--clearmodifiers','ctrl+o');time.sleep(.2)
        self.xdo('type','--clearmodifiers','--delay','1',str(path));self.xdo('key','Return')
    def close(self):
        with self.lock:
            if self.broker:self.broker.close();self.broker=None
            for p in reversed(self.processes):
                if p.poll() is None:
                    try:p.terminate();p.wait(timeout=2)
                    except (OSError,subprocess.TimeoutExpired):p.kill()
            self.processes=[];self.app=None

DESKTOP=Desktop()

def json_body(h,limit=5*1024*1024):
    size=int(h.headers.get('Content-Length','0'))
    if not 0<size<=limit:raise ValueError('Invalid request size')
    body=json.loads(h.rfile.read(size))
    if not isinstance(body,dict):raise ValueError('JSON object required')
    return body

def same_origin(h):
    origin=h.headers.get('Origin')
    return not origin or urlparse(origin).netloc==h.headers.get('Host')

def websocket(h):
    if not same_origin(h):return h.send(403,{'error':'Origin rejected'})
    if h.headers.get('Upgrade','').lower()!='websocket':return h.send(400,{'error':'WebSocket required'})
    DESKTOP.start()
    # Proxy the original upgraded stream; websockify owns RFC6455/RFB parsing.
    with socket.create_connection(('127.0.0.1',6081),timeout=10) as peer:
        headers=['GET / HTTP/1.1','Host: 127.0.0.1:6081','Upgrade: websocket','Connection: Upgrade']
        for key in ('Sec-WebSocket-Key','Sec-WebSocket-Version','Sec-WebSocket-Protocol'):
            value=h.headers.get(key)
            if value:headers.append(key+': '+value)
        peer.sendall(('\r\n'.join(headers)+'\r\n\r\n').encode())
        response=bytearray()
        while b'\r\n\r\n' not in response:
            data=peer.recv(4096)
            if not data:raise OSError('VNC handshake failed')
            response.extend(data)
            if len(response)>16384:raise OSError('VNC handshake too large')
        if not response.startswith(b'HTTP/1.1 101') and not response.startswith(b'HTTP/1.0 101'):raise OSError('VNC handshake rejected')
        h.wfile.write(response);h.wfile.flush();h.close_connection=True
        relay_stream(h.connection,peer,touch=lambda:setattr(DESKTOP,'last_used',time.monotonic()))


def relay_stream(browser,peer,touch=lambda:None,lifetime=3600,lag_limit=5):
    """Fair duplex transport: a blocked image upload must not block mouse input.

    Retain WebSocket bytes in order; on excessive lag close the connection
    instead of dropping bytes within a frame. noVNC reconnects to the same app.
    """
    sockets=(browser,peer);queues={s:collections.deque() for s in sockets};sizes={s:0 for s in sockets}
    for sock in sockets:
        sock.setblocking(False)
        if sock.family in (socket.AF_INET,socket.AF_INET6):
            sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,16384)
    limits={browser:131072,peer:32768};until=time.monotonic()+lifetime
    try:
        while time.monotonic()<until:
            now=time.monotonic()
            if any(q and now-q[0][1]>lag_limit for q in queues.values()):return
            reads=[s for s in sockets if sizes[peer if s is browser else browser]<limits[peer if s is browser else browser]]
            writes=[s for s in (peer,browser) if queues[s]]
            readable,writable,_=select.select(reads,writes,[],.1)
            if readable or writable:touch()
            # Always handle input before more framebuffer data.
            for source in sockets:
                if source not in readable:continue
                target=peer if source is browser else browser
                try:data=source.recv(min(16384,limits[target]-sizes[target]))
                except BlockingIOError:continue
                if not data:return
                queues[target].append([memoryview(data),time.monotonic()]);sizes[target]+=len(data)
            for target in (peer,browser):
                if target not in writable:continue
                chunk,stamp=queues[target][0]
                try:n=target.send(chunk)
                except BlockingIOError:continue
                if not n:return
                sizes[target]-=n
                if n==len(chunk):queues[target].popleft()
                else:queues[target][0]=[chunk[n:],stamp]
    except (OSError,TimeoutError):return


def handle(h):
    path=urlparse(h.path).path
    tunnel=re.fullmatch(r'/api/native/tunnel/(\d+)',path)
    if tunnel:
        from live import valid_token
        header=h.headers.get('Authorization','')
        if h.command!='POST' or not header.startswith('Bearer ') or not valid_token(tunnel[1],header[7:]):h.send(403,{'error':'Invalid native token'});return True
        try:
            body=json_body(h)
            result=DESKTOP.exchange(tunnel[1],body)
            h.send(200,result)
        except (ValueError,KeyError,TypeError):h.send(400,{'error':'Invalid native packet batch'})
        return True
    if not path.startswith('/native/'):return False
    if not h.auth():return True
    if not same_origin(h):h.send(403,{'error':'Origin rejected'});return True
    try:
        if h.command=='GET':
            if path=='/native/socket':websocket(h);return True
            if path=='/native/status':
                running=bool(DESKTOP.app and DESKTOP.app.poll() is None)
                h.send(200,{'running':running,'target':DESKTOP.broker.target if DESKTOP.broker else None});return True
            if path=='/native/files':
                DESKTOP.start();h.send(200,sorted(p.name for p in (DESKTOP.root/'files').iterdir() if p.is_file()));return True
            if path.startswith('/native/download/'):
                DESKTOP.start();name=unquote(path.rsplit('/',1)[-1]);p=DESKTOP.root/'files'/name
                if name!=Path(name).name or not p.is_file() or p.is_symlink():raise ValueError('File not found')
                h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('Content-Length',str(p.stat().st_size));h.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+__import__('urllib.parse',fromlist=['quote']).quote(name));h.end_headers()
                with p.open('rb') as f:shutil.copyfileobj(f,h.wfile)
                return True
            base=Path('/opt/novnc') if path.startswith('/native/novnc/') else ROOT/'static'/'native'
            rel=unquote(path[len('/native/novnc/'):] if path.startswith('/native/novnc/') else path[len('/native/'):])
            p=(base/rel).resolve()
            if not p.is_relative_to(base.resolve()) or not p.is_file():h.send(404,{'error':'Not found'});return True
            h.send(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream');return True
        if h.command=='POST':
            if path=='/native/start':DESKTOP.start();h.send(200,{'ok':True});return True
            if path=='/native/stop':DESKTOP.close();h.send(200,{'ok':True});return True
            if path=='/native/connect':
                body=json_body(h);target=str(body.get('id',''))
                if not re.fullmatch(r'(\d+|personal:[a-f0-9]{32})',target):raise ValueError('Choose an Arena test first')
                DESKTOP.connect(target);h.send(200,{'ok':True});return True
            if path=='/native/close-tool':DESKTOP.close_tool();h.send(200,{'ok':True});return True
            if path=='/native/upload':
                DESKTOP.start();query=parse_qs(urlparse(h.path).query);name=query.get('name',[''])[0]
                if not name or name!=Path(name).name or not re.fullmatch(r'[\w .,+()\-]+',name) or name.startswith('.'):raise ValueError('Invalid filename')
                if Path(name).suffix.lower() not in ('.rcg','.gz','.log','.dcl','.ocl','.conf','.json','.dat','.csv','.xpm','.png','.svg','.txt','.xml'):raise ValueError('Upload a replay, debug log, or formation file')
                size=int(h.headers.get('Content-Length','0'))
                if size<=0 or size>shutil.disk_usage(DESKTOP.root).free-64*1024**2:raise ValueError('Not enough temporary disk space')
                p=DESKTOP.root/'files'/name
                with p.open('wb') as f:
                    remaining=size
                    while remaining:
                        data=h.rfile.read(min(remaining,65536))
                        if not data:raise ValueError('Incomplete upload')
                        f.write(data);remaining-=len(data)
                if query.get('open')==['1']:DESKTOP.open_file(p)
                h.send(200,{'name':name,'path':str(p)});return True
        h.send(404,{'error':'Not found'})
    except (ValueError,KeyError,TypeError) as exc:h.send(400,{'error':str(exc)})
    except (RuntimeError,OSError,subprocess.SubprocessError) as exc:h.send(503,{'error':str(exc)})
    return True
