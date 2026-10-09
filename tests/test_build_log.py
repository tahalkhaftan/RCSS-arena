import io,unittest
from unittest.mock import patch
from cloud_app import Handler

class BuildLog(unittest.TestCase):
    def test_authenticated_portal_streams_whole_build_log(self):
        blob=(b'full compiler output\n'*10000)
        class Storage:
            def require_private(self):pass
            def release(self,i):return {'name':'arena-'+'a'*32}
            def assets(self,i):return {'build-left.log':{'id':44,'size':len(blob)}}
            def open(self,p,binary=False):
                assert p=='/releases/assets/44' and binary
                return io.BytesIO(blob)
        handler=Handler.__new__(Handler);handler.path='/api/tests/7/build-log/left';handler.wfile=io.BytesIO();handler.auth=lambda:True
        statuses=[];handler.send_response=statuses.append;handler.send_header=lambda *args:None;handler.end_headers=lambda:None
        with patch('cloud_app.storage_client',return_value=Storage()),patch('cloud_app.GitHub'):handler.do_GET()
        self.assertEqual(statuses,[200]);self.assertEqual(handler.wfile.getvalue(),blob)

    def test_log_route_requires_authentication(self):
        handler=Handler.__new__(Handler);handler.path='/api/tests/7/build-log/left';handler.auth=lambda:False
        with patch('cloud_app.storage_client') as storage:handler.do_GET();storage.assert_not_called()
