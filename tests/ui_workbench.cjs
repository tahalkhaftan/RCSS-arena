const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
eval(fs.readFileSync('tests/ui_monitor.cjs','utf8').split('const frame=')[0].replace("const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');",'').replace('const context=','var context='));
const run=code=>vm.runInContext(code,context),plain=x=>JSON.parse(JSON.stringify(x));
const roles=Array.from({length:11},(_,i)=>({number:i+1,name:i?'Player':'Goalie',type:i?'MF':'G',side:'C',pair:0})),data=Array.from({length:2},(_,i)=>({index:i,ball:{x:i*10,y:i*5},...Object.fromEntries(roles.map(r=>[String(r.number),{x:r.number,y:-r.number}]))}));
context.native=JSON.stringify({version:'20240718-143444',method:'DelaunayTriangulation',role:roles,data,custom_metadata:{retained:true}});
const out=run('const formationFixture=swParseFormation(native);formationFixture.samples[1].players[6].x=12.34;swFormationExport(formationFixture)');assert.equal(JSON.parse(out).data[1]['7'].x,12.34);assert.equal(JSON.parse(out).custom_metadata.retained,true);assert.equal(JSON.parse(out).data[0]['7'].x,7);
context.v3='Formation DelaunayTriangulation 3\nBegin Roles\n'+roles.map(r=>r.number+' '+r.type+' '+r.name+' 0 false false').join('\n')+'\nEnd Roles\nBegin Samples 2 1\n----- 0 -----\nBall 0 0\n'+roles.map(r=>r.number+' '+r.number+' '+(-r.number)).join('\n')+'\nEnd Samples\n# retain this comment\n';
assert.equal(run('swParseFormation(v3).roles[0].name'),'Goalie');assert.match(run('swFormationExport(swParseFormation(v3))'),/retain this comment/);
assert.equal(run("swDebugLine('12,3 1024 l 1 2 3 4 red','l:9')[0].stopped"),3);
assert.equal(run("swDebugLine('12 1024 p NaN 2','l:9').length"),0);
// A VM clock offset must not cause all live frames to be discarded; closed feeds resume history.
context.EventSource=function(url){this.url=url;this.readyState=1;this.close=()=>{this.readyState=2;};};
run("report={status:'running',total:1,matches:[],config:{},progress:{round:1,game:1}};job={id:'7',api:'https://arena.test'};arenaMonitor.key='1/1';$('monitorMode').value='live';startDirectLive();");
context.packet=JSON.stringify({frames:[{round:1,game:1,captured_at:Date.now()/1000-3600,frame:{cycle:100,players:[],ball:[1,2],score:[0,0],names:['A','B'],mode:'3'}}]});
run("directLive.source.onmessage({data:packet,lastEventId:'17'});");assert.equal(run("directLive.frames.get('1/1').frame.cycle"),100);run("directLive.source.readyState=2;startDirectLive();");assert.match(run('directLive.source.url'),/after=17/);assert.equal(run("directLive.frames.get('1/1').frame.cycle"),100);
console.log('PASS native JSON/text formation preservation, debug clocks/validation and live VM-clock/reconnect history');
