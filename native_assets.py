"""Stream original per-game RCG into the desktop; never reconstruct it from JSON."""
import gzip,shutil,tempfile,zipfile
from pathlib import Path


def rcg_asset_name(r,g):return f'round-{r:03d}-game-{g:03d}.rcg.gz'

def local_rcg(job,r,g):
    folder=job['root']/'logs'/f'round-{r:03d}-game-{g:03d}'
    for sub in (folder/'server-logs',folder):
        for name in ('match.rcg','match.rcg.gz'):
            path=sub/name
            if path.is_file():return path
    raise LookupError('The original RCG is not available yet.')

def copy_stream(stream,destination):
    while True:
        chunk=stream.read(65536)
        if not chunk:break
        if shutil.disk_usage(Path(destination.name).parent).free<64*1024**2:raise ValueError('Not enough temporary disk space')
        destination.write(chunk)

def cloud_rcg(gh,ident,r,g,path):
    from github_api import is_arena_release
    gh.require_private()
    if not is_arena_release(gh.release(ident)):raise ValueError('Not an Arena test')
    assets=gh.assets(ident);asset=assets.get(rcg_asset_name(r,g))
    if asset:
        with gh.open('/releases/assets/'+str(asset['id']),binary=True) as response, gzip.GzipFile(fileobj=response) as raw, path.open('wb') as dest:copy_stream(raw,dest)
        return
    archive=assets.get('logs.zip')
    if not archive:raise LookupError('Game RCG publication pending; retry after the game finishes.')
    with tempfile.NamedTemporaryFile(dir=path.parent) as temp:
        with gh.open('/releases/assets/'+str(archive['id']),binary=True) as response:copy_stream(response,temp)
        temp.flush()
        prefix=f'logs/round-{r:03d}-game-{g:03d}/'
        with zipfile.ZipFile(temp.name) as z:
            member=next((prefix+n for n in ('server-logs/match.rcg','match.rcg','server-logs/match.rcg.gz','match.rcg.gz') if prefix+n in z.namelist()),None)
            if not member:raise LookupError('No original RCG in this game archive.')
            with z.open(member) as source,path.open('wb') as dest:
                if member.endswith('.gz'):
                    with gzip.GzipFile(fileobj=source) as raw:copy_stream(raw,dest)
                else:copy_stream(source,dest)

def personal_rcg(ident,r,g,path):
    from personal_bridge import BRIDGE,Call,CHUNK
    import time
    c=Call('GET',f'/api/tests/{ident}/rcg/{r}/{g}','',0)
    try:
        BRIDGE.enqueue(c)
        with c.condition:
            if not c.condition.wait_for(lambda:c.headers is not None or c.closed,120) or c.closed:raise ConnectionError('Ubuntu worker did not respond')
            status,headers=c.headers
            if status!=200:raise LookupError('Original RCG unavailable; update the Ubuntu worker and finish the game first.')
        offset=0
        with path.open('wb') as dest:
            while True:
                with c.condition:
                    if not c.condition.wait_for(lambda:c.size>offset or c.done or c.closed,120) or c.closed:raise ConnectionError('Ubuntu download interrupted')
                    c.response.seek(offset);chunk=c.response.read(min(CHUNK,c.size-offset))
                    if not chunk and c.done:break
                if chunk:
                    if shutil.disk_usage(path.parent).free<64*1024**2:raise ValueError('Not enough temporary disk space')
                    dest.write(chunk);offset+=len(chunk)
    finally:
        with BRIDGE.condition:BRIDGE.calls.pop(c.id,None)
        c.close()
