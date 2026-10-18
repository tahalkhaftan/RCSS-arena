"""Cloud regression: real RCSS games with supplied modern and older binaries."""
import json,os,tempfile,threading
from pathlib import Path
from app import extract
from presets import catalog,archive_bytes
from runner import run_match

teams={t['id']:t for t in catalog()}
root=Path('runtime-verification').resolve();root.mkdir(exist_ok=True)
# These public bundled teams need no GitHub credentials while running.
for key in ('GITHUB_TOKEN','STORAGE_TOKEN','ARENA_USER','ARENA_PASSWORD'):os.environ.pop(key,None)
results=[]
for number,(left,right) in enumerate([('IAU_Center','yushan2025'),('CambysesI','AITech-2D'),('AITech-2D','CYRUS')],1):
    folder=root/str(number);config={'synch_mode':True}
    for side,ident in [('left',left),('right',right)]:
        team=teams[ident];extract(archive_bytes(team),folder/'teams'/side)
        config[side]={key:team[key] for key in ('name','directory','command')}
    print('Real match: '+left+' vs '+right,flush=True)
    last=[-1]
    def progress(info):
        if info['cycle']//1000!=last[0]:
            last[0]=info['cycle']//1000
            print('cycle='+str(info['cycle'])+' players='+str(info.get('left_players',0))+'/'+str(info.get('right_players',0)),flush=True)
    try:
        result=run_match(config,folder/'teams',folder/'logs',threading.Event(),progress)
        if result['last_cycle']<6000:raise RuntimeError('Incomplete real match')
        results.append({'left':left,'right':right,**result})
        print('PASS: completed 6000 cycles with 11 players on each side; score '+str(result['left_score'])+':'+str(result['right_score']),flush=True)
    except Exception:
        for name in ('server.log','left.log','right.log'):
            path=folder/'logs'/name
            if path.exists():print(name+':\n'+path.read_text(errors='replace')[-6000:],flush=True)
        raise
    finally:
        (root/'results.json').write_text(json.dumps(results,indent=2))
