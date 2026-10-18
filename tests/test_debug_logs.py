import io,tempfile,time,unittest
from pathlib import Path
from debug_logs import parse_line,attach_replay,DebugTail
from live import Relay
class Debug(unittest.TestCase):
 def test_native_log_shapes_messages_and_stopped_cycle(self):
  r=parse_line('17, 2 1024 l 1 2 3 4 red','l:9')[0]
  self.assertEqual((r['cycle'],r['stopped'],r['kind'],r['values']),(17,2,'l',[1,2,3,4]))
  self.assertEqual(parse_line('17 1 m 3 4 (c cyan) receiver 10','l:9')[0]['text'],'receiver 10')
  self.assertEqual(parse_line('17 1 p nan 2','l:9'),[])
 def test_native_dcl_actor_target_and_rect_geometry(self):
  records=parse_line('%% debug [((debug (format-version 5)) (time 12,0) (s r 8 0 1 2 0 0 90 0) (target-point 3 4) (rect 1 2 4 6 "blue") (message "pass"))]','l:1')
  self.assertEqual(records[0]['agent'],'r:8');self.assertEqual(records[1]['values'],[1,2,3,4]);self.assertEqual(records[2]['text'],'pass')
 def test_replay_has_only_recorded_cycles_live_tailer_does_not_use_future(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);folder=root/'debug-log/left-team';folder.mkdir(parents=True);log=folder/'Blue-7.log';log.write_text('1 1024 l 0 0 2 3 red\n3 1 M future\n')
   data=attach_replay({'frames':[{'cycle':1},{'cycle':2}]},root)
   self.assertEqual(data['frames'][0]['debug'][0]['agent'],'l:7');self.assertNotIn('debug',data['frames'][1])
   tail=DebugTail(root)
   try:
    deadline=time.monotonic()+2
    while not tail.frame(1) and time.monotonic()<deadline:time.sleep(.02)
    self.assertEqual(tail.frame(1)[0]['cycle'],1);self.assertTrue(all(r['cycle']<=2 for r in tail.frame(2)))
   finally:tail.close()
 def test_relay_preserves_intermediate_packets_for_reconnecting_viewer(self):
  relay=Relay();payload=lambda n:{'frames':[{'round':1,'game':1,'frame':{'cycle':n,'players':[]}}]}
  relay.publish('test',payload(1));first,_=relay.wait('test',0)
  relay.publish('test',payload(2));relay.publish('test',payload(3))
  second,data=relay.wait('test',first);self.assertEqual(data['frames'][0]['frame']['cycle'],2)
  third,data=relay.wait('test',second);self.assertEqual(data['frames'][0]['frame']['cycle'],3)
 def test_debug_client_wrapper_passes_only_advertised_flags(self):
  import subprocess,os
  from offline_logs import prepare_team
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);src=root/'src';src.mkdir();code=src/'player.c'
   code.write_text('#include <stdio.h>\n#include <string.h>\nint main(int argc,char**argv){if(argc>1&&!strcmp(argv[1],"--help")){puts("--debug --debug_pass --debug_server_logging --log_dir");return 0;}for(int i=1;i<argc;i++)puts(argv[i]);return 0;}')
   subprocess.run(['cc',str(code),'-o',str(src/'player')],check=True)
   info=prepare_team(src,root/'runtime',root/'logs',os.environ,offline=False,debug=True)
   output=subprocess.check_output([str(root/'runtime/player')],text=True)
   self.assertIn('--debug_pass',output);self.assertIn('--debug_server_logging',output);self.assertNotIn('--offline_logging',output);self.assertNotIn('--debug_shoot',output);self.assertEqual(info['debug_clients'],['player'])
