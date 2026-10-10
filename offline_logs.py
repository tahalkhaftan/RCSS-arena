"""Enable librcsc logging on disposable per-match copies, never uploaded originals."""
import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path


def prepare_team(source, destination, log_dir, env):
    source=Path(source).resolve(); destination=Path(destination).resolve()
    shutil.copytree(source,destination,symlinks=False)
    log_dir=Path(log_dir).resolve();log_dir.mkdir(parents=True,exist_ok=True)
    probe_env=env.copy()
    libs=sorted({str(p.parent) for p in destination.rglob('*.so*') if p.is_file()})
    probe_env['LD_LIBRARY_PATH']=':'.join(libs+[env.get('LD_LIBRARY_PATH','')])
    supported=[]
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
        if b'offline_logging' not in out or b'log_dir' not in out:continue
        original=binary.with_name(binary.name+'.arena-real')
        binary.rename(original)
        # Resolve relative to launcher location so relocation does not break wrappers.
        binary.write_text('#!/bin/bash\nexec "$(dirname -- "$0")"/'+shlex.quote(original.name)+
                          ' "$@" --offline_logging --log_dir '+shlex.quote(str(log_dir))+'\n')
        binary.chmod(0o755);supported.append(str(binary.relative_to(destination)))
    return {'supported_clients':supported}
