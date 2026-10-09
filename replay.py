"""Read-only monitor frames from RCSS text show records (ULG4/5)."""
import gzip
import json
import math
from analysis import sexpr


def number(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Non-finite monitor coordinate')
    return round(result,3)


def show_frame(record, previous=None):
    prev=previous or {}
    frame={'cycle':int(record[1]),'ball':None,'players':[],
           'score':prev.get('score',[0,0]),'names':prev.get('names',['Left','Right']),
           'mode':prev.get('mode','before_kick_off')}
    for item in record[2:]:
        if not isinstance(item,list) or not item:continue
        if item[0]=='pm':frame['mode']=str(item[1])
        elif item[0]=='tm':frame.update(names=item[1:3],score=[int(item[3]),int(item[4])])
        elif isinstance(item[0],list):
            if item[0]==['b']:
                frame['ball']=[number(item[1]),number(item[2])]
                if len(item)>4:frame['ball_velocity']=[number(item[3]),number(item[4])]
            elif len(item[0])==2 and item[0][0] in ('l','r'):
                state=int(str(item[2]),16)
                if state and not state & (0x100|0x200|0x80000):
                    player=[item[0][0],int(item[0][1]),number(item[3]),number(item[4]),number(item[7]) if len(item)>7 else 0,bool(state & 8)]
                    stamina=next((part for part in item if isinstance(part,list) and len(part)>1 and part[0]=='s'),None)
                    if stamina is not None:player.append(number(stamina[1]))
                    frame['players'].append(player)
                    counters=next((part for part in item if isinstance(part,list) and len(part)>1 and part[0]=='c'),None)
                    if counters is not None:frame.setdefault('kicks',{})[f'{player[0]}:{player[1]}']=int(counters[1])
    return frame


def parse_replay(stream):
    if stream.readline().strip() not in ('ULG4','ULG5'):raise ValueError('Expected ULG4/5 replay')
    frames=[];context={};step_ms=100
    for line in stream:
        text=line.lstrip()
        if not text.startswith(('(show ','(team ','(playmode ','(server_param ')):continue
        record=sexpr(text)
        if record[0]=='team':context.update(names=record[2:4],score=[int(record[4]),int(record[5])])
        elif record[0]=='playmode':context['mode']=record[2]
        elif record[0]=='server_param':
            for item in record[1:]:
                if isinstance(item,list) and item[0]=='simulator_step':step_ms=max(1,min(1000,int(item[1])))
        else:
            frame=show_frame(record,context);frames.append(frame);context=frame.copy()
            if len(frames)>50000:raise ValueError('Replay exceeds 50000 frames')
    if not frames:raise ValueError('No monitor frames in this match log')
    if str(context.get('mode')) in ('time_over','2'):
        frames[-1]=dict(frames[-1],score=context.get('score',frames[-1]['score']),mode=context['mode'])
    return {'version':1,'step_ms':step_ms,'frames':frames,'final_score':context.get('score',[0,0]),'team_names':context.get('names',['Left','Right'])}


def encode_replay(stream):
    return gzip.compress(json.dumps(parse_replay(stream),ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)


def asset_name(round_number,game_number):
    return f'replay-{int(round_number):03d}-{int(game_number):03d}.json.gz'
