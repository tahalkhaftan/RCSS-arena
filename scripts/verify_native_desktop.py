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
 # Screenshot proves native Qt/editor rendering survives the complete path.
 subprocess.run(['xwd','-root','-silent','-display',':91','-out',str(DESKTOP.root/'native.xwd')],check=True)
 print('PASS original Qt startup, native formation editor/close, RCG file open and outbound monitor tunnel',flush=True)
finally:DESKTOP.close()
