import io,unittest
from replay import parse_replay
from runner import monitor_snapshot

class Stamina(unittest.TestCase):
 def test_stamina_is_preserved_in_replay_and_live_frames(self):
  show='(show 1 ((b) 0 0 0 0) ((l 1) 0 9 -40 0 0 0 90 (s 0 1 1)) ((r 2) 0 1 10 0 0 0 0 (s 1000 1 1)))'
  replay=parse_replay(io.StringIO('ULG5\n'+show+'\n'))
  self.assertEqual([p[6] for p in replay['frames'][0]['players']],[0,1000])
  self.assertEqual(monitor_snapshot(show)['frame']['players'],replay['frames'][0]['players'])
