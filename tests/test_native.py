import base64,json,os,socket,threading,time,unittest,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from native_tunnel import MonitorBroker,NativeTunnel,pack,unpack
from cloud_app import Handler

class NativeTests(unittest.TestCase):
 def test_packet_validation(self):
  self.assertEqual(unpack(pack(b'(show 7)\0')),b'(show 7)\0')
  for v in ('!!!','',pack(b'x'*65508)):
   with self.assertRaises(ValueError):unpack(v)
 def test_original_udp_roundtrip_and_command(self):
  broker=MonitorBroker(0);client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(3)
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0));server.settimeout(3)
  broker.bind('17');tunnel=NativeTunnel(lambda body:broker.exchange('17',body),server.getsockname()[1])
  try:
   client.sendto(b'(dispinit version 5)\0',broker.socket.getsockname())
   command,addr=server.recvfrom(65535);self.assertEqual(command,b'(dispinit version 5)\0')
   server.sendto(b'(server_param (goal_width 14.02))\0',addr)
   raw,remote=client.recvfrom(65535);self.assertEqual(raw,b'(server_param (goal_width 14.02))\0')
   client.sendto(b'(dispstart)\0',remote)
   self.assertEqual(server.recvfrom(65535)[0],b'(dispstart)\0')
   # Selection is isolated by test ID, including a personal-worker test.
   self.assertFalse(broker.exchange('18',{'packets':[]})['active'])
   broker.bind('personal:'+'a'*32)
   self.assertFalse(broker.exchange('17',{'packets':[]})['active'])
  finally:tunnel.close();broker.close();client.close();server.close()
 def test_native_routes_auth_origin_and_tunnel_token(self):
  with patch.dict(os.environ,{'ARENA_USER':'u','ARENA_PASSWORD':'p'}):
   http=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
   base='http://127.0.0.1:'+str(http.server_port);auth='Basic '+base64.b64encode(b'u:p').decode()
   try:
    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/native/site.js')
    self.assertEqual(e.exception.code,401)
    req=urllib.request.Request(base+'/native/site.js',headers={'Authorization':auth})
    with urllib.request.urlopen(req) as r:self.assertIn(b'Native',r.read().replace(b'native',b'Native'))
    req=urllib.request.Request(base+'/native/start',data=b'{}',headers={'Authorization':auth,'Origin':'https://elsewhere.example'})
    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
    self.assertEqual(e.exception.code,403)
    req=urllib.request.Request(base+'/api/native/tunnel/1',data=b'{}',headers={'Authorization':'Bearer bad'})
    with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
    self.assertEqual(e.exception.code,403)
   finally:http.shutdown();http.server_close();thread.join()
