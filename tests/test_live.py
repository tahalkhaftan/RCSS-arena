import base64,io,json,os,threading,time,unittest,urllib.error,urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from live import LivePublisher,Relay,issue_token,valid_token,connection_info,RELAY
from cloud_app import Handler

FRAME={'cycle':23,'players':[['l',1,0,0,0,True]],'ball':[1,2],'score':[0,0],'names':['A','B'],'mode':'3'}
class Live(unittest.TestCase):
 def test_job_bound_expiring_token_and_destination(self):
  with patch.dict(os.environ,{'ARENA_PASSWORD':'fixture','RENDER_EXTERNAL_URL':'https://arena.example'}):
   token=issue_token(42)
   self.assertTrue(valid_token(42,token));self.assertFalse(valid_token(43,token))
   self.assertFalse(valid_token(42,issue_token(42,int(time.time())-1)))
   self.assertFalse(valid_token(42,'bad'))
   self.assertEqual(connection_info(42)['url'],'https://arena.example/api/live/42')
 def test_expired_feed_waits_instead_of_spinning(self):
  relay=Relay();relay.events['7']=(1,{},time.monotonic()-30)
  start=time.monotonic();self.assertEqual(relay.wait('7',0,.05),(0,None))
  self.assertGreaterEqual(time.monotonic()-start,.04)
 def test_live_http_pipeline_is_authenticated_and_subsecond_locally(self):
  with patch.dict(os.environ,{'ARENA_USER':'fixture','ARENA_PASSWORD':'fixture'}):
   RELAY.events.clear();server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
   threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
   publisher=None;stream=None
   try:
    with self.assertRaises(urllib.error.HTTPError) as denial:urllib.request.urlopen(base+'/api/tests/42/live',timeout=2)
    self.assertEqual(denial.exception.code,401)
    req=urllib.request.Request(base+'/api/live/42',data=b'{}',headers={'Authorization':'Bearer bad'})
    with self.assertRaises(urllib.error.HTTPError) as denial:urllib.request.urlopen(req,timeout=2)
    self.assertEqual(denial.exception.code,403)
    auth='Basic '+base64.b64encode(b'fixture:fixture').decode()
    stream=urllib.request.urlopen(urllib.request.Request(base+'/api/tests/42/live',headers={'Authorization':auth}),timeout=3)
    self.assertEqual(stream.headers['Content-Type'],'text/event-stream; charset=utf-8')
    self.assertEqual(stream.readline(),b'retry: 1000\n');stream.readline()
    publisher=LivePublisher({'url':base+'/api/live/42','token':issue_token(42)},allow_local=True)
    start=time.monotonic();publisher.submit(1,2,FRAME)
    line=stream.readline();elapsed=time.monotonic()-start
    self.assertTrue(line.startswith(b'data: '));self.assertLess(elapsed,2)
    event=json.loads(line[6:]);self.assertEqual(event['frames'][0]['game'],2);self.assertEqual(event['frames'][0]['frame']['cycle'],23)
   finally:
    if publisher:publisher.close()
    if stream:stream.close()
    server.shutdown();server.server_close()
 def test_slow_network_does_not_block_runner_or_grow_queue(self):
  with patch('live.LivePublisher.run'):
   publisher=LivePublisher({'url':'https://example.test/api/live/1','token':'fixture'})
   start=time.monotonic()
   for i in range(10000):publisher.submit(1,1,FRAME)
   self.assertLess(time.monotonic()-start,.5);self.assertLessEqual(len(publisher.queue),12);publisher.close()
 def test_redirect_cannot_receive_live_token(self):
  from live import NoRedirect
  self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))
