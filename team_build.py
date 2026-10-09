"""One-time source builds, on the match worker, for trusted uploaded teams."""
import os,signal,subprocess,time
from pathlib import Path

class BuildCancelled(Exception):pass


def source_root(root,requested=''):
    root=Path(root).resolve()
    if requested:
        chosen=(root/requested).resolve()
        if not chosen.is_relative_to(root) or not chosen.is_dir():raise ValueError('Source folder missing or outside ZIP')
    else:
        candidates=sorted({p.parent.resolve() for p in root.rglob('bootstrap') if p.is_file() and p.parent.resolve().is_relative_to(root) and '.git' not in p.parts})
        if candidates:
            depth=min(len(p.relative_to(root).parts) for p in candidates)
            candidates=[p for p in candidates if len(p.relative_to(root).parts)==depth]
        if len(candidates)!=1:raise ValueError('Set the source folder: expected one bootstrap, found '+str(len(candidates)))
        chosen=candidates[0]
    if not (chosen/'bootstrap').is_file():raise ValueError('Source folder has no ./bootstrap')
    return chosen


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
            chosen=source_root(root,team.get('source_directory',''))
            for script in ('bootstrap','configure'):
                file=chosen/script
                if file.is_file():file.chmod(file.stat().st_mode|0o100)
            steps=[(['./bootstrap'],chosen),(['./configure'],chosen)]
            if team['base']=='school':
                steps += [(['mkdir','-p','build'],chosen),(['cmake','..'],chosen/'build'),(['make','-j','8'],chosen/'build')]
                runtime=chosen/'build'/'bin'
            else:
                steps += [(['make','-j','8'],chosen)]
                runtime=chosen/'src'
            for command,cwd in steps:
                if cancel.is_set():raise BuildCancelled('Build cancelled')
                stage=' '.join(command);on_stage(stage);log.write('\n$ '+stage+'\n[cwd] '+str(cwd)+'\n');log.flush()
                # configure can be created by bootstrap; restore executable bit immediately before launching it.
                script=cwd/command[0]
                if command[0].startswith('./') and script.is_file():script.chmod(script.stat().st_mode|0o100)
                proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    while proc.poll() is None:
                        if cancel.is_set():raise BuildCancelled('Build cancelled')
                        if time.monotonic()-started>timeout:raise TimeoutError('Source build exceeded '+str(timeout)+' seconds')
                        time.sleep(.1)
                    if proc.returncode:raise RuntimeError(stage+' failed with exit code '+str(proc.returncode))
                finally:
                    if proc.poll() is None:_stop(proc)
            if not runtime.is_dir():raise ValueError('Built runtime directory missing: '+str(runtime.relative_to(root)))
            team['directory']=str(runtime.relative_to(root))
            log.write('\nBuild completed. Runtime: '+team['directory']+'\n')
            return {'source_directory':str(chosen.relative_to(root)),'directory':team['directory']}
        except Exception as exc:
            log.write('\nERROR: '+str(exc)+'\n');log.flush();raise
