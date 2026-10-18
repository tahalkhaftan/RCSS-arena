"""Read-only monitor frames from RCSS text show records (ULG4/5)."""
import gzip
import json
import math
from analysis import sexpr,params


def number(value):
    result=float(value)
    if not math.isfinite(result):raise ValueError('Non-finite monitor coordinate')
    return round(result,3)


MONITOR_PARAMETERS=('player_size','ball_size','kickable_margin','stamina_max','catchable_area_l','catchable_area_w','tackle_dist','tackle_back_dist','tackle_width','visible_distance','pitch_length','pitch_width')

def monitor_parameters(parameters):
    return {k:v for k,v in (parameters or {}).items() if k in MONITOR_PARAMETERS}

def show_frame(record, previous=None, parameters=None, player_types=None):
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
                ident=f'{item[0][0]}:{int(item[0][1])}'
                if state & 2 and not state & 4:frame.setdefault('kickers',[]).append(ident)
                if state & 4:frame.setdefault('kick_faults',[]).append(ident)
                if state & 16 and state & 8 and not state & 32:frame.setdefault('catchers',[]).append(ident)
                if state and not state & (0x100|0x200|0x80000):
                    player=[item[0][0],int(item[0][1]),number(item[3]),number(item[4]),number(item[7]) if len(item)>7 else 0,bool(state & 8)]
                    stamina=next((part for part in item if isinstance(part,list) and len(part)>1 and part[0]=='s'),None)
                    if stamina is not None:player.append(number(stamina[1]))
                    frame['players'].append(player)
                    meta={'type':int(item[1]),'state':state}
                    if len(item)>6:meta['velocity']=[number(item[5]),number(item[6])]
                    if len(item)>8 and not isinstance(item[8],list):meta['neck']=number(item[8])
                    if len(item)>10 and not isinstance(item[9],list) and not isinstance(item[10],list):meta['pointto']=[number(item[9]),number(item[10])]
                    for part in item:
                        if not isinstance(part,list) or not part:continue
                        if part[0]=='v' and len(part)>2:meta.update(view_quality=part[1],view_width=number(part[2]))
                        elif part[0]=='s' and len(part)>3:meta.update(effort=number(part[2]),recovery=number(part[3]))
                        elif part[0]=='f' and len(part)>2:meta['attention']=[part[1],int(part[2])]
                        elif part[0]=='c':meta['counters']=[int(v) for v in part[1:]]
                    frame.setdefault('player_meta',{})[ident]=meta
                    if parameters is not None:
                        pt=(player_types or {}).get(int(item[1]),{})
                        radius=pt.get('player_size',parameters.get('player_size',.3))+pt.get('kickable_margin',parameters.get('kickable_margin',.7))+parameters.get('ball_size',.085)
                        if math.isfinite(radius) and radius>0:frame.setdefault('control_radii',{})[ident]=radius
                    counters=next((part for part in item if isinstance(part,list) and len(part)>1 and part[0]=='c'),None)
                    if counters is not None:frame.setdefault('kicks',{})[f'{player[0]}:{player[1]}']=int(counters[1])
    if parameters:frame['parameters']=monitor_parameters(parameters)
    if player_types:frame['player_types']={k:{n:v for n,v in pt.items() if n in ('player_size','kickable_margin','player_speed_max','player_decay','dash_power_rate','effort_max','effort_min')} for k,pt in player_types.items()}
    return frame


def parse_replay(stream):
    if stream.readline().strip() not in ('ULG4','ULG5','ULG6'):raise ValueError('Expected ULG4/5/6 replay')
    frames=[];context={};step_ms=100;parameters={};player_types={}
    for line in stream:
        text=line.lstrip()
        if not text.startswith(('(show ','(team ','(playmode ','(server_param ','(player_type ')):continue
        record=sexpr(text)
        if record[0]=='team':context.update(names=record[2:4],score=[int(record[4]),int(record[5])])
        elif record[0]=='playmode':context['mode']=record[2]
        elif record[0]=='player_type':
            pt=params(record);player_types[int(pt['id'])]=pt
        elif record[0]=='server_param':
            parameters.update(params(record))
            for item in record[1:]:
                if isinstance(item,list) and item[0]=='simulator_step':step_ms=max(1,min(1000,int(item[1])))
        else:
            frame=show_frame(record,context,parameters,player_types);frames.append(frame);context=frame.copy()
            if len(frames)>50000:raise ValueError('Replay exceeds 50000 frames')
    if not frames:raise ValueError('No monitor frames in this match log')
    if str(context.get('mode')) in ('time_over','2'):
        frames[-1]=dict(frames[-1],score=context.get('score',frames[-1]['score']),mode=context['mode'])
    return {'version':1,'step_ms':step_ms,'frames':frames,'final_score':context.get('score',[0,0]),'team_names':context.get('names',['Left','Right'])}


def encode_replay(stream,debug_root=None):
    data=parse_replay(stream)
    if debug_root is not None:
        from debug_logs import attach_replay
        data=attach_replay(data,debug_root)
    return gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0)


def asset_name(round_number,game_number):
    return f'replay-{int(round_number):03d}-{int(game_number):03d}.json.gz'
