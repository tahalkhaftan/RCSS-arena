import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis import analyze, summary
from app import extract, validate

HEADER='ULG5\n(server_param (ball_size 0.085) (player_size 0.3) (kickable_margin 0.7))\n(player_type (id 0) (player_size 0.3) (kickable_margin 0.7))\n(team 0 A B 0 0)\n(playmode 0 play_on)\n'
def show(c,l,r): return f'(show {c} ((b) 0 0 0 0) ((l 1) 0 0x1 {l} 0 0 0 0 0) ((r 1) 0 0x1 {r} 0 0 0 0 0))\n'
class Core(unittest.TestCase):
    def test_real_server_header_contains_text_parameters(self):
        header=HEADER.replace('(ball_size 0.085)', '(coach_msg_file "") (game_log_dir "/tmp/logs") (game_log_fixed_name "match") (ball_size 0.085)')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'match.rcg'
            p.write_text(header+show(1,.5,4)+'(playmode 6000 time_over)\n(team 6000 A B 2 1)\n')
            result=analyze(p)
            self.assertTrue(result['natural_end'])
            self.assertEqual(result['scores'],[2,1])
            self.assertEqual(result['possession']['left_percent'],100)

    def test_possession_categories_and_final_score(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'match.rcg';p.write_text(HEADER+show(1,.5,4)+show(2,4,.5)+show(3,.5,.5)+show(4,4,4)+'(playmode 5 time_over)\n(team 5 A B 2 1)\n')
            x=analyze(p);self.assertTrue(x['natural_end']);self.assertEqual(x['scores'],[2,1]);self.assertEqual(x['possession']['left_percent'],25);self.assertEqual(x['possession']['shared_percent'],25)
    def test_excludes_stoppage_and_disabled_players(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';p.write_text(HEADER+show(1,.5,4)+show(1,.5,4)+'(playmode 2 before_kick_off)\n'+show(2,4,.5))
            self.assertEqual(analyze(p)['possession']['cycles'],1)
    def test_heterogeneous_kickable_radius(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';p.write_text(HEADER+'(player_type (id 1) (player_size .3) (kickable_margin 1.0))\n'+show(1,1.2,4).replace('((l 1) 0','((l 1) 1'))
            self.assertEqual(analyze(p)['possession']['left_percent'],100)
    def test_incomplete_not_in_aggregate(self):
        x=summary([{'status':'failed'},{'status':'completed','left_score':2,'right_score':1,'possession':{'left_percent':25}}]);self.assertEqual(x['completed'],1);self.assertEqual(x['average_possession']['left_percent'],25)
    def test_zip_traversal(self):
        for name in ('../evil','/evil','a/../../evil','a\\evil'):
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:z.writestr(name,'bad')
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):extract(b.getvalue(),Path(d))
    def test_executable_restore(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('Team/start.sh','#!/bin/bash\nexit 0')
        with tempfile.TemporaryDirectory() as d:
            extract(b.getvalue(),Path(d));self.assertTrue(os.access(Path(d)/'Team/start.sh',os.X_OK))
    def test_counts_and_paths(self):
        c={'rounds':1,'games_per_round':5,'synch_mode':True,'left':{'name':'A','directory':'A/','command':'./start.sh'},'right':{'name':'B','directory':'B/','command':'./start.sh'}}
        self.assertEqual(validate(c)['games_per_round'],5);c['left']['directory']='../escape'
        with self.assertRaises(ValueError):validate(c)
if __name__=='__main__':unittest.main()
