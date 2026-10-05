"""Lifecycle integration with a fake UDP server, NOT a real RCSS match."""
import os
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner import run_match, run_job, start_team, monitor_snapshot
FAKE=r'''#!/usr/bin/env python3
import sys,socket,time
from pathlib import Path
args=dict(a.removeprefix('server::').split('=',1) for a in sys.argv[1:])
folder=Path(args['game_log_dir'])
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',6000));s.settimeout(.05)
peer=None;done=None
players=' '.join('((%s %d) 0 0x1 %d 0 0 0 0 0)'%(side,n,20+n) for side in ['l','r'] for n in range(1,12))
show='(show 1 ((b) 0 0 0 0) '+players+')'
while True:
    try:data,peer=s.recvfrom(8192)
    except socket.timeout:pass
    if peer:s.sendto(show.encode()+b'\0',peer)
    if (folder/'left-ready').exists() and (folder/'right-ready').exists():
        if done is None:done=time.monotonic()+.5
        if time.monotonic()>done:break
(folder/'match.rcg').write_text('ULG5\n(team 0 A B 0 0)\n(playmode 0 play_on)\n'+show+'\n(playmode 6000 time_over)\n(team 6000 A B 2 1)\n')
(folder/'match.rcl').write_text('fake integration fixture\n')
s.close()
'''
class Lifecycle(unittest.TestCase):
    def test_each_team_loads_its_own_bundled_library(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); env=os.environ.copy()
            env.update(RCSS_HOST='127.0.0.1',RCSS_PORT='6000',RCSS_COACH_PORT='6001',RCSS_OLCOACH_PORT='6002')
            env['LD_LIBRARY_PATH']=str(base/'server-libs')
            for side,value in [('left',11),('right',22)]:
                root=base/side; libs=root/'lib'; libs.mkdir(parents=True)
                (root/'library.c').write_text(f'int team_value(void) {{ return {value}; }}')
                (root/'player.c').write_text('#include <stdio.h>\nint team_value(void); int main(void) { printf("%d\\n",team_value()); }')
                subprocess.run(['cc','-shared','-fPIC','-Wl,-soname,libfixture.so.18',str(root/'library.c'),'-o',str(libs/'libfixture.so.18')],check=True)
                subprocess.run(['cc',str(root/'player.c'),'-L'+str(libs),'-l:libfixture.so.18','-o',str(root/'player')],check=True)
                procs=[]
                with (root/'launch.log').open('wb') as log:
                    start_team({'directory':'.','command':'./player'},root,log,procs,env)
                    self.assertEqual(procs[0].wait(timeout=5),0)
                self.assertEqual((root/'launch.log').read_text(),f'{value}\n')
            self.assertEqual(env['LD_LIBRARY_PATH'],str(base/'server-libs'))

    def test_failed_matches_do_not_report_completed_batch(self):
        success={'status':'completed','left_score':1,'right_score':0,'possession':{}}
        for outcomes,expected in (([success,success],'completed'),
                                  ([success,RuntimeError('server failed')],'failed'),
                                  ([RuntimeError('server failed')]*2,'failed')):
            with self.subTest(expected=expected),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                config={'rounds':1,'games_per_round':2,'left':{'name':'A'},'right':{'name':'B'}}
                state={'config':config,'matches':[]}
                job={'state':state,'root':root,'cancel':threading.Event()}
                def write(_): (root/'results.json').write_text(json.dumps(state))
                with patch('runner.run_match',side_effect=outcomes): run_job(job,write)
                self.assertEqual(state['status'],expected)
                self.assertEqual(len(state['matches']),2)
                self.assertTrue(state['archive_ready'])
                self.assertTrue((root/'logs.zip').is_file())

    def test_live_snapshot_tracks_cycles_score_and_real_end(self):
        data='(show 3000 (pm 3) (tm A B 2 1) ((b) 0 0 0 0) ((l 1) 0 0x1 1 1) ((r 1) 0 0x1 3 4))'
        result=monitor_snapshot(data)
        self.assertEqual(result['percent'],50)
        self.assertEqual(result['cycle'],3000)
        self.assertEqual(result['left_score'],2)
        self.assertEqual(result['right_players'],1)
        self.assertLess(monitor_snapshot('(show 6000 (pm 3))',result)['percent'],100)
        self.assertEqual(monitor_snapshot('(playmode 6000 time_over)',result)['percent'],100)
        self.assertEqual(monitor_snapshot('(msg malformed XPM)',result),result)

    def test_runner_argv_logs_and_result(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); fake=root/'server';fake.write_text(FAKE);fake.chmod(0o700)
            teams=root/'teams';(teams/'left').mkdir(parents=True);(teams/'right').mkdir()
            folder=root/'logs';c={'synch_mode':False}
            for side in ('left','right'):
                c[side]={'directory':'.','command':f'touch "{folder}/{side}-ready"'}
            with patch.dict(os.environ,{'RCSSSERVER':str(fake),'MATCH_TIMEOUT_SECONDS':'10'}):
                updates=[]
                result=run_match(c,teams,folder,threading.Event(),updates.append)
            self.assertTrue(updates)
            self.assertTrue(any(u.get('stage')=='playing' for u in updates))
            self.assertEqual(result['status'],'completed');self.assertEqual(result['left_score'],2);self.assertTrue((folder/'left.log').exists());self.assertEqual(result['possession']['free_percent'],100)
if __name__=='__main__':unittest.main()
