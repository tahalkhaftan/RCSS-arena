import base64,io,json,os,socket,tempfile,threading,time,unittest,urllib.request,zipfile,uuid
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import app,cloud_app,personal_bridge
from personal_worker import WorkerClient,PersonalLive,local_handler
from runner import run_job
from test_runner import FAKE

class Personal(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.env=patch.dict(os.environ,{'ARENA_USER':'owner','ARENA_PASSWORD':'secret','MATCH_TIMEOUT_SECONDS':'10'});self.env.start()
  self.auth='Basic '+base64.b64encode(b'owner:secret').decode()
  self.data_patch=patch.object(app,'DATA',self.root/'matches');self.data_patch.start();app.DATA.mkdir();app.JOBS.clear()
  self.bridge_patch=patch.object(personal_bridge,'BRIDGE',personal_bridge.Bridge());self.bridge_patch.start()
  self.cloud_bridge_patch=patch.object(cloud_app,'BRIDGE',personal_bridge.BRIDGE);self.cloud_bridge_patch.start()
  self.cloud=ThreadingHTTPServer(('127.0.0.1',0),cloud_app.Handler);threading.Thread(target=self.cloud.serve_forever,daemon=True).start()
  self.site='http://127.0.0.1:'+str(self.cloud.server_port)
  self.client=WorkerClient(self.site,personal_bridge.worker_token())
  self.local=ThreadingHTTPServer(('127.0.0.1',0),local_handler(self.root));threading.Thread(target=self.local.serve_forever,daemon=True).start()
  self.stop=threading.Event();self.machine=uuid.uuid4().hex
  def loop():
   while not self.stop.is_set():
    try:
     self.client.json('heartbeat',{'machine_id':self.machine,'name':'Ubuntu-test','data_dir':str(self.root)})
     task=self.client.json('poll',{'machine_id':self.machine})
     if task:threading.Thread(target=self.client.serve_call,args=(task,self.local.server_port,self.auth),daemon=True).start()
    except Exception:time.sleep(.05)
  self.poll=threading.Thread(target=loop,daemon=True);self.poll.start()
  deadline=time.monotonic()+3
  while not personal_bridge.BRIDGE.online() and time.monotonic()<deadline:time.sleep(.02)
 def tearDown(self):
  self.stop.set();self.cloud.shutdown();self.local.shutdown();self.cloud.server_close();self.local.server_close()
  self.poll.join(timeout=12)
  for p in (self.cloud_bridge_patch,self.bridge_patch,self.data_patch,self.env):p.stop()
  app.JOBS.clear();self.tmp.cleanup()
 def wait_for_cleanup(self):
  deadline=time.monotonic()+3
  while personal_bridge.BRIDGE.calls and time.monotonic()<deadline:time.sleep(.01)
  self.assertFalse(personal_bridge.BRIDGE.calls)
 def request(self,path,data=None,ctype='application/json'):
  with urllib.request.urlopen(urllib.request.Request(self.site+path,data=data,headers={'Authorization':self.auth,'Content-Type':ctype}),timeout=15) as f:return f.read()
 def multipart(self,fields):
  boundary=uuid.uuid4().hex
  blob=b''.join(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+k+'"\r\n\r\n').encode()+v+b'\r\n' for k,v in fields.items())+('--'+boundary+'--\r\n').encode()
  return blob,'multipart/form-data; boundary='+boundary
 def test_worker_auth_and_local_catalog_without_github(self):
  with self.assertRaises(urllib.error.HTTPError):WorkerClient(self.site,'wrong').json('heartbeat',{'machine_id':self.machine})
  with patch('cloud_app.GitHub',side_effect=AssertionError('Personal mode must not use GitHub')):
   state=json.loads(self.request('/api/personal/status'));self.assertTrue(state['online'])
   teams=json.loads(self.request('/personal/api/teams'));self.assertGreater(len(teams),2)
   self.wait_for_cleanup()
 def test_local_source_build_reused_and_settings_checked(self):
  def build(team,root,log,cancel,stage):
   stage('Building test source');(root/'bin').mkdir();(root/'bin/start.sh').write_text('#!/bin/bash\nexit 0\n');team['directory']='bin';log.write_text('Build successful')
  with patch('team_build.build_team',side_effect=build) as builder:
   self.local.RequestHandlerClass=local_handler(self.root)
  team={'name':'source','directory':'.','command':'./start.sh','input_mode':'source','base':'school','source_directory':'.'}
  archive=io.BytesIO()
  with zipfile.ZipFile(archive,'w') as z:z.writestr('CMakeLists.txt','project(test)')
  blob,ctype=self.multipart({'config':json.dumps({'team':team}).encode(),'source_file':archive.getvalue()})
  ident=json.loads(self.request('/personal/api/builds',blob,ctype))['id'];deadline=time.monotonic()+3
  while time.monotonic()<deadline:
   state=json.loads(self.request('/personal/api/builds/'+ident))
   if state['status'] in ('completed','failed'):break
   time.sleep(.05)
  self.assertEqual(state['status'],'completed');self.assertEqual(builder.call_count,1)
  self.assertEqual(self.request('/personal/api/builds/'+ident+'/log'),b'Build successful')
  with zipfile.ZipFile(self.root/'builds'/ident/'compiled.zip') as z:self.assertIn('bin/start.sh',z.namelist())
  team['build_id']=ident;team['command']='./changed.sh'
  config={'left':team,'right':dict(team),'rounds':1,'games_per_round':1,'synch_mode':True}
  blob,ctype=self.multipart({'config':json.dumps(config).encode()})
  with self.assertRaises(urllib.error.HTTPError) as e:self.request('/personal/api/tests',blob,ctype)
  self.assertIn(b'settings changed',e.exception.read());self.assertEqual(builder.call_count,1)
  self.wait_for_cleanup()
 def test_complete_local_match_stream_replay_and_download(self):
  fake=self.root/'server';fake.write_text(FAKE);fake.chmod(0o700)
  config={'rounds':1,'games_per_round':1,'synch_mode':False}
  fields={}
  for side in ('left','right'):
   b=io.BytesIO()
   with zipfile.ZipFile(b,'w') as z:z.writestr('start.sh','#!/bin/bash\ntouch ../../logs/round-001-game-001/'+side+'-ready\n')
   fields[side+'_file']=b.getvalue();config[side]={'name':side,'directory':'.','command':'./start.sh'}
  fields['config']=json.dumps(config).encode();blob,ctype=self.multipart(fields)
  def local_run(job,write):
   live=PersonalLive(self.client,job['state']['id']);job['live']=live
   try:run_job(job,write)
   finally:live.close()
  with patch.dict(os.environ,{'RCSSSERVER':str(fake)}),patch.object(app,'run_job',local_run),patch('cloud_app.GitHub',side_effect=AssertionError('No cloud match')):
   ident=json.loads(self.request('/personal/api/tests',blob,ctype))['id'];deadline=time.monotonic()+10
   while time.monotonic()<deadline:
    state=json.loads(self.request('/personal/api/tests/'+ident))
    if state.get('archive_ready'):break
    time.sleep(.1)
   self.assertEqual(state['status'],'completed');self.assertTrue((app.DATA/ident/'logs.zip').is_file())
   with zipfile.ZipFile(io.BytesIO(self.request('/personal/api/tests/'+ident+'/logs.zip'))) as z:self.assertIn('logs/round-001-game-001/match.rcg',z.namelist())
   with urllib.request.urlopen(urllib.request.Request(self.site+'/personal/api/tests/'+ident+'/replay/1/1',headers={'Authorization':self.auth}),timeout=10) as f:
    import gzip
    self.assertTrue(json.loads(gzip.decompress(f.read()))['frames'])
   from live import RELAY
   seq,payload=RELAY.wait('personal:'+ident,0,1);self.assertIsNotNone(payload)
   self.assertEqual(json.loads(self.request('/personal/api/tests'))[0]['id'],ident)
   large=os.urandom(3*1024*1024+17);(app.DATA/ident/'logs.zip').write_bytes(large)
   self.assertEqual(self.request('/personal/api/tests/'+ident+'/logs.zip'),large)
   self.wait_for_cleanup()
if __name__=='__main__':unittest.main()
