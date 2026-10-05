"""RCG text log (ULG5) result and possession analysis. No external packages."""
import re
import json
import math
from collections import Counter
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]')

def sexpr(text):
    stack = []; root = None
    for token in TOKEN.findall(text):
        if token == '(':
            node = []
            if stack: stack[-1].append(node)
            stack.append(node)
        elif token == ')':
            if not stack: raise ValueError('Unbalanced log record')
            root = stack.pop()
        else:
            if not stack: raise ValueError('Invalid record')
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack: raise ValueError('Incomplete record')
    return root

def params(record):
    return {x[0]: float(x[1]) for x in record[1:] if isinstance(x,list) and len(x)==2}

def analyze(path):
    mode = None; ended = False; score = None; names = None
    counts = Counter(); types = {}; sp = {}; seen = set(); max_players = {'l':0,'r':0}; cycles = 0
    with open(path,encoding='utf-8') as stream:
        if stream.readline().strip() not in ('ULG4','ULG5'):
            raise ValueError('Expected a text RCG log (ULG4/5)')
        for line in stream:
            if not line.strip(): continue
            rec = sexpr(line)
            if not rec: continue
            kind = rec[0]
            if kind=='server_param': sp.update(params(rec))
            elif kind=='player_type':
                p=params(rec); types[int(p['id'])]=p
            elif kind=='playmode':
                mode=rec[2]; ended = ended or mode=='time_over'
            elif kind=='team':
                names = [rec[2],rec[3]]; score=[int(rec[4]),int(rec[5])]
            elif kind=='show':
                cycles=max(cycles,int(rec[1])); ball=None; players=[]
                for x in rec[2:]:
                    if not isinstance(x,list) or not x: continue
                    if x[0]=='pm': mode=x[1]; ended=ended or str(mode)=='2'
                    elif x[0]=='tm': names=[x[1],x[2]]; score=[int(x[3]),int(x[4])]
                    elif isinstance(x[0],list):
                        if x[0]==['b']: ball=(float(x[1]),float(x[2]))
                        elif len(x[0])==2 and x[0][0] in ('l','r'):
                            # Type, state, X, Y. State is hexadecimal in text game logs.
                            state=int(str(x[2]),16)
                            if state and not state & (0x100|0x200|0x80000):
                                players.append((x[0][0],int(x[1]),float(x[3]),float(x[4])))
                for side in ('l','r'): max_players[side]=max(max_players[side],sum(p[0]==side for p in players))
                key=int(rec[1])
                if str(mode) not in ('play_on','3') or ball is None or key in seen: continue
                seen.add(key); owners=set()
                for side,ptype,x,y in players:
                    pt=types.get(ptype,{})
                    radius=pt.get('player_size',sp.get('player_size',.3))+pt.get('kickable_margin',sp.get('kickable_margin',.7))+sp.get('ball_size',.085)
                    if math.hypot(x-ball[0],y-ball[1])<=radius: owners.add(side)
                counts['shared' if len(owners)==2 else next(iter(owners)) if owners else 'free']+=1
    total=sum(counts.values())
    possession={'method':'kickable_range_play_on_v1','description':'Control estimate; shared and free ball included in denominator. Not last-touch possession.',
                'cycles':total,'left_percent':round(100*counts['l']/total,3) if total else None,
                'right_percent':round(100*counts['r']/total,3) if total else None,
                'free_percent':round(100*counts['free']/total,3) if total else None,
                'shared_percent':round(100*counts['shared']/total,3) if total else None}
    return {'natural_end':ended,'scores':score,'team_names':names,'last_cycle':cycles,'max_players':max_players,'possession':possession}

def summary(matches):
    valid=[m for m in matches if m['status']=='completed']; n=len(valid)
    return {'completed':n,'failed':sum(m['status']=='failed' for m in matches),
            'left_wins':sum(m['left_score']>m['right_score'] for m in valid),
            'right_wins':sum(m['right_score']>m['left_score'] for m in valid),
            'draws':sum(m['right_score']==m['left_score'] for m in valid),
            'left_goals':sum(m['left_score'] for m in valid),'right_goals':sum(m['right_score'] for m in valid),
            'average_possession':{key:round(sum(v)/len(v),3) if v else None for key in ('left_percent','right_percent','free_percent','shared_percent')
                for v in [[m['possession'][key] for m in valid if m.get('possession',{}).get(key) is not None]]}}
