"""Compile both official source bases through the uploaded-team build path."""
import os,subprocess,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from team_build import build_team

base=sys.argv[1]
projects={
    'school':('RCSS-IR/StarterAgent2D-V2','435df0e596e23b790bc74793fb4032b283b3fbca'),
    'university':('helios-base/helios-base','66fd63d6f9d022423b8c4430668a2b8510353caf'),
}
root=Path(os.environ['RUNNER_TEMP'])/('arena-source-'+base);root.mkdir()
repo,revision=projects[base];project=root/'official-team'
subprocess.run(['git','init',str(project)],check=True)
subprocess.run(['git','-C',str(project),'fetch','--depth','1','https://github.com/'+repo+'.git',revision],check=True)
subprocess.run(['git','-C',str(project),'checkout','--detach','FETCH_HEAD'],check=True)
# ZIP uploads drop executable bits; exercise restoration too.
for name in ('bootstrap','configure'):
    if (project/name).is_file():(project/name).chmod(0o600)
team={'base':base,'source_directory':'wrong-zip-filename/','command':'./start.sh'}
log=Path('source-build-'+base+'.log')
try:
    result=build_team(team,root,log,threading.Event(),lambda stage:print(stage,flush=True))
    runtime=root/result['directory']
    assert (runtime/'start.sh').is_file(),runtime
    binaries=[p for p in runtime.rglob('*') if p.is_file() and p.read_bytes()[:4]==b'\x7fELF']
    assert binaries,'No compiled ELF binaries found'
    env=os.environ.copy()
    env['LD_LIBRARY_PATH']=':'.join(sorted({str(p.parent) for p in root.rglob('*.so*') if p.is_file()}))
    for binary in binaries:
        libs=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,env=env)
        assert 'not found' not in libs.stdout,libs.stdout
    print('PASS: official '+base+' team compiled; start script and shared libraries verified')
except Exception:
    print(log.read_text(errors='replace'),flush=True)
    raise
