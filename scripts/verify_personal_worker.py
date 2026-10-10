"""Exercise the site -> outbound Worker -> local RCSS pipeline with a real match."""
import io,json,os,socket,sys,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from test_personal_worker import Personal
from personal_worker import PersonalLive
from runner import run_job
import app
from live import RELAY

h=Personal(methodName='test_worker_auth_and_local_catalog_without_github');h.setUp()
output=Path('personal-verification');output.mkdir(exist_ok=True)
try:
    os.environ['MATCH_TIMEOUT_SECONDS']='600'
    config={'rounds':1,'games_per_round':1,'synch_mode':True,
            'left':{'name':'AITech-2D','directory':'.','command':'./localStartAll','preset_id':'AITech-2D'},
            'right':{'name':'CYRUS','directory':'.','command':'./localStartAll','preset_id':'CYRUS'}}
    def local_run(job,write):
        live=PersonalLive(h.client,job['state']['id']);job['live']=live;job['state']['execution']='personal';job['state']['storage_directory']=str(job['root'])
        try:run_job(job,write)
        finally:live.close()
    blob,ctype=h.multipart({'config':json.dumps(config).encode()})
    with patch.object(app,'run_job',local_run),patch('cloud_app.GitHub',side_effect=AssertionError('Personal match must not use GitHub')):
        ident=json.loads(h.request('/personal/api/tests',blob,ctype))['id']
        mon=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);mon.settimeout(.3)
        local_frame=False;live_frame=False;deadline=time.monotonic()+750;last=-1
        try:
            while time.monotonic()<deadline:
                state=json.loads(h.request('/personal/api/tests/'+ident))
                cycle=state.get('progress',{}).get('cycle',0)
                if cycle//1000!=last:last=cycle//1000;print('Personal cycle='+str(cycle),flush=True)
                if not local_frame:
                    mon.sendto(b'(dispinit version 4)\0',('127.0.0.1',6000))
                    try:local_frame=mon.recvfrom(65535)[0].startswith(b'(show ')
                    except socket.timeout:pass
                _,payload=RELAY.wait('personal:'+ident,0,.1);live_frame=live_frame or bool(payload)
                if state.get('archive_ready'):break
                time.sleep(2)
            else:raise RuntimeError('Personal match exceeded verification deadline')
        finally:
            try:mon.sendto(b'(dispbye)\0',('127.0.0.1',6000))
            except OSError:pass
            mon.close()
        assert state['status']=='completed',state
        assert state['matches'][0]['last_cycle']>=6000
        assert local_frame and live_frame
        assert (app.DATA/ident/'logs.zip').exists()
        assert state['execution']=='personal'
        logs=h.request('/personal/api/tests/'+ident+'/logs.zip')
        with zipfile.ZipFile(io.BytesIO(logs)) as z:
            assert z.read('logs/round-001-game-001/match.rcg')
            assert z.read('logs/round-001-game-001/match.rcl')
        assert h.request('/personal/api/tests/'+ident+'/replay/1/1')
        (output/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
        h.wait_for_cleanup()
        print('PASS: real complete match on worker, site live frames, simultaneous local UDP monitor, replay, local storage and streamed ZIP without GitHub storage',flush=True)
finally:
    for j in app.JOBS.values():
        j['cancel'].set()
        if j.get('thread'):j['thread'].join(timeout=8)
    h.tearDown()
