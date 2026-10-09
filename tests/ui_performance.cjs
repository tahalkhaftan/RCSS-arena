const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/index.html','utf8'),harness=fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame={')[0];
eval('(()=>{'+harness.replace("const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');",'')+';globalThis.perfHarness={context,el};})()');
const {context,el}=globalThis.perfHarness;
function frame(cycle,x,y,owner,unum=2,velocity){return {cycle,mode:'3',score:[0,0],names:['Alpha','Beta'],ball:[x,y],...(velocity?{ball_velocity:velocity}:{}),players:[['l',1,-50,0,0,true],['r',1,50,0,0,true],['l',2,owner==='l'&&unum===2?x:-20,owner==='l'&&unum===2?y:20,0,false],['l',3,owner==='l'&&unum===3?x:-22,owner==='l'&&unum===3?y:20,0,false],['r',2,owner==='r'?x:20,owner==='r'?y:20,0,false]]};}
function run(frames){const s=context.newPerformance();for(const f of frames)context.recordPerformance(s,f);return s;}
assert.equal(run([frame(1,0,0,'l'),frame(5,10,0,'l',3)]).counts.passOK[0],1);
assert.equal(run([frame(1,0,0,'l'),frame(5,10,0,'l',3)]).counts.deepOK[0],1);
assert.equal(run([frame(1,0,0,'l'),frame(5,10,0,'r')]).counts.deepFail[0],1);
assert.equal(run([frame(1,0,0,'l'),frame(3,0,6,'l',3)]).counts.deepOK[0],0);
assert.equal(run([frame(1,0,0,'l'),frame(20,10,0,'l',3)]).counts.passOK[0],0,'Sparse reports must not invent passes');
const drib=run([frame(1,0,0,'l'),frame(2,1,0,'l'),frame(3,2,0,'l'),frame(4,3,0,'l'),frame(5,4,0,'l')]);assert.equal(drib.counts.dribbleOK[0],1);
// Merely travelling towards goal is not an observed shot on target.
assert.equal(run([frame(1,30,0,'l'),frame(2,32,0,null,2,[2,0])]).counts.shotOn[0],0);
function launch(y=0){const a=frame(1,30,0,'l',2,[0,0]),b=frame(2,32,y,null,2,[2,y]);a.kicks={'l:2':0};b.kicks={'l:2':1};return [a,b];}
assert.equal(run(launch()).counts.shotOn[0],0,'Do not count an unresolved trajectory');
const goal=frame(3,53,0,null);goal.mode='goal_l';goal.score=[1,0];assert.equal(run([...launch(),goal]).counts.shotOn[0],1);
const wide=frame(3,53,11.5,null);assert.equal(run([...launch(1),wide]).counts.shotOff[0],1);
const save=frame(3,48,0,'r',2,[0,0]);save.catchers=['r:1'];const saved=run([...launch(),save]);assert.equal(saved.counts.saves[1],1);assert.equal(saved.counts.shotOn[0],1);
const block=frame(3,40,0,'r');const blocked=run([...launch(),block]);assert.equal(blocked.counts.shotBlocked[0],1);assert.equal(blocked.counts.shotOn[0],0);assert.equal(blocked.counts.saves[1],0);
const teammate=frame(3,40,0,'l',3);const forwardPass=run([...launch(),teammate]);assert.equal(forwardPass.counts.passOK[0],1);assert.equal(forwardPass.counts.shotOn[0],0,'A forward pass is not a shot');
const corners=frame(1,0,0,null);corners.mode='10';const repeated={...corners,cycle:2};const active=frame(3,0,0,'l');const again={...corners,cycle:4};assert.equal(run([corners,repeated,active,again]).counts.corners[0],2,'One count per restart, not per frame');
const tackle=frame(4,2.5,0,'r');tackle.players.find(p=>p[0]==='l'&&p[1]===2).splice(2,2,2,0);assert.equal(run([frame(1,0,0,'l'),frame(2,1,0,'l'),frame(3,2,0,'l'),tackle]).counts.dribbleFail[0],1);
const cross=run([frame(1,0,0,'l'),frame(2,2,1,null,2,[2,1])]);assert.equal(cross.counts.shotOff[0],0,'Far-field forward passes are not shots');
const duplicate=frame(5,10,0,'l',3),once=run([frame(1,0,0,'l'),duplicate,duplicate]);assert.equal(once.counts.passOK[0],1);
// Statistics follow the replay cursor and selected names, not future frames or another game.
context.data={final_score:[0,0],frames:[frame(1,0,0,'l'),frame(5,10,0,'l',3)]};vm.runInContext("monitorSource='file';arenaMonitor.data=data;arenaMonitor.index=0;monitorReplayFrame()",context);
assert.equal(el('performanceLeft').textContent,'Alpha');assert.equal(el('performanceRight').textContent,'Beta');assert.equal(el('performance_passOK_0').textContent,'0');
vm.runInContext('arenaMonitor.index=1;monitorReplayFrame()',context);assert.equal(el('performance_passOK_0').textContent,'1');
vm.runInContext('arenaMonitor.index=0;monitorReplayFrame()',context);assert.equal(el('performance_passOK_0').textContent,'0','Seeking backwards restores earlier statistics');
context.monitorDisplay(null);assert.equal(el('performance_passOK_0').textContent,'—','No data is not a fabricated zero');
assert.ok(source.indexOf('aria-label="عملکرد تیم‌ها"')<source.indexOf('<section class="card results">'));
const noMetadata=context.performanceValues({counts:context.newPerformance().counts,control:[1,1],samples:1,gaps:0,shotMetadata:false},frame(3,0,0,'l'));assert.equal(noMetadata.shotOn,null);assert.equal(noMetadata.saves,null,'Unknown saves must not appear as invented zero');
console.log('PASS: performance passes, deep passes, turnovers, dribbles, shots, missing samples, deduplication and replay/source/cursor isolation');
