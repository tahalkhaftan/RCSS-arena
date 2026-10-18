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

class ResponsiveTransport(unittest.TestCase):
 def test_slow_video_receiver_cannot_block_clicks(self):
  from native_desktop import relay_stream
  client,browser=socket.socketpair();peer,server=socket.socketpair()
  browser.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096)
  server.settimeout(2);client.settimeout(2)
  relay=threading.Thread(target=relay_stream,args=(browser,peer),kwargs={'lifetime':3},daemon=True)
  def video():
   try:server.sendall(b'v'*2000000)
   except OSError:pass
  producer=threading.Thread(target=video,daemon=True)
  try:
   relay.start();producer.start();time.sleep(.1)
   # The browser deliberately does not consume any image data.
   start=time.monotonic();client.sendall(b'click')
   self.assertEqual(server.recv(5),b'click')
   self.assertLess(time.monotonic()-start,.5)
  finally:
   for s in (client,browser,peer,server):s.close()
   relay.join(1);producer.join(1)
 def test_stale_video_queue_disconnects_instead_of_growing(self):
  from native_desktop import relay_stream
  client,browser=socket.socketpair();peer,server=socket.socketpair()
  browser.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096);server.settimeout(.5)
  relay=threading.Thread(target=relay_stream,args=(browser,peer),kwargs={'lifetime':3,'lag_limit':.15},daemon=True)
  try:
   relay.start()
   try:server.sendall(b'v'*300000)
   except socket.timeout:pass
   relay.join(.8);self.assertFalse(relay.is_alive())
  finally:
   for s in (client,browser,peer,server):s.close()
 def test_live_frame_burst_coalesces_to_latest_without_losing_parameters(self):
  broker=MonitorBroker(0);client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(1)
  try:
   broker.bind('17');client.sendto(b'(dispinit version 5)\0',broker.socket.getsockname())
   deadline=time.monotonic()+1
   while not broker.clients and time.monotonic()<deadline:time.sleep(.005)
   ident=next(iter(broker.clients));packets=[{'client':ident,'data':pack(('(show '+str(i)+')\0').encode())} for i in range(40)]
   packets.append({'client':ident,'data':pack(b'(server_param fixture)\0')})
   broker.exchange('17',{'epoch':broker.epoch,'packets':packets})
   self.assertEqual(client.recv(65535),b'(server_param fixture)\0')
   self.assertEqual(client.recv(65535),b'(show 39)\0')
   client.settimeout(.05)
   with self.assertRaises(socket.timeout):client.recv(65535)
  finally:broker.close();client.close()

class ContinuousNativeReceive(unittest.TestCase):
 def test_slow_http_does_not_leave_udp_frames_waiting_in_kernel(self):
  entered=threading.Event();release=threading.Event()
  def slow(body):
   entered.set();release.wait(3)
   return {'active':False,'epoch':0,'packets':[]}
  tunnel=NativeTunnel(slow);server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
  server.bind(('127.0.0.1',0));server.settimeout(2)
  try:
   self.assertTrue(entered.wait(1));tunnel.port=server.getsockname()[1]
   tunnel.command('1',b'(dispinit version 5)\0');_,addr=server.recvfrom(65535)
   server.sendto(b'(server_param fixture)\0',addr)
   for cycle in range(200):
    server.sendto(f'(show {cycle})\0'.encode(),addr);time.sleep(.001)
   deadline=time.monotonic()+1
   while time.monotonic()<deadline:
    with tunnel.lock:latest=tunnel.clients['1'].get('show')
    if latest==b'(show 199)\0':break
    time.sleep(.005)
   self.assertEqual(latest,b'(show 199)\0','Receive must continue while HTTP is blocked')
   packets=[unpack(p['data']) for p in tunnel.take_packets()]
   self.assertEqual(packets,[b'(server_param fixture)\0',b'(show 199)\0'])
   self.assertEqual(tunnel.take_packets(),[])
  finally:release.set();tunnel.close();server.close()
 def test_broker_does_not_hold_a_fresh_frame_until_the_next_http_request(self):
  broker=MonitorBroker(0);client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(1)
  try:
   broker.bind('17');client.sendto(b'(dispinit version 5)\0',broker.socket.getsockname())
   deadline=time.monotonic()+1
   while not broker.clients and time.monotonic()<deadline:time.sleep(.005)
   ident=next(iter(broker.clients))
   for cycle in (1,2):
    broker.exchange('17',{'epoch':broker.epoch,'packets':[{'client':ident,'data':pack(f'(show {cycle})\0'.encode())}]})
    self.assertEqual(client.recv(65535),f'(show {cycle})\0'.encode())
  finally:broker.close();client.close()


class WindowExportIsolation(unittest.TestCase):
 def test_only_owned_visible_window_ids_may_create_streams(self):
  from native_desktop import DESKTOP
  with patch.object(DESKTOP,'window_state',return_value={'detached':True,'windows':[{'id':'123'}]}),patch('native_desktop.subprocess.Popen') as launch:
   for ident in ('1','456','../123','123;id'):
    with self.assertRaises(ValueError):DESKTOP.window_stream(ident)
   launch.assert_not_called()
  with patch.object(DESKTOP,'window_state',return_value={'detached':False,'windows':[{'id':'123'}]}),patch('native_desktop.subprocess.Popen') as launch:
   with self.assertRaises(ValueError):DESKTOP.window_stream('123')
   launch.assert_not_called()
 def test_hidden_tool_is_reopened_even_when_the_qt_snapshot_is_stale(self):
  from native_desktop import DESKTOP
  visible=['1'];record={'id':'2','key':'formation'}
  def command(*args):
   if args==('key','--clearmodifiers','ctrl+alt+f'):visible.append('2')
  with patch.object(DESKTOP,'set_detached'),patch.object(DESKTOP,'main_window','1',create=True),patch.object(DESKTOP,'window_state',return_value={'detached':True,'windows':[record]}),patch.object(DESKTOP,'windows',side_effect=lambda:visible.copy()),patch.object(DESKTOP,'xdo',side_effect=command) as xdo:
   self.assertEqual(DESKTOP.open_tool('formation'),record)
   xdo.assert_any_call('key','--clearmodifiers','ctrl+alt+f')

 def test_closing_a_browser_view_only_closes_an_owned_tool(self):
  from native_desktop import DESKTOP
  from tempfile import TemporaryDirectory
  from pathlib import Path
  state={'detached':True,'windows':[{'id':'1','key':'main'},{'id':'2','key':'formation'}]}
  with TemporaryDirectory() as folder,patch.object(DESKTOP,'root',Path(folder)),patch.object(DESKTOP,'window_state',return_value=state):
   with self.assertRaises(ValueError):DESKTOP.close_window('1')
   DESKTOP.close_window('999');self.assertFalse((Path(folder)/'windows.json.close').exists())
   state['windows'].append({'id':'3','key':'window','modal':True,'attached':True,'owner':'2'})
   self.assertTrue(DESKTOP.close_window('2')['confirmation']);self.assertFalse((Path(folder)/'windows.json.close').exists())
   state['windows'].pop();DESKTOP.close_window('2');self.assertEqual((Path(folder)/'windows.json.close').read_text(),'2')
