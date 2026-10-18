"""Bounded visual debug records from librcsc .log/.dcl, not inferred decisions."""
import collections,math,re,threading,time
from pathlib import Path
from analysis import sexpr
COUNTS={'p':2,'l':4,'a':5,'c':3,'C':3,'r':4,'R':4,'s':6,'S':6,'t':6,'T':6,'m':2}

def parse_line(line,agent):
    if len(line)>262144:return []
    try:
        if '%% debug [' in line or line.lstrip().startswith('((debug '):
            text=line.split('%% debug [',1)[-1].strip().removesuffix(']')
            rec=sexpr(text);clock=next(p for p in rec if isinstance(p,list) and p[0]=='time')[1].split(',');cycle=int(clock[0]);stopped=int(clock[1]) if len(clock)>1 else 0
            who=next((p for p in rec if isinstance(p,list) and p[0]=='s'),None)
            if who:agent=str(who[1])+':'+str(int(who[2]))
            out=[]
            for p in rec:
                if not isinstance(p,list) or not p:continue
                kind={'line':'l','circle':'c','tri':'t','rect':'r','target-point':'p'}.get(p[0])
                if kind:
                    n=COUNTS[kind];v=list(map(float,p[1:1+n]));color=str(p[1+n]) if len(p)>1+n else '#ff66ff'
                    if p[0]=='rect':v[2]-=v[0];v[3]-=v[1]
                    if all(math.isfinite(x) for x in v):out.append(dict(cycle=cycle,stopped=stopped,agent=agent,level=0,kind=kind,values=v,color=color[:80]))
                elif p[0] in ('message','say','hear'):out.append(dict(cycle=cycle,stopped=stopped,agent=agent,level=0,kind='M',text=' '.join(map(str,p[1:]))[:1000]))
            return out[:256]
        m=re.match(r'^\s*(\d+)(?:\s*,\s*(\d+))?\s+(-?\d+)\s+([MlcaCrRsStTpm])\s+(.*)$',line)
        if not m:return []
        cycle,stopped,level,kind,payload=m.groups();r=dict(cycle=int(cycle),stopped=int(stopped or 0),agent=agent,level=int(level),kind=kind)
        if kind=='M':r['text']=payload[:1000]
        else:
            tokens=payload.split(maxsplit=COUNTS[kind]);values=list(map(float,tokens[:COUNTS[kind]]))
            if len(values)!=COUNTS[kind] or not all(math.isfinite(x) and abs(x)<1e6 for x in values):return []
            r['values']=values;r['color']=(tokens[COUNTS[kind]] if len(tokens)>COUNTS[kind] else '#ff66ff')[:80]
            if kind=='m':
                rest=tokens[COUNTS[kind]] if len(tokens)>COUNTS[kind] else '';col=re.match(r'\(c\s+([^)]*)\)\s*(.*)',rest);r['color']=col[1] if col else '#ffffff';r['text']=(col[2] if col else rest)[:1000]
        return [r]
    except (ValueError,IndexError,TypeError,StopIteration):return []

def paths(root):
    for directory in ('debug-log','ocl-log'):
        for p in sorted((Path(root)/directory).rglob('*')):
            if p.is_file() and not p.is_symlink() and p.suffix in ('.log','.dcl'):
                side='r' if 'right-team' in p.parts else 'l';m=re.search(r'[-_](\d{1,2})\.(log|dcl)$',p.name)
                yield p,side+':'+m[1] if m else side+':'+p.stem

class DebugTail:
    def __init__(self,root):
        self.root=Path(root);self.handles={};self.cache=collections.OrderedDict();self.lock=threading.Lock();self.stop=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.wait(.15):
            for p,agent in paths(self.root):
                try:
                    h=self.handles.setdefault(p,p.open(encoding='utf-8',errors='replace')) if p not in self.handles else self.handles[p]
                    for _ in range(200):
                        position=h.tell();line=h.readline(262145)
                        if not line:break
                        if not line.endswith('\n'):h.seek(position);break
                        for record in parse_line(line,agent):
                            with self.lock:
                                bucket=self.cache.setdefault(record['cycle'],[])
                                if len(bucket)<128:bucket.append(record)
                                while len(self.cache)>64:self.cache.popitem(last=False)
                except OSError:continue
    def frame(self,cycle):
        with self.lock:
            key=cycle if cycle in self.cache else max((k for k in self.cache if 0<=cycle-k<=2),default=cycle)
            return list(self.cache.get(key,[]))
    def close(self):
        self.stop.set();self.thread.join(timeout=2)
        for h in self.handles.values():h.close()

def attach_replay(data,root):
    available={f['cycle'] for f in data['frames']};records={};count=0;omitted=0;budgets={}
    for p,agent in paths(root):
        with p.open(encoding='utf-8',errors='replace') as stream:
            for line in stream:
                for record in parse_line(line,agent):
                    if record['cycle'] not in available:continue
                    bucket=records.setdefault(record['cycle'],[])
                    key=(record['cycle'],record['agent'],'message' if record['kind']=='M' else 'shape')
                    limit=1 if key[2]=='message' else 2
                    if budgets.get(key,0)<limit and len(bucket)<66:
                        budgets[key]=budgets.get(key,0)+1
                        if 'text' in record:record=dict(record,text=record['text'][:120])
                        bucket.append(record);count+=1
                    else:omitted+=1
    for frame in data['frames']:
        if frame['cycle'] in records:frame['debug']=records[frame['cycle']]
    data['debug_records']=count;data['debug_omitted']=omitted
    return data
