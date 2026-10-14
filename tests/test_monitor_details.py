import io,json,unittest
from replay import parse_replay
from runner import monitor_snapshot,results_only
PARAM='(server_param (stamina_max 8000) (catchable_area_l 2) (player_size 0.3) (ball_size 0.085) (kickable_margin 0.7))'
TYPE='(player_type (id 2) (player_size 0.4) (kickable_margin 0.8) (player_speed_max 1.1))'
SHOW='(show 4 ((b) 1 2 0.1 -0.2) ((l 7) 2 1 3 4 0.2 0.3 90 -10 8 9 (v h 60) (s 7000 0.9 0.8) (f r 3) (c 1 2 3 4 5 6 7 8 9 10 11)))'
class Details(unittest.TestCase):
 def test_same_record_metadata_in_uploaded_replay_and_live(self):
  f=parse_replay(io.StringIO('ULG5\n'+PARAM+'\n'+TYPE+'\n'+SHOW+'\n'))['frames'][0]
  m=f['player_meta']['l:7'];self.assertEqual(m['neck'],-10);self.assertEqual(m['velocity'],[.2,.3]);self.assertEqual(m['pointto'],[8,9]);self.assertEqual(m['view_width'],60);self.assertEqual(m['attention'],['r',3]);self.assertEqual(m['counters'][-1],11)
  snap={}
  for record in (PARAM,TYPE,SHOW):snap=monitor_snapshot(record,snap)
  self.assertEqual(snap['frame'],f);self.assertEqual(f['parameters']['stamina_max'],8000)
  clean=results_only({'progress':snap});self.assertNotIn('frame',clean['progress']);self.assertNotIn('monitor_types',clean['progress']);self.assertNotIn('monitor_parameters',clean['progress'])
 def test_missing_optional_fields_stay_unknown(self):
  f=parse_replay(io.StringIO('ULG5\n(show 1 ((l 1) 0 9 1 2 0 0 0 (s 2000)))\n'))['frames'][0]
  self.assertNotIn('neck',f['player_meta']['l:1']);self.assertNotIn('view_width',f['player_meta']['l:1'])
