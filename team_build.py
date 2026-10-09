"""One-time source builds, on the match worker, for trusted uploaded teams."""
import os,signal,subprocess,time,shutil
from pathlib import Path

class BuildCancelled(Exception):pass


def source_root(root,requested='',base='university'):
    root=Path(root).resolve()
    if requested:
        chosen=(root/requested).resolve()
        if not chosen.is_relative_to(root):raise ValueError('Source folder outside ZIP')
        if chosen.is_dir() and _is_project(chosen,base):return chosen
    # ZIP filenames need not match the archive's internal top-level folder.
    search=chosen if requested and chosen.is_dir() else root
    markers=('CMakeLists.txt',) if base=='school' else ('bootstrap','configure','configure.ac')
    candidates=sorted({p.parent.resolve() for marker in markers for p in search.rglob(marker) if p.is_file() and p.parent.resolve().is_relative_to(root) and not any(x in p.parts for x in ('.git','.arena-deps','CMakeFiles')) and _is_project(p.parent,base)})
    if candidates:
        depth=min(len(p.relative_to(root).parts) for p in candidates)
        candidates=[p for p in candidates if len(p.relative_to(root).parts)==depth]
    if len(candidates)!=1:raise ValueError('Set the source folder: expected one team project, found '+str(len(candidates)))
    return candidates[0]

def _is_project(path,base):
    if (path/'rcsc'/'types.h').is_file():return False # library, not a team
    if base=='school':return (path/'CMakeLists.txt').is_file() and (path/'src').is_dir()
    return any((path/name).is_file() for name in ('bootstrap','configure','configure.ac'))

LIBRARIES={
    'school':('RCSS-IR/StarterLibRCSC-V2','af506602e0c7f4872101a86c63e1a9f662602b8b'),
    'university':('helios-base/librcsc','078d59ff85c336f94c021adac060ef6f2e63c575'),
}


def _stop(proc):
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.wait()


def build_team(team,root,log_path,cancel,on_stage=lambda stage:None):
    root=Path(root).resolve();log_path=Path(log_path);log_path.parent.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ('TOKEN','PASSWORD','SECRET','CREDENTIAL'))}
    started=time.monotonic();timeout=int(os.environ.get('BUILD_TIMEOUT_SECONDS','1200'))
    with log_path.open('w',encoding='utf-8') as log:
        try:
            base=team['base'];chosen=source_root(root,team.get('source_directory',''),base)
            log.write('Source project: '+str(chosen.relative_to(root))+'\n');log.flush()
            def run(command,cwd):
                if cancel.is_set():raise BuildCancelled('Build cancelled')
                stage=' '.join(command);on_stage(stage);log.write('\n$ '+stage+'\n[cwd] '+str(cwd)+'\n');log.flush()
                # configure can be created by bootstrap; restore executable bit immediately before launching it.
                script=cwd/command[0]
                if command[0].startswith('./') and script.is_file():
                    data=script.read_bytes()
                    if data.startswith(b'#!') and b'\r\n' in data:script.write_bytes(data.replace(b'\r\n',b'\n'))
                    script.chmod(script.stat().st_mode|0o100)
                proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    while proc.poll() is None:
                        if cancel.is_set():raise BuildCancelled('Build cancelled')
                        if time.monotonic()-started>timeout:raise TimeoutError('Source build exceeded '+str(timeout)+' seconds')
                        time.sleep(.1)
                    if proc.returncode:raise RuntimeError(stage+' failed with exit code '+str(proc.returncode))
                finally:
                    if proc.poll() is None:_stop(proc)
            # Install the matching API before configuring real RCSS projects.
            needs_rcsc=any('rcsc' in (chosen/name).read_text(errors='replace').lower() for name in ('CMakeLists.txt','configure.ac','configure') if (chosen/name).is_file())
            prefix=None
            if needs_rcsc:
                deps=root/'.arena-deps';deps.mkdir(exist_ok=True)
                # StarterLibRCSC's own CMake forces this documented install prefix.
                prefix=Path.home()/'local'/'starter' if base=='school' else deps/'install'
                lib=deps/'librcsc';repo,revision=LIBRARIES[base]
                run(['git','init',str(lib)],deps)
                run(['git','-C',str(lib),'fetch','--depth','1','https://github.com/'+repo+'.git',revision],deps)
                run(['git','-C',str(lib),'checkout','--detach','FETCH_HEAD'],deps)
                if base=='school':
                    run(['cmake','-S',str(lib),'-B',str(deps/'lib-build'),'-DCMAKE_INSTALL_LIBDIR=lib'],deps)
                    run(['cmake','--build',str(deps/'lib-build'),'--parallel','8'],deps)
                    run(['cmake','--install',str(deps/'lib-build')],deps)
                else:
                    run(['./bootstrap'],lib)
                    run(['./configure','--disable-unit-test','--prefix='+str(prefix)],lib)
                    run(['make','-j','8'],lib);run(['make','install'],lib)
                env['LD_LIBRARY_PATH']=str(prefix/'lib')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
            if base=='school':
                build=chosen/'build';build.mkdir(exist_ok=True)
                # Remove caches tied to the uploader's machine; retain source/assets.
                (build/'CMakeCache.txt').unlink(missing_ok=True)
                if (build/'CMakeFiles').is_dir():shutil.rmtree(build/'CMakeFiles')
                command=['cmake','..']
                if prefix:command+=['-DLIBRCSC_INSTALL_DIR='+str(prefix)]
                run(command,build);run(['make','-j','8'],build)
                runtime=build/'bin'
            else:
                if (chosen/'bootstrap').is_file():run(['./bootstrap'],chosen)
                elif not (chosen/'configure').is_file():run(['autoreconf','-fi'],chosen)
                command=['./configure']
                if prefix:command+=['--with-librcsc='+str(prefix)]
                run(command,chosen)
                if needs_rcsc:run(['make','clean'],chosen)
                run(['make','-j','8'],chosen);runtime=chosen/'src'
            if not runtime.is_dir():raise ValueError('Built runtime directory missing: '+str(runtime.relative_to(root)))
            team['directory']=str(runtime.relative_to(root))
            log.write('\nBuild completed. Runtime: '+team['directory']+'\n')
            return {'source_directory':str(chosen.relative_to(root)),'directory':team['directory']}
        except Exception as exc:
            log.write('\nERROR: '+str(exc)+'\n');log.flush();raise
