import gzip,io,json,tempfile,threading,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from replay import parse_replay,encode_replay,asset_name
from cloud_app import replay_data,REPLAY_CACHE
from runner import monitor_snapshot,run_job

LOG='''ULG5
(server_param (simulator_step 100))
(team 0 Blue Orange 0 0)
(playmode 0 play_on)
(msg 0 1 "(team_graphic_l (0 0 \"broken quotes\"))")
(show 1 ((b) 4 5 0 0) ((l 1) 0 0x9 -45 2 0 0 90 0) ((r 2) 0 0x1 10 -2 0 0 -30 0) ((r 3) 0 0x0 0 0 0 0 0 0))
(show 6000 (pm 2) (tm Blue Orange 2 1) ((b) 0 0 0 0) ((l 1) 0 0x9 -45 0 0 0 0 0))
(team 6000 Blue Orange 2 1)
(playmode 6000 time_over)
'''
class Replay(unittest.TestCase):
 def setUp(self):REPLAY_CACHE.clear()
 def test_positions_sides_heading_goalie_score_and_graphics(self):
  replay=parse_replay(io.StringIO(LOG));f=replay['frames'][0]
  self.assertEqual(f['ball'],[4,5]);self.assertEqual(f['players'][0],['l',1,-45,2,90,True])
  self.assertEqual(len(f['players']),2)
  self.assertEqual(replay['frames'][-1]['cycle'],6000)
  self.assertEqual(replay['final_score'],[2,1])
  self.assertEqual(json.loads(gzip.decompress(encode_replay(io.StringIO(LOG)))),replay)
 def test_live_frame_uses_same_coordinates_as_replay(self):
  line=next(l for l in LOG.splitlines() if l.startswith('(show 1 '))
  snap=monitor_snapshot(line)
  self.assertEqual(snap['frame']['players'],parse_replay(io.StringIO(LOG))['frames'][0]['players'])
 def test_each_game_has_distinct_replay_and_old_zip_fallback(self):
  buffer=io.BytesIO()
  with zipfile.ZipFile(buffer,'w') as z:
   z.writestr('logs/round-001-game-002/match.rcg',LOG)
  class Storage:
   def release(self,ident):return {'name':'arena-'+'a'*32}
   def assets(self,ident):return {'logs.zip':{'id':9,'size':len(buffer.getvalue())}}
   def open(self,*args,**kwargs):return io.BytesIO(buffer.getvalue())
  self.assertEqual(json.loads(gzip.decompress(replay_data(Storage(),7,1,2)))['final_score'],[2,1])
  with self.assertRaises(LookupError):replay_data(Storage(),7,1,1)
 def test_published_replay_available_before_final_archive(self):
  blob=encode_replay(io.StringIO(LOG))
  class Storage:
   def release(self,ident):return {'tag_name':'untagged-1','name':'arena-'+'a'*32}
   def assets(self,ident):return {asset_name(2,3):{'size':len(blob)}}
   def read_asset(self,asset):return blob
  self.assertEqual(replay_data(Storage(),7,2,3),blob)
 def test_unrelated_release_rejected(self):
  class Storage:
   def release(self,ident):return {'name':'not-arena'}
  with self.assertRaises(ValueError):replay_data(Storage(),7,1,1)
 def test_replay_generated_per_match_without_changing_result(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);state={'config':{'rounds':1,'games_per_round':2,'left':{'name':'A'},'right':{'name':'B'}},'matches':[]}
   job={'state':state,'root':root,'cancel':threading.Event()}
   def fake(config,teams,folder,cancel,progress):
    folder.mkdir(parents=True);(folder/'match.rcg').write_text(LOG)
    return {'status':'completed','left_score':2,'right_score':1,'possession':{}}
   def write(_):(root/'results.json').write_text(json.dumps(state))
   with patch('runner.run_match',side_effect=fake):run_job(job,write)
   self.assertEqual(state['status'],'completed')
   self.assertTrue(all(m['replay_available'] for m in state['matches']))
   with zipfile.ZipFile(root/'logs.zip') as z:self.assertIn('logs/round-001-game-002/replay.json.gz',z.namelist())
