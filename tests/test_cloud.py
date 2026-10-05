import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud_app import state,CACHE
from github_api import SafeRedirect
from urllib.request import Request
class FakeGitHub:
    def release(self,i):return {'tag_name':'arena-test','created_at':'2026-10-04'}
    def assets(self,i):return {'config.json':{'id':1}}
    def read_asset(self,a):return b'{"rounds":1,"games_per_round":5}'
    def json(self,p):return {'workflow_runs':[{'display_title':'Arena 7','status':'completed','conclusion':'failure','html_url':'https://github.com/test/actions/runs/1'}]}
class Cloud(unittest.TestCase):
    def test_failure_before_runner_is_visible(self):
        CACHE.clear();s=state(FakeGitHub(),7);self.assertEqual(s['status'],'failed');self.assertFalse(s['archive_ready'])
    def test_atomic_live_state_does_not_depend_on_asset_replacement(self):
        import json
        live={'id':'7','status':'running','matches':[], 'progress':{'cycle':1234},'total':1}
        class Storage(FakeGitHub):
            def release(self,i): return dict(super().release(i),body=json.dumps({'arena_state':live}))
            def read_asset(self,a): raise AssertionError('Live state must not download a stale report')
            def json(self,p): return {'workflow_runs':[]}
        CACHE.clear(); result=state(Storage(),7)
        self.assertEqual(result['progress']['cycle'],1234)
        self.assertEqual(result['status'],'running')
        self.assertFalse(result['archive_ready'])

    def test_strip_secret_on_asset_redirect(self):
        req=Request('https://api.github.com/test',headers={'Authorization':'Bearer secret'})
        redirect=SafeRedirect().redirect_request(req,None,302,'',{},'https://release-assets.githubusercontent.com/test')
        self.assertIsNone(redirect.get_header('Authorization'))
if __name__=='__main__':unittest.main()

class PublicStorage(unittest.TestCase):
    def test_public_storage_is_rejected(self):
        from github_api import GitHub
        gh=GitHub(repo='owner/data',token='test-token')
        with patch.object(gh,'json',return_value={'private':False}):
            with self.assertRaisesRegex(ValueError,'private'):gh.require_private()
        with patch.object(gh,'json',return_value={'private':True}):gh.require_private()

    def test_storage_uses_separate_repository_and_token(self):
        from github_api import storage_client
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'owner/public','GITHUB_TOKEN':'render-token','STORAGE_REPOSITORY':'owner/private','STORAGE_TOKEN':'storage-token'}):
            gh=storage_client()
            self.assertEqual(gh.repo,'owner/private')
            self.assertEqual(gh.token,'storage-token')

    def test_workflow_status_is_read_from_public_project(self):
        class Storage(FakeGitHub):
            def json(self,p):raise AssertionError('Actions API must use public workflow repository')
        CACHE.clear()
        result=state(Storage(),7,FakeGitHub())
        self.assertEqual(result['status'],'failed')
