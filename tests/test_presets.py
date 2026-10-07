import hashlib
import io
import json
import unittest
import zipfile
from presets import ROOT,catalog,resolve_teams,archive_bytes

class Presets(unittest.TestCase):
    def test_every_archive_and_selected_start_script(self):
        teams=catalog()
        self.assertEqual(len(teams),8)
        for t in teams:
            blob=archive_bytes(t)
            self.assertEqual(hashlib.sha256(blob).hexdigest(),t['sha256'])
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                scripts=[n for n in z.namelist() if n.rsplit('/',1)[-1]=='localStartAll']
                chosen=t['directory']+t['command'][2:]
                self.assertIn(chosen,z.namelist())
                if scripts:self.assertIn(chosen,scripts)
                else:self.assertTrue(chosen.endswith('/start.sh'))

    def test_mixed_preset_and_upload_preserves_personal_upload(self):
        config={'left':{'preset_id':'hades2d2025','directory':'wrong','command':'wrong'},'right':{'name':'Mine','directory':'bin/','command':'./start.sh'}}
        blobs=resolve_teams(config,{'right_file':b'personal-zip','left_file':b'ignored'})
        self.assertEqual(config['left']['directory'],'hades2d/bin/')
        self.assertEqual(config['left']['command'],'./start.sh')
        self.assertEqual(blobs['right'],b'personal-zip')
        self.assertEqual(config['right']['command'],'./start.sh')

    def test_two_presets_need_no_uploaded_files(self):
        config={side:{'preset_id':'AITech-2D'} for side in ('left','right')}
        blobs=resolve_teams(config,{})
        self.assertEqual(blobs['left'],blobs['right'])
        self.assertEqual(config['left']['command'],'./localStartAll')

    def test_unknown_id_cannot_read_arbitrary_path(self):
        with self.assertRaisesRegex(ValueError,'Unknown preset'):
            resolve_teams({'left':{'preset_id':'../github_api.py'}},{})

    def test_http_catalog_and_dispatch_without_uploaded_zips(self):
        import base64,os,threading,urllib.request
        from http.server import ThreadingHTTPServer
        from unittest.mock import patch
        from cloud_app import Handler
        uploads={};dispatch=[]
        class Storage:
            def require_private(self):pass
            def json(self,path,method='GET',body=None):
                if path=='/releases':return {'id':77}
            def put(self,ident,name,data,*args):uploads[name]=data
        class Workflow:
            def json(self,path,method='GET',body=None):
                if method=='GET':return {'workflow_runs':[]}
                dispatch.append(body)
        config={'left':{'preset_id':'AITech-2D'},'right':{'preset_id':'CambysesI'},'rounds':1,'games_per_round':1,'synch_mode':False}
        payload=('--fixture\r\nContent-Disposition: form-data; name="config"\r\n\r\n'+json.dumps(config)+'\r\n--fixture--\r\n').encode()
        with patch.dict(os.environ,{'ARENA_USER':'test','ARENA_PASSWORD':'test','GITHUB_REF':'main','RENDER_EXTERNAL_URL':'https://arena.example'}),patch('cloud_app.storage_client',return_value=Storage()),patch('cloud_app.GitHub',return_value=Workflow()):
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def request(path,data=None):
                headers={'Authorization':'Basic '+base64.b64encode(b'test:test').decode(),'Content-Type':'multipart/form-data; boundary=fixture'}
                with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=data,headers=headers)) as r:return json.load(r)
            try:
                self.assertEqual(len(request('/api/teams')),8)
                self.assertEqual(request('/api/tests',payload)['id'],'77')
                saved=json.loads(uploads['config.json'])
                self.assertEqual(saved['left']['command'],'./localStartAll')
                self.assertEqual(saved['right']['directory'],'CambysesI/')
                self.assertEqual(set(uploads),{'left.zip','right.zip','config.json','live.json'})
                self.assertEqual(json.loads(uploads['live.json'])['url'],'https://arena.example/api/live/77')
                self.assertNotIn('token',saved)
                self.assertEqual(dispatch[0]['inputs']['release_id'],'77')
            finally:server.shutdown();server.server_close()
