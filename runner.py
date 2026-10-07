"""Sequential runner for trusted teams on one dedicated RCSS Arena instance."""
import os
import re
import signal
import shutil
import socket
import subprocess
import time
from pathlib import Path
from analysis import analyze, summary, sexpr
from replay import show_frame,encode_replay

def results_only(value):
    """Copy results without the separate monitor/replay position data."""
    if isinstance(value,dict):
        return {k:results_only(v) for k,v in value.items() if k not in ('frame','frames','players','ball')}
    if isinstance(value,list):return [results_only(v) for v in value]
    return value

class Cancelled(Exception): pass

def kill_group(proc):
    # Kill group even when launcher shell already exited (background players).
    try: os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError: return
    time.sleep(.3)
    try: os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired: pass

def start_team(team,root,log,procs,env):
    root=root.resolve()
    team_env=env.copy()
    # Search the uploaded package, since binaries often refer to the original
    # computer's library install path. Keep each opponent's libraries separate.
    lib_dirs=sorted({str(p.parent.resolve()) for p in root.rglob('*.so*') if p.is_file()})
    if lib_dirs:
        existing=team_env.get('LD_LIBRARY_PATH','')
        team_env['LD_LIBRARY_PATH']=':'.join(lib_dirs+([existing] if existing else []))
    cmd=team['command']
    for key in ('host','port','coach_port','olcoach_port'):
        cmd=cmd.replace('{'+key+'}',env['RCSS_'+key.upper()])
    proc=subprocess.Popen(['/bin/bash','-c',cmd],cwd=root/team['directory'],env=team_env,
                          stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    procs.append(proc)

def monitor_snapshot(text, previous=None):
    """Read only structured state records; graphical/message records are irrelevant."""
    snapshot=dict(previous or {})
    if not text.startswith(('(show ', '(team ', '(playmode ')): return snapshot
    rec=sexpr(text)
    if rec[0]=='team':
        snapshot.update(server_team_names=rec[2:4],left_score=int(rec[4]),right_score=int(rec[5]))
    elif rec[0]=='playmode': snapshot['playmode']=rec[2]
    else:
        snapshot['cycle']=int(rec[1])
        snapshot['frame']=show_frame(rec,{'names':snapshot.get('server_team_names',['Left','Right']),'score':[snapshot.get('left_score',0),snapshot.get('right_score',0)],'mode':snapshot.get('playmode','before_kick_off')})
        counts={'l':0,'r':0}
        for item in rec[2:]:
            if not isinstance(item,list) or not item: continue
            if item[0]=='pm': snapshot['playmode']=str(item[1])
            elif item[0]=='tm':
                snapshot.update(server_team_names=item[1:3],left_score=int(item[3]),right_score=int(item[4]))
            elif isinstance(item[0],list) and item[0][0] in counts:
                state=int(str(item[2]),16)
                if state and not state & (0x100|0x200|0x80000): counts[item[0][0]]+=1
        snapshot.update(left_players=counts['l'],right_players=counts['r'])
    snapshot['expected_cycles']=6000
    # Stoppages do not advance the RCSS cycle. 100% requires confirmed time_over.
    snapshot['percent']=100 if snapshot.get('playmode') in ('time_over','2') else min(99.9,round(snapshot.get('cycle',0)/60,1))
    snapshot['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    return snapshot


def run_match(config,teams,folder,cancel,progress=None,live=None):
    folder.mkdir(parents=True); procs=[]; files=[]
    env=os.environ.copy(); env.update(RCSS_HOST='127.0.0.1',RCSS_PORT='6000',RCSS_COACH_PORT='6001',RCSS_OLCOACH_PORT='6002')
    # Dedicated instance: one match uses the standard ports. No public UDP needed.
    opts={'auto_mode':'true','connect_wait':1000,'kick_off_wait':100,'game_over_wait':20,
          'half_time':300,'nr_normal_halfs':2,'nr_extra_halfs':0,'penalty_shoot_outs':'false',
          'synch_mode':'true' if config['synch_mode'] else 'false',
          'game_logging':'true','text_logging':'true','game_log_version':5,
          'game_log_compression':0,'text_log_compression':0,
          'game_log_fixed':'true','text_log_fixed':'true','game_log_dated':'false','text_log_dated':'false',
          'game_log_fixed_name':'match','text_log_fixed_name':'match','game_log_dir':str(folder),'text_log_dir':str(folder),
          # RCSS parses argv as configuration text: empty strings need quotes.
          'team_l_start':'""','team_r_start':'""','port':6000,'coach_port':6001,'olcoach_port':6002}
    monitor=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); monitor.settimeout(.3)
    deadline=time.monotonic()+int(os.environ.get('MATCH_TIMEOUT_SECONDS','1800'))
    try:
        def launch_log(name):
            f=open(folder/name,'wb'); files.append(f); return f
        server=subprocess.Popen([os.environ.get('RCSSSERVER','rcssserver')]+[f'server::{k}={v}' for k,v in opts.items()],
             cwd=folder,stdout=launch_log('server.log'),stderr=subprocess.STDOUT,start_new_session=True)
        procs.append(server)
        # Read-only UDP monitor supplies connection counts, without a graphical monitor.
        monitor_addr=None
        snapshot={'cycle':0,'percent':0,'expected_cycles':6000,'stage':'connecting'}
        published=0;live_published=0
        def observe(data, force=False):
            nonlocal snapshot,published,live_published
            text=data.rstrip(b'\0').decode('utf-8',errors='replace')
            try: snapshot=monitor_snapshot(text,snapshot)
            except (ValueError,IndexError,TypeError): return
            now=time.monotonic()
            if live and text.startswith('(show ') and now-live_published>=.1:
                try:live(snapshot['frame'])
                except Exception:pass
                live_published=now
            if progress and (force or now-published>=10):
                progress(dict(snapshot)); published=now
        def wait_for(side=None,timeout=35):
            until=time.monotonic()+timeout
            while time.monotonic()<until:
                if cancel.is_set(): raise Cancelled()
                if server.poll() is not None: raise RuntimeError('rcssserver exited while preparing teams; see server.log')
                if side is not None:
                    team_log=folder/('left.log' if side=='l' else 'right.log')
                    with team_log.open('rb') as f:
                        f.seek(max(0,team_log.stat().st_size-8192))
                        lines=f.read().decode('utf-8',errors='replace').splitlines()
                    for line in lines:
                        if ('error while loading shared libraries:' in line or ('version ' in line and 'not found' in line) or 'cannot execute binary file' in line):
                            raise RuntimeError(('Left' if side=='l' else 'Right')+' team launch failed: '+line[:600])
                if monitor_addr is None: monitor.sendto(b'(dispinit version 4)\0',('127.0.0.1',6000))
                try: data,addr=monitor.recvfrom(65535)
                except socket.timeout: continue
                observe(data)
                text=data.rstrip(b'\0').decode('utf-8',errors='replace')
                if not text.startswith('(show '): continue
                rec=sexpr(text)
                if side is None: return addr
                count=0
                for p in rec[2:]:
                    if isinstance(p,list) and isinstance(p[0],list) and p[0][0]==side:
                        state=int(str(p[2]),16)
                        if state and not state & (0x100|0x200|0x80000): count+=1
                if count==11: return addr
            raise RuntimeError('Timed out waiting for server/11 players on '+str(side))
        monitor_addr=wait_for(timeout=15)
        start_team(config['left'],teams/'left',launch_log('left.log'),procs,env)
        wait_for('l')  # Establish left side before launching opponent.
        start_team(config['right'],teams/'right',launch_log('right.log'),procs,env)
        wait_for('r')
        snapshot['stage']='playing'
        if progress: progress(dict(snapshot))
        while server.poll() is None:
            if cancel.is_set(): raise Cancelled()
            if time.monotonic()>deadline: raise RuntimeError('Match timeout; logs retained')
            # Drain UDP so server sends do not accumulate in socket buffer.
            try: observe(monitor.recvfrom(65535)[0])
            except socket.timeout: pass
        if server.returncode:
            raise RuntimeError(f'Server exited with code {server.returncode}; last observed cycle {snapshot.get("cycle",0)}; see server.log and team logs')
        parsed=analyze(folder/'match.rcg')
        if not parsed['natural_end'] or parsed['scores'] is None or min(parsed['max_players'].values())<11:
            raise RuntimeError('Game did not finish normally with both complete teams')
        if not (folder/'match.rcl').exists(): raise RuntimeError('Missing .rcl log')
        return {'status':'completed','left_score':parsed['scores'][0],'right_score':parsed['scores'][1],
                'server_team_names':parsed['team_names'],'last_cycle':parsed['last_cycle'],'possession':parsed['possession']}
    finally:
        monitor.close()
        for p in reversed(procs): kill_group(p)
        for f in files: f.close()

def run_job(job,write):
    import zipfile
    state=job['state']; root=job['root']; cancel=job['cancel']; config=state['config']
    state['status']='running'; write(job)
    try:
        for r in range(1,config['rounds']+1):
            for g in range(1,config['games_per_round']+1):
                if cancel.is_set(): raise Cancelled()
                entry={'round':r,'game':g,'left_team':config['left']['name'],'right_team':config['right']['name']}
                def progress(info):
                    state['progress']=dict(info,round=r,game=g,match_index=len(state['matches'])+1)
                    write(job)
                live_options={'live':lambda frame:job['live'].submit(r,g,frame)} if job.get('live') else {}
                try: entry.update(run_match(config,root/'teams',root/'logs'/f'round-{r:03d}-game-{g:03d}',cancel,progress,**live_options))
                except Cancelled: entry.update(status='cancelled'); state['matches'].append(entry); raise
                except Exception as exc:
                    entry.update(status='failed',error=str(exc))
                    entry['last_observed']=state.get('progress',{}).copy()
                # Replay generation must never change a match's result.
                folder=root/'logs'/f'round-{r:03d}-game-{g:03d}'
                if (folder/'match.rcg').exists():
                    try:
                        with (folder/'match.rcg').open(encoding='utf-8') as stream:
                            (folder/'replay.json.gz').write_bytes(encode_replay(stream))
                        entry['replay_available']=True
                    except Exception as exc:entry['replay_error']=str(exc)
                state.pop('progress',None)
                state['matches'].append(entry); state['summary']=summary(state['matches']); write(job)
        failures=sum(m['status']!='completed' for m in state['matches'])
        state['status']='failed' if failures else 'completed'
        if failures: state['error']=f'{failures} of {len(state["matches"])} matches failed; see per-match errors and logs'
    except Cancelled: state['status']='cancelled'
    except Exception as exc: state.update(status='failed',error=str(exc))
    finally:
        state['summary']=summary(state['matches']); state['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); write(job)
        tmp=root/'logs.tmp.zip'
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(root/'results.json','results.json')
            if (root/'logs').exists():
                for p in (root/'logs').rglob('*'):
                    if p.is_file() and not p.is_symlink(): archive.write(p,str(p.relative_to(root)))
        tmp.replace(root/'logs.zip')
        state['archive_ready']=True; write(job)
