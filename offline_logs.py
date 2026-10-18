"""Enable librcsc logging on disposable per-match copies, never uploaded originals."""
import os
import re
import shlex
import shutil
import signal
import subprocess
from pathlib import Path


def prepare_team(source, destination, log_dir, env, offline=True, debug=False):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    shutil.copytree(source,destination,symlinks=False)
    log_dir=Path(log_dir).resolve();log_dir.mkdir(parents=True,exist_ok=True)
    probe_env=env.copy()
    libs=sorted({str(p.parent) for p in destination.rglob('*.so*') if p.is_file()})
    probe_env['LD_LIBRARY_PATH']=':'.join(libs+[env.get('LD_LIBRARY_PATH','')])
    supported=[];debug_clients=[]
    for binary in sorted(destination.rglob('*')):
        if not binary.is_file() or not os.access(binary,os.X_OK) or '.so' in binary.name:continue
        with binary.open('rb') as stream:
            if stream.read(4)!=b'\x7fELF':continue
        # Only enable documented options advertised by this particular client.
        probe=subprocess.Popen([str(binary),'--help'],cwd=binary.parent,env=probe_env,
                               stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        try:out=probe.communicate(timeout=3)[0]
        except subprocess.TimeoutExpired:
            out=b''
        finally:
            try:os.killpg(probe.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            probe.communicate()
        helptext=out.decode('utf-8','replace')
        advertised=lambda key:bool(re.search(r'(?<![a-z_])'+re.escape(key)+r'(?![a-z_])',helptext))
        if not advertised('log_dir'):continue
        options=[]
        if offline and advertised('offline_logging'):options.append('--offline_logging')
        if debug and advertised('debug'):
            options.append('--debug')
            if env.get('ARENA_NATIVE_DEBUG')=='1' and advertised('debug_server_connect'):
                options.append('--debug_server_connect')
                if advertised('debug_server_host'):options.extend(['--debug_server_host','127.0.0.1'])
                if advertised('debug_server_port'):options.extend(['--debug_server_port','6032'])
            for key in ('debug_server_logging','debug_system','debug_world','debug_action','debug_intercept','debug_kick','debug_hold','debug_dribble','debug_pass','debug_cross','debug_shoot','debug_clear','debug_block','debug_mark','debug_positioning','debug_role','debug_plan','debug_team','debug_communication','debug_analyzer','debug_action_chain'):
                if advertised(key):options.append('--'+key)
        if not options:continue
        original=binary.with_name(binary.name+'.arena-real')
        binary.rename(original)
        # Resolve relative to launcher location so relocation does not break wrappers.
        binary.write_text('#!/bin/bash\nexec "$(dirname -- "$0")"/'+shlex.quote(original.name)+
                          ' "$@" '+ ' '.join(options)+' --log_dir '+shlex.quote(str(log_dir))+'\n')
        binary.chmod(0o755);supported.append(str(binary.relative_to(destination)))
        if '--debug' in options:debug_clients.append(str(binary.relative_to(destination)))
    return {'supported_clients':supported,'debug_clients':debug_clients}
