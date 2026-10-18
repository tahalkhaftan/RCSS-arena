"""Run a complete real match via the portal HTTP API on a cloud test instance."""
import base64
import io
import json
import os
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from http.server import ThreadingHTTPServer
from cloud_app import Handler
from github_api import storage_client
from analysis import analyze

storage=storage_client();storage.require_private()
assets=storage.assets(int(os.environ['SOURCE_RELEASE_ID']))
config=json.loads(storage.read_asset(assets['config.json']))
config.update(rounds=1,games_per_round=1)
boundary=uuid.uuid4().hex
parts=[]
for field,name,blob in [('config',None,json.dumps(config).encode()),('left_file','left.zip',storage.read_asset(assets['left.zip'])),('right_file','right.zip',storage.read_asset(assets['right.zip']))]:
    disposition='Content-Disposition: form-data; name="'+field+'"'+('; filename="'+name+'"' if name else '')
    parts.append(('--'+boundary+'\r\n'+disposition+'\r\n\r\n').encode()+blob+b'\r\n')
payload=b''.join(parts)+('--'+boundary+'--\r\n').encode()
os.environ['ARENA_USER']='cloud-verification'
os.environ['ARENA_PASSWORD']=uuid.uuid4().hex
os.environ['GITHUB_TOKEN']=os.environ['STORAGE_TOKEN']
os.environ['GITHUB_REF']='main'
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
auth='Basic '+base64.b64encode((os.environ['ARENA_USER']+':'+os.environ['ARENA_PASSWORD']).encode()).decode()
def request(path,data=None,ctype=None):
    headers={'Authorization':auth}
    if ctype:headers['Content-Type']=ctype
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=data,headers=headers),timeout=120) as response:return response.read()
try:
    ident=json.loads(request('/api/tests',payload,'multipart/form-data; boundary='+boundary))['id']
    print('Verification match release: '+ident,flush=True)
    observed=False;deadline=time.monotonic()+1000
    while time.monotonic()<deadline:
        state=json.loads(request('/api/tests/'+ident))
        cycle=state.get('progress',{}).get('cycle',0)
        observed |= cycle>0
        print('Portal status: '+state['status']+'; cycle: '+str(cycle),flush=True)
        if state['status'] in ('completed','failed','cancelled') and not state.get('publication_pending'):break
        time.sleep(10)
    else:raise RuntimeError('Cloud verification exceeded its time limit; check the match workflow')
    if state['status']!='completed':raise RuntimeError('Real match failed; details retained in private Arena report')
    if not observed:raise RuntimeError('Live positive cycle was not observed through the portal')
    matches=state['matches']
    with zipfile.ZipFile(io.BytesIO(request('/api/tests/'+ident+'/logs.zip'))) as archive,tempfile.TemporaryDirectory() as directory:
        assert archive.testzip() is None
        for match in matches:
            prefix=f"logs/round-{match['round']:03d}-game-{match['game']:03d}/"
            assert archive.read(prefix+'match.rcl')
            path=Path(directory)/'match.rcg';path.write_bytes(archive.read(prefix+'match.rcg'))
            parsed=analyze(path)
            assert parsed['natural_end'] and parsed['last_cycle']>=6000
            assert parsed['scores']==[match['left_score'],match['right_score']]
            assert min(parsed['max_players'].values())==11
    rel=storage.release(ident);body=json.loads(rel.get('body') or '{}')
    body['verification']={'http_upload':True,'live_cycle':True,'complete_real_match':True,'http_zip_download':True,'rcg_rcl_validated':True}
    storage.json('/releases/'+ident,'PATCH',{'body':json.dumps(body)})
    print('PASS: HTTP upload, real complete match, live cycle, result, ZIP, RCG and RCL.',flush=True)
finally:server.shutdown();server.server_close()
