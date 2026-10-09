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
assert.equal(run([frame(1,30,0,'l'),frame(2,32,0,null,2,[2,0])]).counts.shotOn[0],1);
assert.equal(run([frame(1,30,0,'l'),frame(2,32,1,null,2,[2,1])]).counts.shotOff[0],1);
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
console.log('PASS: performance passes, deep passes, turnovers, dribbles, shots, missing samples, deduplication and replay/source/cursor isolation');
