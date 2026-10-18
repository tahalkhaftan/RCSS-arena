import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from performance import analyze_performance
from runner import run_job,results_only

LOG='''ULG6
(server_param (player_size 0.3) (kickable_margin 0.7) (ball_size 0.085))
(player_type (id 0) (player_size 0.3) (kickable_margin 0.7))
(team 0 Alpha Beta 0 0)
(playmode 0 before_kick_off)
(show 0 ((b) 0 0 0 0) ((l 2) 0 0x1 0 0 0 0 0 0 (c 0)))
(playmode 1 play_on)
(show 1 ((b) 0 0 0 0) ((l 2) 0 0x1 0 0 0 0 0 0 (c 0)) ((l 3) 0 0x1 6 0 0 0 0 0 (c 0)))
(show 2 ((b) 2 0 2 0) ((l 2) 0 0x3 0 0 0 0 0 0 (c 1)) ((l 3) 0 0x1 6 0 0 0 0 0 (c 0)))
(show 3 ((b) 4 0 2 0) ((l 2) 0 0x1 0 0 0 0 0 0 (c 1)) ((l 3) 0 0x1 6 0 0 0 0 0 (c 0)))
(show 4 ((b) 6 0 0 0) ((l 2) 0 0x1 0 0 0 0 0 0 (c 1)) ((l 3) 0 0x1 6 0 0 0 0 0 (c 0)))
(show 5 ((b) 6 0 0 0) ((l 2) 0 0x1 0 0 0 0 0 0 (c 1)) ((l 3) 0 0x1 6 0 0 0 0 0 (c 0)))
(team 5 Alpha Beta 0 0)
(playmode 5 time_over)
'''
class PerformanceExport(unittest.TestCase):
    def test_full_log_export_has_resolved_pass_and_no_position_payload(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'match.rcg';p.write_text(LOG);data=analyze_performance(p)
        self.assertEqual(data['left']['passes']['completed'],1)
        self.assertEqual(data['left']['passes']['accuracy_percent'],100)
        self.assertEqual(data['left']['shots']['total'],0)
        self.assertEqual(data['quality']['missing_active_cycles'],0)
        self.assertEqual(data['status'],'complete')
        for forbidden in ('frames','players','ball','control_radii','kickers'):
            self.assertNotIn('"'+forbidden+'"',json.dumps(data))

    def test_gaps_remain_partial_instead_of_inventing_actions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'match.rcg';p.write_text(LOG.replace('(show 3 ', '(show 30 ').replace('(show 4 ', '(show 40 ').replace('(show 5 ', '(show 50 '))
            data=analyze_performance(p)
        self.assertEqual(data['status'],'partial')
        self.assertGreater(data['quality']['missing_active_cycles'],0)
        self.assertEqual(data['left']['passes']['completed'],0)

    def test_each_finished_match_saves_its_own_statistics(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state={'config':{'rounds':1,'games_per_round':2,'left':{'name':'A'},'right':{'name':'B'}},'matches':[]}
            job={'state':state,'root':root,'cancel':threading.Event()}
            def fake(config,teams,folder,cancel,progress):
                folder.mkdir(parents=True);score=1 if '002' in folder.name else 0
                (folder/'match.rcg').write_text(LOG.replace('(team 5 Alpha Beta 0 0)',f'(team 5 Alpha Beta {score} 0)'))
                return {'status':'completed','left_score':score,'right_score':0}
            def write(_):(root/'results.json').write_text(json.dumps(results_only(state)))
            with patch('runner.run_match',side_effect=fake):run_job(job,write)
            saved=json.loads((root/'results.json').read_text())
            self.assertEqual([m['performance']['left']['goals'] for m in saved['matches']],[0,1])
            self.assertTrue(all(m['performance']['left']['passes']['completed']==1 for m in saved['matches']))
            self.assertEqual(saved['matches'][1]['performance']['left']['shots']['on_target'],0,'Do not manufacture a shot to match the score')
