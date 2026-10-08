const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},draw=new Proxy({}, {get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
function el(id){return nodes[id]||(nodes[id]={value:'',textContent:'',className:'',style:{},files:[],options:[],disabled:false,addEventListener(n,f){this[n]=f},setAttribute(){},replaceChildren(){this.options=[]},add(o){this.options.push(o)}})}
el('pitch').getContext=()=>draw;el('pitch').width=1100;el('pitch').height=750;
el('monitorMode').value='live';el('monitorSpeed').value='1';
const ctx={document:{getElementById:el,querySelector:()=>el('track'),querySelectorAll:()=>[]},window:{addEventListener(){}},location:{protocol:'https:',origin:'https://test'},URL,AbortController,console,Option:function(t,v){this.text=t;this.value=v},setTimeout,clearTimeout};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/index.html','utf8').split('<script>')[1].split('</script>')[0],ctx);
const rcg='ULG5\n(server_param (simulator_step 100))\n(team 0 Blue Orange 0 0)\n(show 1 (pm 3) ((b) 1 2 0 0) ((l 1) 0 9 -40 0 0 0 90) ((r 9) 0 1 20 10 0 0 0))\n(team 6000 Blue Orange 2 1)\n(show 6000 ((b) 0 0 0 0) ((l 1) 0 9 -40 0 0 0 90))\n(playmode 6000 time_over)\n';
(async()=>{
 for(const header of ['ULG4','ULG5','ULG6','\ufeffULG6']){const data=await ctx.parseLocalRCG(rcg.replace('ULG5',header));assert.equal(data.frames[0].players.length,2);assert.equal(data.final_score.join(':'),'2:1');}
 const parsed=await ctx.parseLocalRCG(rcg.replace('ULG5','ULG6'));assert.equal(parsed.frames.length,2);assert.equal(parsed.frames[0].players.length,2);assert.equal(parsed.frames[0].players[0][5],true);assert.equal(parsed.final_score.join(':'),'2:1');
 await assert.rejects(ctx.parseLocalRCG('ULG3\n'),/ULG4/);
 await assert.rejects(ctx.parseLocalRCG('ULG5\n'),/داده/);
 el('monitorSource').value='file';el('monitorSource').change();
 el('monitorFile').files=[{name:'match.rcg',size:rcg.length,text:async()=>rcg.replace('ULG5','ULG6')}];await el('monitorFile').change();
 assert.equal(el('monitorScore').textContent,'0 : 0');assert.equal(el('monitorSeek').max,1);assert.equal(el('resultsTitle').textContent,'نتایج RCG');assert.equal(JSON.parse(el('json').textContent).matches[0].right_score,1);assert.equal(el('leftGoals').textContent,2);assert.equal(el('zip').disabled,true);

 // Start a real server request while an independent RCG is playing.
 ctx.FormData=function(){this.append=()=>{}};
 const requests=[];ctx.fetch=async(url,options={})=>{requests.push({url,method:options.method||'GET'});return {ok:true,json:async()=>options.method==='POST'?{id:'new-server'}:{id:'new-server',status:'completed',matches:[],config:{rounds:1,games_per_round:1},total:1,archive_ready:true}};};
 for(const side of ['left','right']){el(side+'Name').value='Server '+side;el(side+'Dir').value='team/';el(side+'Cmd').value='./start';el(side+'Preset').value='preset';}
 el('rounds').value='1';el('games').value='1';el('mode').value='server';el('speed').value='sync';
 el('monitorPlay').click();const playingScore=el('monitorScore').textContent;assert.equal(vm.runInContext('arenaMonitor.playing',ctx),true);
 await el('form').submit({preventDefault(){}});
 assert.equal(requests[0].method,'POST');assert.equal(requests[1].method,'GET');assert.equal(vm.runInContext('arenaMonitor.playing',ctx),true);
 assert.equal(el('monitorScore').textContent,playingScore);assert.equal(JSON.parse(el('json').textContent).source,'rcg_file');
 vm.runInContext('monitorStop();arenaMonitor.index=0',ctx);
 // A playback score change produces a three-second notice, without duplicates.
 const timers=[];ctx.setTimeout=(callback,ms)=>{timers.push({callback,ms});return timers.length;};ctx.clearTimeout=()=>{};
 vm.runInContext('arenaMonitor.playing=true;monitorTick()',ctx);
 assert.equal(el('goalToast').className,'goal-toast visible');assert.match(el('goalToastTitle').textContent,/Blue/);assert.match(el('goalToastScore').textContent,/2 : 1/);
 const notice=timers.find(t=>t.ms===3000);assert.ok(notice);
 vm.runInContext('announceReplayGoal(arenaMonitor.data.frames[1],arenaMonitor.data.frames[1])',ctx);
 assert.equal(timers.filter(t=>t.ms===3000).length,1);notice.callback();assert.equal(el('goalToast').className,'goal-toast');
 vm.runInContext('monitorStop();arenaMonitor.index=0;monitorReplayFrame()',ctx);
 vm.runInContext("report={id:'server',status:'running',matches:[],config:{},total:1};render();updateMonitor()",ctx);
 assert.equal(el('monitorScore').textContent,'0 : 0','Server updates must not replace a local replay');
 el('monitorSeek').value='1';el('monitorSeek').input();assert.equal(el('monitorScore').textContent,'2 : 1');assert.match(el('monitorInfo').textContent,/match.rcg/);
 el('monitorPlay').click();assert.equal(el('monitorPlay').textContent,'توقف موقت ❚❚');el('monitorPlay').click();

 // Server goals remain visible while the independent RCG is on screen.
 vm.runInContext("job=null;report={id:'parallel-server',status:'running',matches:[],total:1,config:{left:{name:'ServerA'},right:{name:'ServerB'}},progress:{round:1,game:1,cycle:10,left_score:0,right_score:0}};render()",ctx);
 vm.runInContext('report.progress.cycle=20;report.progress.right_score=1;render()',ctx);
 assert.match(el('goalToastTitle').textContent,/مسابقهٔ سرور/);assert.match(el('goalToastScore').textContent,/ServerA 0 : 1 ServerB/);
 assert.equal(el('monitorScore').textContent,'2 : 1','Server goal must not replace the RCG picture');
 const noticeCount=timers.filter(t=>t.ms===3000).length;vm.runInContext('render()',ctx);assert.equal(timers.filter(t=>t.ms===3000).length,noticeCount,'Repeated polling must not repeat a goal');
 el('monitorSource').value='server';el('monitorSource').change();
 el('monitorSource').value='file';el('monitorSource').change();
 assert.equal(el('monitorSeek').value,1);assert.equal(el('monitorScore').textContent,'2 : 1','Returning to RCG must preserve the last viewed frame');
 el('monitorFile').files=[{name:'bad.rcg',size:5,text:async()=>'ULG3'}];await el('monitorFile').change();assert.equal(el('monitorBadge').textContent,'خطای فایل RCG');
 vm.runInContext('report=null',ctx);el('monitorSource').value='server';el('monitorSource').change();assert.equal(el('monitorBadge').textContent,'منتظر انتخاب تست');assert.equal(el('resultsTitle').textContent,'گزارش تست');assert.equal(JSON.parse(el('json').textContent).source,undefined);
 console.log('PASS: local RCG parsing, upload, playback, seeking, invalid files and server isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
