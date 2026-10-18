"""Real hosted-runner regression for OCL capture, CSV joins and replay isolation."""
import csv,json,os,threading,zipfile
from pathlib import Path
from app import extract
from presets import catalog,archive_bytes
from runner import run_job

root=Path('offline-verification').resolve();root.mkdir(exist_ok=True)
teams={t['id']:t for t in catalog()}
config={'synch_mode':True,'offline_logging':True,'rounds':1,'games_per_round':1}
for side,ident in [('left','AITech-2D'),('right','CYRUS')]:
    team=teams[ident];extract(archive_bytes(team),root/'teams'/side)
    config[side]={key:team[key] for key in ('name','directory','command')}
state={'id':'offline-verification','config':config,'matches':[]}
job={'state':state,'root':root,'cancel':threading.Event()}
for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_USER','ARENA_PASSWORD'):os.environ.pop(key,None)
def write(_):
    (root/'results.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
run_job(job,write)
assert state['status']=='completed',state
match=state['matches'][0];assert match['last_cycle']>=6000
report=match['dataset'];assert report['status']=='completed',report
assert report['rows']>1000,report
assert report['execution_confirmed']>100,report
assert report['ocl_joined_rows']>100,report
folder=root/'logs/round-001-game-001/server-logs'
with (folder/'decisions.csv').open() as f:
    for row in csv.DictReader(f):
        if row['ocl_before_cycle']:assert int(row['ocl_before_cycle'])<int(row['cycle'])
with zipfile.ZipFile(root/'logs.zip') as z:
    prefix='logs/round-001-game-001/server-logs/'
    for name in ('match.rcg','match.rcl','decisions.csv','dataset-metadata.json'):assert prefix+name in z.namelist()
    assert any(n.startswith(prefix+'ocl-log/') and n.endswith('.ocl') for n in z.namelist())
assert match.get('replay_available')
print('PASS: complete real match, OCL, confirmed commands, CSV prior-input joins, archive and replay')
print(json.dumps(report,ensure_ascii=False,indent=2))
