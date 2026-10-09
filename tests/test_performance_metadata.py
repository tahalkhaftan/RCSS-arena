import unittest
from analysis import sexpr
from replay import show_frame

class PerformanceMetadata(unittest.TestCase):
    def test_monitor_preserves_velocity_and_kick_counters_without_changing_player_layout(self):
        frame=show_frame(sexpr('(show 2 ((b) 1 2 2.5 -0.3) ((l 2) 0 0x1 1 2 0 0 90 0 (s 7000 1 1) (c 4 0 0 0 0 0 0 0)))'))
        self.assertEqual(frame['ball'],[1,2])
        self.assertEqual(frame['ball_velocity'],[2.5,-0.3])
        self.assertEqual(frame['kicks'],{'l:2':4})
        self.assertEqual(frame['players'][0],['l',2,1,2,90,False,7000])

    def test_old_record_without_optional_metadata_remains_readable(self):
        frame=show_frame(sexpr('(show 1 ((b) 1 2) ((r 2) 0 0x1 1 2 0 0 0 0))'))
        self.assertNotIn('kicks',frame)
        self.assertNotIn('ball_velocity',frame)

    def test_successful_kick_and_goalkeeper_catch_flags(self):
        frame=show_frame(sexpr('(show 3 ((b) 1 2 0 0) ((l 2) 0 0x3 1 2 0 0 0 0) ((r 1) 0 0x19 48 0 0 0 0 0))'))
        self.assertEqual(frame['kickers'],['l:2'])
        self.assertEqual(frame['catchers'],['r:1'])
        fault=show_frame(sexpr('(show 4 ((b) 1 2 0 0) ((r 1) 0 0x39 48 0 0 0 0 0))'))
        self.assertNotIn('catchers',fault)

    def test_configured_player_type_controls_kickable_radius(self):
        import io
        from replay import parse_replay
        data=parse_replay(io.StringIO('ULG6\n(server_param (ball_size 0.085))\n(player_type (id 2) (player_size 0.4) (kickable_margin 0.9))\n(show 1 ((b) 1 2 0 0) ((l 2) 2 0x1 1 2 0 0 0 0))\n'))
        self.assertAlmostEqual(data['frames'][0]['control_radii']['l:2'],1.385)
