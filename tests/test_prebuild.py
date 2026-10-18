import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from build_store import build_signature,compiled_team,is_build_release,pack_compiled
from github_api import is_arena_release
from cloud_app import Handler

class Prebuild(unittest.TestCase):
    def team(self):return {'name':'A','input_mode':'source','base':'university','source_directory':'','command':'./start.sh','build_id':'7'}
    def storage(self,status='completed'):
        team=self.team();blob=b'compiled archive'
        info={'status':status,'signature':build_signature(team),'compiled_sha256':hashlib.sha256(blob).hexdigest()}
        class Storage:
            def require_private(self):pass
            def release(self,i):return {'name':'arena-build-'+'a'*32,'body':json.dumps({'build_state':info})}
            def assets(self,i):return {'compiled.zip':{'id':8}}
            def read_asset(self,a):return blob
        return Storage(),info
    def test_only_successful_unchanged_build_becomes_binary(self):
        storage,state=self.storage();prepared,blob=compiled_team(storage,self.team())
        self.assertEqual(prepared['input_mode'],'binary');self.assertEqual(prepared['directory'],'bin')
        self.assertEqual(blob,b'compiled archive')
        team=self.team();team['command']='./other.sh'
        with self.assertRaisesRegex(ValueError,'changed'):compiled_team(storage,team)
        for status in ('failed','queued','building'):
            state['status']=status
            with self.assertRaises(ValueError):compiled_team(storage,self.team())
        with self.assertRaisesRegex(ValueError,'before'):compiled_team(storage,dict(self.team(),build_id=''))
    def test_builds_are_not_listed_as_match_tests(self):
        release={'name':'arena-build-'+'a'*32,'tag_name':'untagged-123'}
        self.assertTrue(is_build_release(release));self.assertFalse(is_arena_release(release))
    def test_pack_keeps_runtime_and_materializes_library_aliases(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);runtime=root/'Team'/'src';runtime.mkdir(parents=True)
            (runtime/'start.sh').write_text('#!/bin/sh\n./player\n');(runtime/'player').write_bytes(b'\x7fELFbinary')
            (runtime/'unused.o').write_bytes(b'object')
            lib=root/'.arena-deps'/'install'/'lib';lib.mkdir(parents=True)
            (lib/'librcsc.so.18').write_bytes(b'\x7fELFlibrary');(lib/'librcsc.so').symlink_to('librcsc.so.18')
            blob=pack_compiled({'directory':'Team/src'},root)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                self.assertIn('bin/player',z.namelist());self.assertNotIn('bin/unused.o',z.namelist())
                self.assertEqual(z.read('lib/librcsc.so'),z.read('lib/librcsc.so.18'))
                self.assertNotEqual((z.getinfo('lib/librcsc.so').external_attr>>16)&0o170000,0o120000)
    def test_match_endpoint_reuses_build_and_never_uploads_source(self):
        team=self.team();config={'left':team,'right':{'name':'B','directory':'bin','command':'./start.sh'},'rounds':1,'games_per_round':1,'synch_mode':True}
        boundary='fixture';parts=[]
        for name,content in [('config',json.dumps(config).encode()),('right_file',b'binary')]:
            parts.append(b'--fixture\r\nContent-Disposition: form-data; name="'+name.encode()+b'"\r\n\r\n'+content+b'\r\n')
        payload=b''.join(parts)+b'--fixture--\r\n'
        handler=Handler.__new__(Handler);handler.path='/api/tests';handler.headers={'Content-Length':str(len(payload)),'Content-Type':'multipart/form-data; boundary='+boundary};handler.rfile=io.BytesIO(payload);handler.auth=lambda:True
        sent=[];handler.send=lambda *args:sent.append(args)
        class Storage:
            uploads={}
            def require_private(self):pass
            def json(self,p,method='GET',body=None):return {'id':9}
            def put(self,i,name,blob,ctype=None):self.uploads[name]=blob
        class Workflow:
            def json(self,p,method='GET',body=None):return {'workflow_runs':[]}
        storage=Storage()
        with patch('cloud_app.storage_client',return_value=storage),patch('cloud_app.GitHub',return_value=Workflow()),patch('cloud_app.connection_info',return_value=None),patch('cloud_app.compiled_team',return_value=(dict(team,input_mode='binary',directory='bin'),b'compiled')) as prepared:
            handler.do_POST()
        self.assertEqual(sent[0][0],202);prepared.assert_called_once()
        self.assertEqual(storage.uploads['left.zip'],b'compiled')
        self.assertEqual(json.loads(storage.uploads['config.json'])['left']['input_mode'],'binary')
