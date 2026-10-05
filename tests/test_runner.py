"""Lifecycle integration with a fake UDP server, NOT a real RCSS match."""
import os
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner import run_match, run_job
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

    def test_runner_argv_logs_and_result(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); fake=root/'server';fake.write_text(FAKE);fake.chmod(0o700)
            teams=root/'teams';(teams/'left').mkdir(parents=True);(teams/'right').mkdir()
            folder=root/'logs';c={'synch_mode':False}
            for side in ('left','right'):
                c[side]={'directory':'.','command':f'touch "{folder}/{side}-ready"'}
            with patch.dict(os.environ,{'RCSSSERVER':str(fake),'MATCH_TIMEOUT_SECONDS':'10'}):
                result=run_match(c,teams,folder,threading.Event())
            self.assertEqual(result['status'],'completed');self.assertEqual(result['left_score'],2);self.assertTrue((folder/'left.log').exists());self.assertEqual(result['possession']['free_percent'],100)
if __name__=='__main__':unittest.main()
