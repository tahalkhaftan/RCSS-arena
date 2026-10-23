import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from analysis import sexpr
from player_rcg import export_players, selection
from runner import run_job


LOG = 'ULG5\n(team 0 A B 0 0)\n(playmode 0 play_on)\n(show 1 ((b) 1 2 0 0) ((l 1) 0 0x1 -20 0 0 0 0 0) ((l 2) 0 0x1 -10 0 0 0 0 0) ((r 1) 0 0x1 20 0 0 0 0 0))\n(playmode 6000 time_over)\n'


class PlayerRCG(unittest.TestCase):
    def test_tracks_preserve_ball_metadata_cycles_and_original(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'match.rcg'
            source.write_text(LOG)
            paths = export_players(source, {'player_rcg': {'enabled': True, 'left': [2], 'right': [1]}})
            self.assertEqual(len(paths), 2)
            self.assertEqual(source.read_text(), LOG)
            for path, wanted in zip(paths, [['l', '2'], ['r', '1']]):
                data = (source.parent/path).read_text()
                self.assertIn('(playmode 6000 time_over)', data)
                show = sexpr(next(line for line in data.splitlines() if line.startswith('(show ')))
                self.assertEqual(show[1], '1')
                self.assertEqual(show[2][0], ['b'])
                self.assertEqual([p[0] for p in show[3:]], [wanted])

    def test_invalid_numbers_empty_selection_and_disabled_state(self):
        for value in (True, {'enabled': True}, {'enabled': True, 'left': [True]}, {'enabled': True, 'left': [12]}, {'enabled': True, 'right': ['1']}):
            with self.assertRaises(ValueError):
                selection(value)
        self.assertEqual(selection({'enabled': False, 'left': [1]}), {'enabled': False, 'left': [], 'right': []})
        self.assertEqual(selection(None), {'enabled': False, 'left': [], 'right': []})

    def test_zip_contains_full_rcg_and_selected_players_even_on_plus(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            def match(config, teams, folder, *args, **kwargs):
                folder.mkdir(parents=True)
                (folder/'match.rcg').write_text(LOG)
                (folder/'match.rcl').write_text('commands')
                (folder/'server.log').write_text('private debug log')
                return {'status': 'completed', 'left_score': 0, 'right_score': 0}
            config = {'rounds': 1, 'games_per_round': 1, 'left': {'name': 'A'}, 'right': {'name': 'B'}, 'export_tier': 'plus', 'player_rcg': {'enabled': True, 'left': [1, 2], 'right': [1]}}
            state = {'config': config, 'matches': []}
            def write(_):
                (root/'results.json').write_text(json.dumps(state))
            with patch('runner.run_match', side_effect=match):
                run_job({'root': root, 'state': state, 'cancel': threading.Event()}, write)
            with zipfile.ZipFile(root/'logs.zip') as z:
                self.assertEqual(z.read('logs/round-001-game-001/match.rcg').decode(), LOG)
                self.assertEqual(len([p for p in z.namelist() if '/player-rcg/' in p]), 3)
                self.assertFalse(any(p.endswith('.log') for p in z.namelist()))


if __name__ == '__main__':
    unittest.main()
