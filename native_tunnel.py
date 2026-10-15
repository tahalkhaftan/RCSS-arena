"""Original RCSS UDP packets over an authenticated, outbound HTTP exchange.

Only the fixed loopback monitor port is reachable. No filesystem, arbitrary
network address or shell command is accepted from a tunnel packet.
"""
import base64,collections,json,re,select,socket,threading,time,urllib.request

MAX_PACKETS=48

def unpack(value):
    if not isinstance(value,str) or len(value)>87384:raise ValueError('Invalid UDP packet')
    data=base64.b64decode(value,validate=True)
    if not 0<len(data)<=65507:raise ValueError('Invalid UDP packet')
    return data

def pack(data):return base64.b64encode(data).decode('ascii')

class MonitorBroker:
    """One shared authenticated native desktop, bound to one selected test."""
    def __init__(self,port=16000):
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1',port));self.socket.settimeout(.2)
        self.lock=threading.Lock();self.target=None;self.clients={};self.queue=collections.deque(maxlen=MAX_PACKETS)
        self.debug_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.epoch=0;self.stopped=threading.Event()
        threading.Thread(target=self.run,daemon=True).start()
    def bind(self,target):
        with self.lock:
            if target!=self.target:
                self.target=target;self.epoch+=1;self.queue.clear()
                for ident,c in self.clients.items():
                    c.pop('show',None);c['last_show']=0
                    if c.get('init'):self.queue.append({'client':ident,'data':pack(c['init'])})
    def run(self):
        while not self.stopped.is_set():
            try:data,addr=self.socket.recvfrom(65535)
            except socket.timeout:continue
            except OSError:return
            if not data:continue
            with self.lock:
                ident=str(addr[1]);c=self.clients.get(ident)
                if c is None:
                    if len(self.clients)>=8:continue
                    c=self.clients[ident]={'address':addr}
                if data.startswith(b'(dispinit'):c['init']=data
                if data.startswith(b'(dispbye'):
                    self.clients.pop(ident,None)
                if self.target:self.queue.append({'client':ident,'data':pack(data)})
    def exchange(self,target,body):
        packets=body.get('packets',[])
        if not isinstance(packets,list) or len(packets)>MAX_PACKETS:raise ValueError('Invalid packets')
        debug=body.get('debug',[])
        if not isinstance(debug,list) or len(debug)>MAX_PACKETS:raise ValueError('Invalid debug packets')
        debug=[unpack(p) for p in debug]
        # Decode the complete batch before delivering any packet.
        decoded=[(str(p['client']),unpack(p['data'])) for p in packets]
        with self.lock:
            if target!=self.target:return {'active':False,'epoch':self.epoch,'packets':[]}
            if body.get('epoch')==self.epoch:
                for data in debug:
                    if len(data)<8192:self.debug_socket.sendto(data,('127.0.0.1',6032))
                now=time.monotonic()
                for ident,data in decoded:
                    c=self.clients.get(ident)
                    if c is None:continue
                    if data.startswith(b'(show '):c['show']=data
                    else:self.socket.sendto(data,c['address'])
                for c in self.clients.values():
                    if c.get('show') and now-c.get('last_show',0)>=.1:
                        self.socket.sendto(c.pop('show'),c['address']);c['last_show']=now
            pending=list(self.queue);self.queue.clear()
            return {'active':True,'epoch':self.epoch,'packets':pending}
    def close(self):self.stopped.set();self.socket.close();self.debug_socket.close()

class NativeTunnel:
    """Match-side tunnel. HTTP failure cannot block a match or its log writer."""
    def __init__(self,exchange,server_port=6000):
        self.exchange=exchange;self.port=server_port;self.stop=threading.Event();self.lock=threading.Lock()
        self.clients={};self.epoch=None;self.generation=0;self.last_generation=-1;self.debug_enabled=False;self.debug_socket=None;self.active=False
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def reset(self,debug=False):
        with self.lock:self.generation+=1;self.debug_enabled=debug
    def clear(self):
        for c in self.clients.values():c['socket'].close()
        self.clients.clear()
    def run(self):
        outgoing=[];inits={}
        try:
            while not self.stop.is_set():
                with self.lock:generation=self.generation
                if generation!=self.last_generation:
                    self.clear();outgoing=[];self.last_generation=generation
                    # Reattach native monitor to the next RCSS process at the same port.
                    for ident,data in inits.items():self.command(ident,data)
                if self.debug_enabled and self.debug_socket is None:
                    try:
                        self.debug_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.debug_socket.bind(('127.0.0.1',6032));self.debug_socket.setblocking(False)
                    except OSError:
                        if self.debug_socket:self.debug_socket.close()
                        self.debug_socket=None
                debug=[]
                if self.debug_socket:
                    for _ in range(MAX_PACKETS):
                        try:debug.append(pack(self.debug_socket.recvfrom(8191)[0]))
                        except (BlockingIOError,OSError):break
                for ident,c in list(self.clients.items()):
                    for _ in range(128):
                        try:data,addr=c['socket'].recvfrom(65535)
                        except BlockingIOError:break
                        except OSError:break
                        if addr[0]!='127.0.0.1':continue
                        c['address']=addr
                        if data.startswith(b'(show '):c['show']=data
                        else:outgoing.append({'client':ident,'data':pack(data)})
                        if len(outgoing)>=MAX_PACKETS:break
                    if len(outgoing)>=MAX_PACKETS:break
                    if c.get('show') and time.monotonic()-c.get('last_show',0)>=.1 and len(outgoing)<MAX_PACKETS:
                        outgoing.append({'client':ident,'data':pack(c.pop('show'))});c['last_show']=time.monotonic()
                    # Initial handshake may precede server startup; retry only before any response.
                    if c['address'][1]==self.port and c.get('init') and time.monotonic()-c['sent']>1:
                        c['socket'].sendto(c['init'],c['address']);c['sent']=time.monotonic()
                try:
                    answer=self.exchange({'epoch':self.epoch,'packets':outgoing,'debug':debug if self.active else []});outgoing=[]
                    self.active=bool(answer.get('active'))
                    if answer.get('epoch')!=self.epoch:
                        self.clear();inits.clear();self.epoch=answer.get('epoch')
                    if not answer.get('active'):
                        self.clear();inits.clear();self.stop.wait(.5);continue
                    packets=answer.get('packets',[])
                    if not isinstance(packets,list) or len(packets)>MAX_PACKETS:raise ValueError('Invalid packets')
                    for p in packets:
                        ident=str(p['client']);data=unpack(p['data'])
                        if not re.fullmatch(r'\d{1,5}',ident):continue
                        if data.startswith(b'(dispinit'):inits[ident]=data
                        self.command(ident,data)
                except Exception:
                    outgoing=[];self.stop.wait(.5)
                self.stop.wait(.08)
        finally:
            self.clear()
            if self.debug_socket:self.debug_socket.close()
    def command(self,ident,data):
        c=self.clients.get(ident)
        if c is None:
            if len(self.clients)>=8:return
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.setblocking(False)
            c=self.clients[ident]={'socket':sock,'address':('127.0.0.1',self.port),'sent':0}
        c['socket'].sendto(data,c['address']);c['sent']=time.monotonic()
        if data.startswith(b'(dispinit'):c['init']=data
        if data.startswith(b'(dispbye'):c['socket'].close();self.clients.pop(ident,None)
    def close(self):self.stop.set();self.thread.join(timeout=.2)

def http_exchange(connection):
    from live import NoRedirect
    opener=urllib.request.build_opener(NoRedirect())
    def exchange(body):
        request=urllib.request.Request(connection['url'].replace('/api/live/','/api/native/tunnel/'),data=json.dumps(body,separators=(',',':')).encode(),headers={'Authorization':'Bearer '+connection['token'],'Content-Type':'application/json'})
        with opener.open(request,timeout=2) as response:return json.load(response)
    return exchange
