"""Exercise private draft identity through the real HTTP result/download routes."""
import base64
import io
import json
import os
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from cloud_app import Handler, CACHE

class PortalHTTP(unittest.TestCase):
    def test_untagged_release_list_results_download_and_cancel(self):
        report={'id':'7','status':'completed','matches':[], 'total':1}
        release={'id':7,'tag_name':'untagged-123','name':'arena-'+'a'*32,
                 'created_at':'2026-10-05','body':json.dumps({'arena_state':report})}
        class Storage:
            cancelled=False
            def require_private(self): pass
            def release(self,ident): return release
            def assets(self,ident): return {'logs.zip':{'id':8,'size':3}}
            def json(self,path): return [release, {'id':9,'tag_name':'arena-diagnostic-abc','created_at':'2026-10-06'}]
            def open(self,*args,**kwargs): return io.BytesIO(b'zip')
            def put(self,*args): self.cancelled=True
        storage=Storage();CACHE.clear()
        with patch.dict(os.environ,{'ARENA_USER':'fixture','ARENA_PASSWORD':'fixture-password'}),patch('cloud_app.storage_client',return_value=storage),patch('cloud_app.GitHub',return_value=storage):
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,method='GET'):
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,method=method,
                    headers={'Authorization':'Basic '+base64.b64encode(b'fixture:fixture-password').decode()})
                with urllib.request.urlopen(req,timeout=5) as response:return response.read()
            try:
                self.assertEqual([x['id'] for x in json.loads(request('/api/tests'))],['7'])
                self.assertEqual(json.loads(request('/api/tests/7'))['status'],'completed')
                self.assertEqual(request('/api/tests/7/logs.zip'),b'zip')
                self.assertEqual(json.loads(request('/api/tests/7/cancel','POST'))['status'],'cancellation_requested')
                self.assertTrue(storage.cancelled)
            finally: server.shutdown();server.server_close();thread.join(timeout=2)
