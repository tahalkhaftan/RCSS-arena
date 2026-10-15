"""CI-only native desktop server; never copied into the application image."""
import os,signal,threading,time,math
from native_tunnel import pack
from http.server import ThreadingHTTPServer
from cloud_app import Handler
from native_desktop import DESKTOP
os.environ.update(ARENA_USER='latency-test',ARENA_PASSWORD='latency-test-only')
def moving_match():
 broker=DESKTOP.broker;broker.bind('latency-fixture')
 for cycle in range(200):
  with broker.lock:clients=list(broker.clients)
  packets=[]
  for ident in clients:
   if cycle%20==0:packets.append({'client':ident,'data':pack(b'(team 0 Blue Red 0 0)\0')})
   x=30*math.sin(cycle*.15);y=20*math.cos(cycle*.15)
   players=' '.join(f'(({side} {i}) 0 1 {(-35 if side=="l" else 35)+i*2} {i*4-24+math.sin(cycle*.15)*3:.2f} 0 0 0 0)' for side in ('l','r') for i in range(1,12))
   packets.append({'client':ident,'data':pack(f'(show {cycle} ((b) {x:.2f} {y:.2f} 0 0) {players})\0'.encode())})
  broker.exchange('latency-fixture',{'epoch':broker.epoch,'packets':packets})
  time.sleep(.1)
class CheckHandler(Handler):
 def do_POST(self):
  if self.path=='/native-test/motion':
   if not self.auth():return
   DESKTOP.start();DESKTOP.broker.bind('latency-fixture')
   DESKTOP.xdo('windowactivate',DESKTOP.main_window);DESKTOP.xdo('key','--clearmodifiers','ctrl+c')
   threading.Thread(target=moving_match,daemon=True).start()
   return self.send(200,{'ok':True})
  return super().do_POST()
 def do_GET(self):
  if self.path=='/native-test/windows':
   if not self.auth():return
   return self.send(200,{'windows':DESKTOP.windows() if DESKTOP.app else []})
  return super().do_GET()
try:
 ThreadingHTTPServer(('0.0.0.0',8000),CheckHandler).serve_forever()
finally:DESKTOP.close()
