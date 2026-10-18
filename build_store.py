"""Private, reusable team builds. Match requests only accept completed builds."""
import hashlib,io,json,re,zipfile
from pathlib import Path

def is_build_release(release):
    return any(re.fullmatch(r'arena-build-[0-9a-f]{32}',str(release.get(k) or '')) for k in ('name','tag_name'))

def build_signature(team):
    return {k:team.get(k,'') for k in ('name','base','source_directory','command')}

def build_state(gh,ident):
    release=gh.release(ident)
    if not is_build_release(release):raise ValueError('Not an Arena team build')
    state=json.loads(release.get('body') or '{}').get('build_state')
    if not isinstance(state,dict):raise ValueError('Build state is unavailable')
    return state

def compiled_team(gh,team):
    ident=team.get('build_id')
    if not isinstance(ident,str) or not ident.isdigit():raise ValueError('Build this source team before starting the test')
    state=build_state(gh,ident)
    if state.get('status')!='completed':raise ValueError('Source build failed or is not ready; build the team before testing')
    if state.get('signature')!=build_signature(team):raise ValueError('Team settings changed; rebuild before testing')
    asset=gh.assets(ident).get('compiled.zip')
    if not asset:raise ValueError('Compiled team archive is unavailable; rebuild')
    blob=gh.read_asset(asset)
    if hashlib.sha256(blob).hexdigest()!=state.get('compiled_sha256'):raise ValueError('Compiled archive checksum mismatch')
    prepared=dict(team);prepared.update(input_mode='binary',directory='bin',preset_id='',build_id=ident)
    return prepared,blob

def pack_compiled(team,root):
    root=Path(root).resolve();runtime=(root/team['directory']).resolve()
    if not runtime.is_relative_to(root):raise ValueError('Runtime outside source archive')
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(runtime.rglob('*')):
            if not path.is_file() or path.suffix in ('.o','.a') or any(x in path.relative_to(runtime).parts for x in ('.git','.deps')):continue
            if not path.resolve().is_relative_to(root):raise ValueError('Runtime symlink outside source archive')
            archive.write(path,'bin/'+str(path.relative_to(runtime)))
        # Materialize each shared-library alias; no symlinks in the reusable ZIP.
        libraries={}
        for path in sorted((root/'.arena-deps').rglob('*.so*')):
            if path.is_file() and path.resolve().is_relative_to(root):libraries[path.name]=path
        for name,path in libraries.items():archive.write(path,'lib/'+name)
    return data.getvalue()
