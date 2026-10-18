const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const harness=fs.readFileSync('tests/ui_smooth_live.cjs','utf8').split('const a={')[0];
const setup=harness.replace("const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');",'');
eval("(()=>{"+setup+`\n globalThis.timelineHarness={ctx,el,streams,pending,setClock:n=>clock=n};})()`);
const {ctx,el,streams,pending,setClock}=globalThis.timelineHarness;
const frame=(cycle,x,score=[0,0])=>({cycle,mode:'3',names:['A','B'],score,ball:[x,0],players:[['l',2,x,0,0,false]]});
const send=(cycle,stamp,x,score)=>streams[0].onmessage({data:JSON.stringify({frames:[{round:1,game:1,frame:frame(cycle,x,score),captured_at:stamp/1000}]})});
for(let i=0;i<=10;i++)send(100+i,99000+i*100,i);
assert.equal(el('monitorSeek').disabled,false);assert.equal(Number(el('monitorSeek').max),1000);
el('monitorSeek').value='0';el('monitorSeek').input();assert.equal(el('monitorCycle').textContent,'100');assert.equal(el('monitorLiveEdge').hidden,false);assert.equal(el('monitorLiveTrail').style.width,'100%');
setClock(100100);send(111,100100,11,[1,0]);assert.equal(el('monitorCycle').textContent,'100','Incoming frames must not move the paused historical view');assert.equal(el('monitorScore').textContent,'0 : 0','Historical score belongs to the selected moment');assert.equal(Number(el('monitorSeek').max),1100);
el('monitorSeek').value='999999';el('monitorSeek').input();assert.equal(el('monitorCycle').textContent,'111');assert.equal(Number(el('monitorSeek').value),1100,'Cannot seek into future data');
el('monitorSeek').value='0';el('monitorSeek').input();el('monitorLiveButton').click();assert.equal(el('monitorLiveEdge').hidden,true);assert.equal(el('monitorCycle').textContent,'111','Live button jumps to the latest received cycle');assert.equal(Number(el('monitorSeek').value),1100);assert.equal(el('monitorLiveButton').disabled,false);
el('monitorSeek').value='100';el('monitorSeek').input();el('monitorSpeed').value='1';el('monitorPlay').click();setClock(100200);let [id,tick]=pending.entries().next().value;pending.delete(id);tick();assert.equal(el('monitorCycle').textContent,'102','Historical playback moves through captured time');
// Ending the job keeps the in-page history available.
vm.runInContext("report.status='completed';render()",ctx);assert.equal(el('monitorSeek').disabled,false);el('monitorSeek').value='0';el('monitorSeek').input();assert.equal(el('monitorCycle').textContent,'100');
el('monitorSource').value='file';el('monitorSource').change();assert.equal(el('monitorLiveButton').hidden,true);assert.equal(el('monitorLiveEdge').hidden,true);
console.log('PASS: live timeline history, pause while receiving, historical scores, future clamp, live return, playback and completion/source isolation');
