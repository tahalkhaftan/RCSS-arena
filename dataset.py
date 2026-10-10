"""Conservative RCL command samples joined with RCG truth and prior OCL inputs.
No inferred pass targets, internal world models, or parameter values are fabricated.
"""
import bisect
import csv
import json
import math
import re
from collections import Counter,defaultdict
from pathlib import Path
from analysis import sexpr,params

COMMAND=re.compile(r'^\s*(\d+),(\d+)\s+Recv (.+)_(\d+):\s*(.*)$')
COUNTERS={'kick':0,'dash':1,'turn':2,'catch':3,'move':4,'turn_neck':5,'change_view':6,'say':7,'tackle':8,'pointto':9,'attentionto':10}
FIELDS=['schema_version','match_id','round','game','server_version','team','opponent','side','actor_unum','cycle','stopped_cycle','command_index','action_type','command','command_arguments','execution_confirmed','execution_evidence','before_state_valid','ocl_available','ocl_before_cycle','ocl_messages_before','label_valid','label_reason','retained_10c','goal_for_within_50c','goal_against_within_50c','gt_ball_x','gt_ball_y','gt_ball_vx','gt_ball_vy','gt_actor_x','gt_actor_y','gt_actor_vx','gt_actor_vy','gt_actor_body','gt_actor_neck','gt_actor_stamina','gt_actor_type','gt_playmode','gt_left_score','gt_right_score','server_parameters','player_types','tuning_parameters','intended_receiver','intended_target_x','intended_target_y']
for side in ('l','r'):
    for n in range(1,12):
        FIELDS.extend(f'gt_{side}_{n:02d}_{k}' for k in ('x','y','vx','vy','body','neck','stamina','type'))


def read_rcg(path):
    frames=defaultdict(list);sp={};types={};context={'mode':'before_kick_off','names':['Left','Right'],'score':[0,0]}
    with path.open(encoding='utf-8-sig') as f:
        if f.readline().strip() not in ('ULG4','ULG5','ULG6'):raise ValueError('CSV requires text ULG4/5/6')
        for line in f:
            if not line.lstrip().startswith(('(show ','(team ','(playmode ','(server_param ','(player_type ')):continue
            r=sexpr(line)
            if r[0]=='server_param':sp=params(r)
            elif r[0]=='player_type':
                pt=params(r);types[int(pt['id'])]=pt
            elif r[0]=='team':context.update(names=r[2:4],score=list(map(int,r[4:6])))
            elif r[0]=='playmode':context['mode']=r[2]
            else:
                fr=dict(context,cycle=int(r[1]),players={})
                for x in r[2:]:
                    if not isinstance(x,list) or not x:continue
                    if x[0]=='pm':fr['mode']=x[1]
                    elif x[0]=='tm':fr.update(names=x[1:3],score=list(map(int,x[3:5])))
                    elif isinstance(x[0],list) and x[0]==['b']:fr['ball']=list(map(float,x[1:5]))
                    elif isinstance(x[0],list) and len(x[0])==2 and x[0][0] in ('l','r'):
                        state=int(x[2],16)
                        if not state or state & (0x100|0x200|0x80000):continue
                        p=dict(zip(('x','y','vx','vy','body','neck'),map(float,x[3:9])))
                        p.update(type=int(x[1]),state=state)
                        for part in x[9:]:
                            if isinstance(part,list) and part:
                                if part[0]=='s':p['stamina']=float(part[1])
                                elif part[0]=='c':p['counts']=list(map(int,part[1:]))
                        fr['players'][(x[0][0],int(x[0][1]))]=p
                frames[fr['cycle']].append(fr);context={k:fr[k] for k in ('mode','names','score')}
    return frames,sp,types


def read_ocl(folder):
    """Keep raw received messages; these are not a reconstructed client WorldModel."""
    data={};warnings=[];seen=set()
    for side,letter in (('left','l'),('right','r')):
        for path in (folder/'ocl-log'/f'{side}-team').glob('*.ocl'):
            ident=None;groups=defaultdict(list)
            with path.open(encoding='utf-8',errors='replace') as f:
                for line in f:
                    if line.startswith('(init '):
                        m=re.match(r'\(init ([lr]) (\d+)\s',line)
                        if m:ident=int(m[2])
                    m=re.match(r'\((?:see|sense_body|hear|fullstate) (\d+)\s',line)
                    if m:groups[int(m[1])].append(line.rstrip())
            if ident and 1<=ident<=11:
                key=(letter,ident)
                if key in seen:warnings.append(f'Duplicate OCL player {side}:{ident}; ambiguous input omitted');data[key]=None
                else:data[key]=groups
                seen.add(key)
    return data,warnings


def owners(frame,sp,types):
    ball=frame.get('ball');found=set()
    if not ball:return found
    for (side,n),p in frame['players'].items():
        pt=types.get(p['type'],{})
        radius=pt.get('player_size',sp.get('player_size',.3))+pt.get('kickable_margin',sp.get('kickable_margin',.7))+sp.get('ball_size',.085)
        if math.hypot(p['x']-ball[0],p['y']-ball[1])<=radius:found.add(side)
    return found


def export_dataset(folder,config,match_id,round_number,game_number):
    folder=Path(folder);frames,sp,types=read_rcg(folder/'match.rcg');ocl,warnings=read_ocl(folder)
    input_cycles={key:sorted(groups or {}) for key,groups in ocl.items()}
    commands=[]
    with (folder/'match.rcl').open(encoding='utf-8',errors='replace') as f:
        for line in f:
            m=COMMAND.match(line)
            if not m:continue
            cycle,stopped=int(m[1]),int(m[2]);team=m[3];unum=int(m[4])
            # Tokenize each top-level command separately; say payloads may contain parentheses.
            stack=0;quoted=False;escaped=False;start=0
            for i,c in enumerate(m[5]):
                if escaped:escaped=False;continue
                if c=='\\' and quoted:escaped=True;continue
                if c=='"':quoted=not quoted;continue
                if quoted:continue
                if c=='(':
                    if stack==0:start=i
                    stack+=1
                elif c==')':
                    stack-=1
                    if stack==0:
                        raw=m[5][start:i+1];r=sexpr(raw)
                        if r and r[0] in COUNTERS:commands.append((cycle,stopped,team,unum,r[0],raw,r[1:]))
    duplicates=Counter((c,s,t,n,a) for c,s,t,n,a,*_ in commands)
    rows=0;confirmed=0;joined=0
    with (folder/'decisions.csv').open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
        for i,(cycle,stopped,team,n,action,raw,args) in enumerate(commands):
            before=frames.get(cycle,[]);after=frames.get(cycle+1,[])
            names=before[-1]['names'] if before else next((v[0]['names'] for v in frames.values() if team in v[0]['names']),[])
            side='l' if names and names[0]==team else 'r' if len(names)>1 and names[1]==team else None
            row=dict(schema_version=1,match_id=match_id,round=round_number,game=game_number,server_version='19.0.0',team=team,opponent=names[1 if side=='l' else 0] if side else '',side=side or '',actor_unum=n,cycle=cycle,stopped_cycle=stopped,command_index=i,action_type=action,command=raw,command_arguments=json.dumps(args),execution_evidence='unknown',before_state_valid=0,ocl_available=0,label_valid=0,label_reason='ambiguous or missing state',server_parameters=json.dumps(sp,sort_keys=True) if rows==0 else '',player_types=json.dumps(types,sort_keys=True) if rows==0 else '')
            # Repeated/stopped cycles cannot be joined by cycle alone.
            if side and len(before)==1 and stopped==0:
                fr=before[0];p=fr['players'].get((side,n));row['before_state_valid']=int(p is not None)
                row.update(gt_playmode=fr['mode'],gt_left_score=fr['score'][0],gt_right_score=fr['score'][1])
                for k,v in zip(('x','y','vx','vy'),fr.get('ball',[])):row['gt_ball_'+k]=v
                if p:
                    for k in ('x','y','vx','vy','body','neck','stamina','type'):row['gt_actor_'+k]=p.get(k,'')
                for (letter,unum),player in fr['players'].items():
                    for k in ('x','y','vx','vy','body','neck','stamina','type'):row[f'gt_{letter}_{unum:02d}_{k}']=player.get(k,'')
                if p and len(after)==1 and duplicates[(cycle,stopped,team,n,action)]==1:
                    post=after[0]['players'].get((side,n),{});ix=COUNTERS[action];a=p.get('counts',[]);b=post.get('counts',[])
                    if len(a)>ix and len(b)>ix and b[ix]-a[ix] in (0,1):
                        row['execution_confirmed']=int(b[ix]>a[ix]);row['execution_evidence']='rcg_counter_delta';confirmed+=row['execution_confirmed']
                inputs=ocl.get((side,n));times=input_cycles.get((side,n),[]);index=bisect.bisect_left(times,cycle)
                if index:
                    t=times[index-1];row.update(ocl_available=1,ocl_before_cycle=t,ocl_messages_before=json.dumps(inputs[t],ensure_ascii=False));joined+=1
                horizon=[frames.get(c,[]) for c in range(cycle+1,cycle+51)]
                valid=all(len(f)==1 and str(f[0]['mode']) in ('play_on','3') for f in horizon[:10]) and str(fr['mode']) in ('play_on','3')
                if row.get('execution_confirmed')==1 and valid:
                    ownership=owners(horizon[9][0],sp,types)
                    row.update(label_valid=1,label_reason='kickable_control_at_10_cycles_v1',retained_10c=int(ownership=={side}))
                if all(len(f)==1 for f in horizon):
                    index=0 if side=='l' else 1
                    row['goal_for_within_50c']=int(horizon[-1][0]['score'][index]>fr['score'][index])
                    row['goal_against_within_50c']=int(horizon[-1][0]['score'][1-index]>fr['score'][1-index])
            writer.writerow(row);rows+=1
    if rows==0:warnings.append('No supported player commands found in RCL; CSV contains headers only')
    for side,letter in (('left','l'),('right','r')):
        count=sum(bool(v) for (s,n),v in ocl.items() if s==letter)
        if count<11:warnings.append(f'{side}: OCL موجود برای {count} از 11 بازیکن؛ دادهٔ مشاهده‌ای بقیه نامعلوم است')
    report={'schema_version':1,'status':'completed','csv':'decisions.csv','rows':rows,'execution_confirmed':confirmed,'ocl_joined_rows':joined,'warnings':warnings}
    (folder/'dataset-metadata.json').write_text(json.dumps(dict(report,server_parameters=sp,player_types=types,constant_columns='server_parameters/player_types occur in the first CSV row only'),ensure_ascii=False,indent=2),encoding='utf-8')
    return report
