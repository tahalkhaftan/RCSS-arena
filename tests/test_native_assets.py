import gzip,io,json,tempfile,unittest,zipfile
from pathlib import Path
from native_assets import cloud_rcg,local_rcg,rcg_asset_name
from github_api import GitHub
from personal_bridge import ALLOWED

LOG=b'ULG5\n(team 0 RealLeft RealRight 3 1)\n(show 42 ((b) 4 5 0 0))\n'
class NativeAssets(unittest.TestCase):
 def test_separate_original_asset_is_not_rebuilt_from_browser_json(self):
  class Storage:
   def require_private(self):pass
   def release(self,i):return {'name':'arena-'+'a'*32}
   def assets(self,i):return {rcg_asset_name(1,2):{'id':7}}
   def open(self,*a,**k):return io.BytesIO(gzip.compress(LOG))
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'game.rcg';cloud_rcg(Storage(),7,1,2,dest);self.assertEqual(dest.read_bytes(),LOG)
 def test_existing_archive_uses_exact_selected_game(self):
  archive=io.BytesIO()
  with zipfile.ZipFile(archive,'w') as z:
   z.writestr('logs/round-001-game-001/match.rcg',b'wrong game')
   z.writestr('logs/round-002-game-003/server-logs/match.rcg.gz',gzip.compress(LOG))
  class Storage:
   def require_private(self):pass
   def release(self,i):return {'name':'arena-'+'a'*32}
   def assets(self,i):return {'logs.zip':{'id':8}}
   def open(self,*a,**k):return io.BytesIO(archive.getvalue())
  with tempfile.TemporaryDirectory() as d:
   dest=Path(d)/'game.rcg';cloud_rcg(Storage(),7,2,3,dest);self.assertEqual(dest.read_bytes(),LOG)
 def test_personal_path_and_local_log_location(self):
  ident='a'*32;self.assertTrue(ALLOWED.fullmatch(f'/api/tests/{ident}/rcg/1/2'))
  self.assertFalse(ALLOWED.fullmatch(f'/api/tests/{ident}/rcg/../../etc/passwd'))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'logs/round-001-game-002/server-logs/match.rcg';p.parent.mkdir(parents=True);p.write_bytes(LOG)
   self.assertEqual(local_rcg({'root':Path(d)},1,2),p)
 def test_asset_pagination_finds_late_games(self):
  gh=object.__new__(GitHub);calls=[]
  def get(path):
   calls.append(path)
   return [{'name':str(n)} for n in range(100)] if len(calls)==1 else [{'name':'late.rcg.gz'}]
  gh.json=get
  self.assertIn('late.rcg.gz',gh.assets(7));self.assertIn('page=2',calls[1])
