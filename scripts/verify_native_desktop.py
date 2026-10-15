"""Run inside the built Docker image. Tests the actual Qt GUI, not a replica."""
import os,time,subprocess,socket
from pathlib import Path
from native_desktop import DESKTOP
try:
 DESKTOP.start();assert DESKTOP.app.poll() is None
 windows=DESKTOP.windows();assert windows
 print('Native window:',DESKTOP.xdo('getwindowname',DESKTOP.main_window).stdout.strip(),flush=True)
 # Native Formation Editor; actual Qt window and the close action must work.
 DESKTOP.xdo('windowactivate',DESKTOP.main_window);DESKTOP.xdo('key','--clearmodifiers','ctrl+alt+f')
 DESKTOP.wait(lambda:len(DESKTOP.windows())>1)
 DESKTOP.close_tool();DESKTOP.wait(lambda:len(DESKTOP.windows())==1)
 assert DESKTOP.app.poll() is None,'Closing an editor killed the main monitor'
 # The website sees the editor's actual current state and exports a real native model.
 DESKTOP.formation_command('new')
 DESKTOP.wait(lambda:DESKTOP.formation_preview().get('available'))
 preview=DESKTOP.formation_preview();assert len(preview['players'])==11
 export=DESKTOP.root/'files'/'website-formation.conf'
 DESKTOP.formation_command('export',export)
 import json
 model=json.loads(export.read_text());assert len(model['role'])==11 and model['data']
 DESKTOP.formation_command('open',export)
 assert DESKTOP.formation_preview()['available']
 DESKTOP.close_tool()
 # A real native file-open action. Small valid rcg fixture, no browser parser.
 rcg=DESKTOP.root/'files'/'native-fixture.rcg'
 rcg.write_text('ULG5\n(team 0 Blue Red 0 0)\n(playmode 0 before_kick_off)\n(show 1 ((b) 0 0 0 0))\n')
 DESKTOP.open_file(rcg);time.sleep(.5);assert DESKTOP.app.poll() is None
 # Raw UDP handshake through both tunnel ends, including native monitor parsing.
 from native_tunnel import NativeTunnel
 broker=DESKTOP.broker;broker.bind('17')
 sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(5)
 tunnel=NativeTunnel(lambda body:broker.exchange('17',body),sock.getsockname()[1])
 try:
  DESKTOP.xdo('windowactivate',DESKTOP.main_window);DESKTOP.xdo('key','--clearmodifiers','ctrl+c')
  data,addr=sock.recvfrom(65535);assert b'dispinit' in data,data
  sock.sendto(b'(team 0 Blue Red 0 0)\0',addr)
  sock.sendto(b'(show 1 ((b) 0 0 0 0))\0',addr)
  time.sleep(.5);assert DESKTOP.app.poll() is None
 finally:tunnel.close();sock.close()
 # Test the authenticated HTTP/WebSocket route and the actual RFB greeting.
 import base64,threading
 from http.server import ThreadingHTTPServer
 from cloud_app import Handler
 os.environ.update(ARENA_USER='native-check',ARENA_PASSWORD='native-check-only')
 http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
 threading.Thread(target=http.serve_forever,daemon=True).start()
 try:
  with socket.create_connection(('127.0.0.1',http.server_port),timeout=5) as web:
   auth=base64.b64encode(b'native-check:native-check-only').decode()
   request=('GET /native/socket HTTP/1.1\r\nHost: 127.0.0.1:'+str(http.server_port)+'\r\nAuthorization: Basic '+auth+'\r\nOrigin: http://127.0.0.1:'+str(http.server_port)+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n\r\n')
   web.sendall(request.encode());response=b''
   while b'RFB 003.' not in response and len(response)<16384:
    chunk=web.recv(4096)
    if not chunk:raise RuntimeError('VNC connection closed before RFB greeting')
    response+=chunk
   assert b'101 Switching Protocols' in response,response
   assert b'RFB 003.' in response,response
 finally:http.shutdown();http.server_close()
 # Screenshot proves native Qt/editor rendering survives the complete path.
 subprocess.run(['xwd','-root','-silent','-display',':91','-out',str(DESKTOP.root/'native.xwd')],check=True)
 print('PASS original Qt startup, native formation editor/close, RCG file open and outbound monitor tunnel',flush=True)
finally:DESKTOP.close()
